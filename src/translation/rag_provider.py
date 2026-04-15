"""
RAG-based advisory generation with hybrid FAISS/BM25 retrieval + Claude generation.
Two-step: English advisory first, then separate translation call.
"""

from __future__ import annotations
import logging
import re
from typing import Any, Dict, List, Optional, Tuple, Union

log = logging.getLogger(__name__)

SCORE_THRESHOLD = 0.35
TOP_K           = 5
ALPHA           = 0.5  # FAISS weight in blend


# ---------------------------------------------------------------------------
# BM25 sparse scorer
# ---------------------------------------------------------------------------

class _BM25:
    """Lightweight BM25 implementation — no external dependency."""
    def __init__(self, corpus: List[str], k1: float = 1.5, b: float = 0.75):
        import math
        self.k1 = k1
        self.b  = b
        self.corpus = corpus
        self.N = len(corpus)
        self.avgdl = sum(len(d.split()) for d in corpus) / max(1, self.N)
        # Build IDF
        from collections import Counter, defaultdict
        df = defaultdict(int)
        self.tokenized = [doc.lower().split() for doc in corpus]
        for toks in self.tokenized:
            for word in set(toks):
                df[word] += 1
        self.idf = {w: math.log((self.N - n + 0.5) / (n + 0.5) + 1)
                    for w, n in df.items()}

    def score(self, query: str, doc_idx: int) -> float:
        from collections import Counter
        toks   = query.lower().split()
        doc    = self.tokenized[doc_idx]
        dl     = len(doc)
        counts = Counter(doc)
        score  = 0.0
        for term in toks:
            if term not in self.idf:
                continue
            tf = counts[term]
            score += self.idf[term] * (
                tf * (self.k1 + 1)
                / (tf + self.k1 * (1 - self.b + self.b * dl / self.avgdl))
            )
        return score

    def scores(self, query: str) -> List[float]:
        return [self.score(query, i) for i in range(self.N)]


# ---------------------------------------------------------------------------
# Hybrid retriever
# ---------------------------------------------------------------------------

class HybridRetriever:
    def __init__(self, index, corpus: List[str], embedder, bm25: _BM25,
                  alpha: float = ALPHA):
        self.index    = index
        self.corpus   = corpus
        self.embedder = embedder
        self.bm25     = bm25
        self.alpha    = alpha

    def retrieve(self, query: str, top_k: int = TOP_K,
                  threshold: float = SCORE_THRESHOLD) -> List[Tuple[str, float]]:
        """Returns list of (text, blended_score) above threshold."""
        import numpy as np

        # Dense (FAISS) scores
        q_vec = np.array(self.embedder.embed_query(query), dtype="float32")
        q_vec = q_vec / (np.linalg.norm(q_vec) + 1e-10)
        q_vec = q_vec.reshape(1, -1)

        n_search = min(len(self.corpus), top_k * 5)
        D, I     = self.index.search(q_vec, n_search)
        dense_scores = {int(i): float(d) for i, d in zip(I[0], D[0]) if i >= 0}

        # Sparse (BM25) scores — normalize to [0,1]
        bm25_raw = self.bm25.scores(query)
        bm25_max = max(bm25_raw) if bm25_raw else 1.0
        if bm25_max == 0:
            bm25_max = 1.0
        bm25_norm = {i: v / bm25_max for i, v in enumerate(bm25_raw)}

        # Blend scores for union of candidates
        candidates = set(dense_scores.keys()) | set(bm25_norm.keys())
        blended = []
        for idx in candidates:
            ds = dense_scores.get(idx, 0.0)
            bs = bm25_norm.get(idx, 0.0)
            blended.append((idx, self.alpha * ds + (1 - self.alpha) * bs))

        blended.sort(key=lambda x: x[1], reverse=True)

        results, seen = [], set()
        for idx, score in blended[:top_k * 3]:
            if score < threshold:
                continue
            text = self.corpus[idx].strip()
            if text in seen or len(text) < 20:
                continue
            seen.add(text)
            results.append((text, score))
            if len(results) >= top_k:
                break

        return results


# ---------------------------------------------------------------------------
# RAG provider
# ---------------------------------------------------------------------------

