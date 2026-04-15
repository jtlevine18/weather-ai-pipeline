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
            "Write in plain English that can be easily understood and translated. "
            "You must also produce a short SMS version (≤160 characters, plain text, no markdown, no emoji) "
            "calling out the single most important action for the week. "
            "Return both via the emit_advisory tool."
        )
        user = (
            f"7-day weather forecast for {station.name}, {station.state}:\n"
            + "\n".join(forecast_lines) + "\n\n"
            f"Crops: {station.crop_context}\n\n"
            f"Knowledge base:\n{context if context else '[No relevant documents found]'}\n\n"
            "Generate the advisory and SMS for the farmer:"
        )
        tools = [{
            "name": "emit_advisory",
            "description": "Emit the weekly farmer advisory and an SMS-sized version",
            "input_schema": {
                "type": "object",
                "properties": {
                    "advisory_en": {
                        "type": "string",
                        "description": "4-6 sentence weekly advisory in plain English, referencing specific days and the farmer's crops",
                    },
                    "sms_en": {
                        "type": "string",
                        "description": "Plain-text SMS version, 160 characters maximum, no markdown, no emoji, calling out the single most important action for the week",
                    },
                },
                "required": ["advisory_en", "sms_en"],
            },
        }]
        client = self._get_client()
        msg = await client.messages.create(
            model=self.config.model,
            max_tokens=800,
            system=system,
            messages=[{"role": "user", "content": user}],
            tools=tools,
            tool_choice={"type": "tool", "name": "emit_advisory"},
        )
        advisory_en = ""
        sms_en = ""
        for block in (msg.content or []):
            if getattr(block, "type", None) == "tool_use" and getattr(block, "name", None) == "emit_advisory":
                inputs = block.input or {}
                advisory_en = (inputs.get("advisory_en") or "").strip()
                sms_en = (inputs.get("sms_en") or "").strip()
                break
        # Hard cap SMS at 160 chars — tool schema asks the model to self-limit,
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
            f"Return the translations via the emit_translation tool."
        )
        user = (
            f"Translate these agricultural advisories for farmers near {station_name} to {lang_name}.\n\n"
            f"Full advisory (English):\n{advisory_en}\n\n"
            f"SMS version (English):\n{sms_en}"
        )
        tools = [{
            "name": "emit_translation",
            "description": f"Emit the {lang_name} translation of both the full advisory and the SMS",
            "input_schema": {
                "type": "object",
                "properties": {
                    "advisory_local": {
                        "type": "string",
                        "description": f"The full advisory translated into {lang_name}, preserving technical terms, numbers, and actions",
                    },
                    "sms_local": {
                        "type": "string",
                        "description": f"The SMS translated into {lang_name}, 160 characters maximum, plain text, no markdown",
                    },
                },
                "required": ["advisory_local", "sms_local"],
            },
        }]
        client = self._get_client()
        msg = await client.messages.create(
            model=self.config.model,
            max_tokens=900,
            system=system,
            messages=[{"role": "user", "content": user}],
            tools=tools,
            tool_choice={"type": "tool", "name": "emit_translation"},
        )
        advisory_local = ""
        sms_local = ""
        for block in (msg.content or []):
            if getattr(block, "type", None) == "tool_use" and getattr(block, "name", None) == "emit_translation":
                inputs = block.input or {}
                advisory_local = (inputs.get("advisory_local") or "").strip()
                sms_local = (inputs.get("sms_local") or "").strip()
                break
        if not advisory_local:
            # Belt-and-suspenders: if the tool call somehow returned empty,
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