class RAGProvider:
    def __init__(self, api_key: str, config):
        self.api_key   = api_key
        self.config    = config
        self._retriever: Optional[HybridRetriever] = None
        self._client   = None

    def _ensure_retriever(self):
        if self._retriever is not None:
            return
        try:
            from src.translation.rag_index_builder import build_index, EMBED_MODEL
            from langchain_huggingface import HuggingFaceEmbeddings

            index, corpus = build_index()
            if index is None or not corpus:
                log.warning("RAG index unavailable — will use rule-based fallback")
                return

            embedder = HuggingFaceEmbeddings(model_name=EMBED_MODEL)
            bm25     = _BM25(corpus)
            self._retriever = HybridRetriever(index, corpus, embedder, bm25,
                                               alpha=self.config.alpha)
        except Exception as exc:
            log.warning("Failed to init RAG retriever: %s", exc)

    def _get_client(self):
        if self._client is None:
            import anthropic
            self._client = anthropic.AsyncAnthropic(api_key=self.api_key)
        return self._client

    def _query_reformulation(self, forecasts: List[Dict[str, Any]],
                              station) -> str:
        """Convert 7-day forecast list to natural language retrieval query."""
        crops = station.crop_context
        state = station.state

        # Extract key events across the week for better RAG retrieval
        conditions = set()
        max_rain = 0.0
        temp_range = [100.0, -100.0]
        for fc in forecasts:
            conditions.add((fc.get("condition") or "clear").replace("_", " "))
            max_rain = max(max_rain, fc.get("rainfall") or 0.0)
            t = fc.get("temperature")
            if t is not None:
                temp_range[0] = min(temp_range[0], t)
                temp_range[1] = max(temp_range[1], t)

        condition_str = ", ".join(sorted(conditions))
        return (
            f"Weekly outlook: {condition_str} conditions for {crops} in {state}. "
            f"Temperature range {temp_range[0]:.0f}-{temp_range[1]:.0f}°C, "
            f"max rainfall {max_rain:.0f}mm. "
            f"Agricultural advisory recommendations for the week."
        )

    async def _generate_english(self, forecasts: List[Dict[str, Any]], station,
                                  context_docs: List[str]) -> Dict[str, str]:
        """Step 1: Generate English weekly outlook advisory + SMS version from RAG context.

        Returns a dict with ``advisory_en`` (full markdown) and ``sms_en``
        (<=160 char plain text). If the model skips the SMS block, ``sms_en``
        falls back to an empty string and the caller should treat it as None.
        """
        context = "\n---\n".join(context_docs[:TOP_K]) if context_docs else ""

        # Build 7-day forecast table for the prompt
        day_labels = ["Today", "Day 2", "Day 3", "Day 4", "Day 5", "Day 6", "Day 7"]
        forecast_lines = []
        for i, fc in enumerate(forecasts[:7]):
            label = day_labels[i] if i < len(day_labels) else f"Day {i+1}"
            cond = (fc.get("condition") or "clear").replace("_", " ")
            temp = fc.get("temperature", 25.0) or 25.0
            rain = fc.get("rainfall", 0.0) or 0.0
            wind = fc.get("wind_speed", 0.0) or 0.0
            forecast_lines.append(
                f"  {label}: {cond}, {temp:.0f}°C, {rain:.0f}mm rain, {wind:.0f}km/h wind"
            )

        system = (
            "You are an agricultural extension advisor for smallholder farmers in India. "
            "Generate a concise weekly outlook advisory (4-6 sentences) based on the 7-day "
            "weather forecast. Reference specific days when giving actionable advice "
            "(e.g., 'avoid spraying on Day 3-4 due to heavy rain'). "
            "Be specific to the crops and conditions. "
            "Write in plain English that can be easily understood and translated.\n\n"
            "You MUST ALSO generate a short SMS version that fits on a 2G phone "
            "(160 characters maximum, plain text, no markdown, no emoji). The SMS "
            "must call out the single most important action for the week. "
            "The SMS block is mandatory — responses without it are invalid.\n\n"
            "Respond with EXACTLY these two blocks, in this order, with nothing else:\n\n"
            "ADVISORY:\n"
            "<the full 4-6 sentence advisory>\n\n"
            "SMS:\n"
            "<the <=160 character SMS version — required, never empty>"
        )
        user = (
            f"7-day weather forecast for {station.name}, {station.state}:\n"
            + "\n".join(forecast_lines) + "\n\n"
            f"Crops: {station.crop_context}\n\n"
            f"Knowledge base:\n{context if context else '[No relevant documents found]'}\n\n"
            "Generate the advisory and SMS for the farmer:"
        )
        client = self._get_client()
        # Assistant prefill forces the ADVISORY:/SMS: format reliably — Claude
        # cannot "unwrite" a prefilled assistant turn, so it has to continue
        # the format from "ADVISORY:\n" onward. This is more reliable than
        # prompt instructions alone (Claude silently ignores "output format"
        # directives sometimes) and doesn't depend on tool-use SDK support.
        msg = await client.messages.create(
            model=self.config.model,
            max_tokens=800,
            system=system,
            messages=[
                {"role": "user", "content": user},
                {"role": "assistant", "content": "ADVISORY:\n"},
            ],
        )
        continuation = msg.content[0].text if msg.content else ""
        text = "ADVISORY:\n" + continuation
        advisory_en, sms_en = _parse_advisory_and_sms(text)
        # Hard cap SMS at 160 chars — prompt asks the model to self-limit,
        # but we don't trust the model to count precisely.
        if sms_en and len(sms_en) > 160:
            sms_en = sms_en[:157].rstrip() + "..."
        return {"advisory_en": advisory_en, "sms_en": sms_en}

    async def _translate(self, advisory_en: str, sms_en: str, language: str,
                   station_name: str) -> Dict[str, str]:
        """Step 2: Separate Claude call to translate both advisory and SMS.

        Returns dict with ``advisory_local`` and ``sms_local``. For English
        stations both pass through unchanged.
        """
        if language == "en":
            return {"advisory_local": advisory_en, "sms_local": sms_en}

        lang_name = {"ta": "Tamil", "ml": "Malayalam"}.get(language, language)

        system = (
            f"You are a professional translator specializing in agricultural content. "
            f"Translate both the full advisory and the SMS version into {lang_name}. "
            f"Preserve technical terms, numbers, and actionable instructions precisely. "
            f"The SMS translation MUST stay under 160 characters in {lang_name}. "
            f"The SMS block is mandatory — responses without it are invalid.\n\n"
            f"Respond with EXACTLY these two blocks, in this order, with nothing else:\n\n"
            f"ADVISORY:\n"
            f"<full advisory in {lang_name}>\n\n"
            f"SMS:\n"
            f"<SMS in {lang_name}, ≤160 characters — required, never empty>"
        )
        user = (
            f"Translate these agricultural advisories for farmers near {station_name} to {lang_name}:\n\n"
            f"ADVISORY:\n{advisory_en}\n\n"
            f"SMS:\n{sms_en}"
        )
        client = self._get_client()
        msg = await client.messages.create(
            model=self.config.model,
            max_tokens=900,
            system=system,
            messages=[
                {"role": "user", "content": user},
                {"role": "assistant", "content": "ADVISORY:\n"},
            ],
        )
        continuation = msg.content[0].text if msg.content else ""
        text = "ADVISORY:\n" + continuation
        advisory_local, sms_local = _parse_advisory_and_sms(text)
        if not advisory_local:
            # Belt-and-suspenders: if the parser somehow got nothing,
            # fall back to the English advisory rather than dropping content.
            advisory_local = advisory_en
        if sms_local and len(sms_local) > 160:
            sms_local = sms_local[:157].rstrip() + "..."
        return {"advisory_local": advisory_local, "sms_local": sms_local}

    async def generate_advisory(
        self,
        forecasts: Union[Dict[str, Any], List[Dict[str, Any]]],
        station,
    ) -> Dict[str, Any]:
        """Full RAG advisory generation pipeline. Accepts list of daily forecasts."""
        if isinstance(forecasts, dict):
            forecasts = [forecasts]
        self._ensure_retriever()

        # Retrieval
        context_docs = []
        if self._retriever:
            query = self._query_reformulation(forecasts, station)
            hits  = self._retriever.retrieve(query, top_k=TOP_K,
                                              threshold=self.config.score_threshold)
            context_docs = [text for text, _ in hits]

        # Generate English weekly outlook advisory + SMS
        english = await self._generate_english(forecasts, station, context_docs)
        advisory_en = english.get("advisory_en", "")
        sms_en = english.get("sms_en") or None  # empty string -> None for DB

        # Translate both advisory + SMS
        translated = await self._translate(
            advisory_en, sms_en or "", station.language, station.name,
        )
        advisory_local = translated.get("advisory_local", "")
        sms_local = translated.get("sms_local") or None

        return {
            "advisory_en":    advisory_en,
            "advisory_local": advisory_local,
            "sms_en":         sms_en,
            "sms_local":      sms_local,
            "language":       station.language,
            "provider":       "rag_claude",
            "retrieval_docs": len(context_docs),
        }


def _parse_advisory_and_sms(text: str) -> Tuple[str, str]:
    """Split an ADVISORY:/SMS: structured response into (advisory, sms).

    Tolerant to case and whitespace. If the response lacks either header,
    falls back to (text, "") so the caller never crashes on a parse miss.
    """
    if not text:
        return "", ""
    adv_match = re.search(r"ADVISORY:\s*(.*?)(?:\n\s*SMS:|$)", text, re.DOTALL | re.IGNORECASE)
    sms_match = re.search(r"SMS:\s*(.*?)\s*$", text, re.DOTALL | re.IGNORECASE)
    advisory = adv_match.group(1).strip() if adv_match else ""
    sms = sms_match.group(1).strip() if sms_match else ""
    if not advisory and not sms:
        return text.strip(), ""
    return advisory, sms
