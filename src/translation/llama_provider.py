"""
Llama-based advisory personalization + translation via HF Inference API.

Uses a master English advisory (from RAG or curated matrix) and personalizes
it for a specific farmer while translating to their language in a single
forward pass.

Supports two modes:
  - Serverless Inference API (free, rate-limited) — default
  - Dedicated Inference Endpoint (paid, high throughput) — set HF_ENDPOINT_URL
"""

from __future__ import annotations
import asyncio
import logging
import os
from typing import Any, Dict, List, Optional, Union

from config import StationConfig, TranslationConfig

log = logging.getLogger(__name__)

DEFAULT_MODEL = "meta-llama/Meta-Llama-3.1-8B-Instruct"

# Single source of truth for language code → name mapping
LANG_NAMES = {
    "ta": "Tamil", "ml": "Malayalam", "hi": "Hindi",
    "sw": "Swahili", "en": "English", "fr": "French",
    "ar": "Arabic", "am": "Amharic",
}


class LlamaProvider:
    """Personalize + translate advisories via HF Inference (Llama 3.1 8B)."""

    def __init__(self, api_key: str, config: TranslationConfig,
                 hf_token: str = ""):
        # Keep api_key + config so the fallback chain in __init__.py can
        # read them via getattr() and hand them to ClaudeProvider.
        self.api_key = api_key
        self.config = config
        self.hf_token = hf_token
        self.endpoint_url = os.getenv("HF_ENDPOINT_URL", "")
        self.model_id = os.getenv("HF_MODEL_ID", DEFAULT_MODEL)
        self._client = None

    # ------------------------------------------------------------------
    # Client
    # ------------------------------------------------------------------

    def _get_client(self):
        if self._client is not None:
            return self._client
        from huggingface_hub import InferenceClient
        model = self.endpoint_url or self.model_id
        log.info("Using HF %s: %s",
                 "Dedicated Endpoint" if self.endpoint_url else "Serverless Inference",
                 model)
        self._client = InferenceClient(
            model=model,
            token=self.hf_token,
            timeout=120,
        )
        return self._client

    # ------------------------------------------------------------------
    # Master advisory (reuse existing providers)
    # ------------------------------------------------------------------

    def _get_master_advisory(self, forecasts: List[Dict[str, Any]],
                             station: StationConfig) -> str:
        """Get the English master advisory from the curated matrix.

        This is the cheap, zero-cost path. At scale you'd generate masters
        via Claude+RAG once per (crop, condition, severity) and cache them.
        For now the curated matrix covers 9 conditions × 17 crops.
        """
        from src.translation.curated_advisories import get_advisory

        day0 = forecasts[0] if forecasts else {}
        condition = day0.get("condition", "clear")
        advisory = get_advisory(condition, station.crop_context)

        # Enrich with multi-day context
        if len(forecasts) > 1:
            rain_days = [
                i + 1 for i, fc in enumerate(forecasts)
                if (fc.get("rainfall") or 0) > 5.0
            ]
            total_rain = sum(fc.get("rainfall") or 0 for fc in forecasts)
            temps = [fc.get("temperature") for fc in forecasts
                     if fc.get("temperature") is not None]
            temp_range = f"{min(temps):.0f}-{max(temps):.0f}°C" if temps else ""

            if rain_days:
                day_str = ", ".join(f"Day {d}" for d in rain_days)
                advisory += (
                    f" Weekly total: {total_rain:.0f}mm. "
                    f"Rain on {day_str}."
                )
            else:
                advisory += (
                    f" Dry week ({total_rain:.0f}mm total)."
                )
            if temp_range:
                advisory += f" Temperature range: {temp_range}."

        return advisory

    # ------------------------------------------------------------------
    # Prompt construction
    # ------------------------------------------------------------------

    def _build_prompt(self, master_advisory: str, forecasts: List[Dict[str, Any]],
                      station: StationConfig) -> str:
        """Build the personalization + translation prompt for Llama."""
        target_lang = LANG_NAMES.get(station.language, station.language)

        # 7-day forecast summary
        day_labels = ["Today", "Day 2", "Day 3", "Day 4", "Day 5", "Day 6", "Day 7"]
        forecast_lines = []
        for i, fc in enumerate(forecasts[:7]):
            label = day_labels[i] if i < len(day_labels) else f"Day {i+1}"
            cond = (fc.get("condition") or "clear").replace("_", " ")
            temp = fc.get("temperature", 25.0) or 25.0
            rain = fc.get("rainfall", 0.0) or 0.0
            forecast_lines.append(f"  {label}: {cond}, {temp:.0f}°C, {rain:.0f}mm")

        forecast_table = "\n".join(forecast_lines)

        prompt = (
            f"You are an agricultural advisor for smallholder farmers.\n\n"
            f"MASTER ADVISORY (English):\n{master_advisory}\n\n"
            f"WEATHER FORECAST for {station.name}, {station.state}:\n{forecast_table}\n\n"
            f"FARMER CONTEXT:\n"
            f"  Location: {station.name}, {station.state}\n"
            f"  Crops: {station.crop_context}\n"
            f"  Language: {target_lang}\n\n"
            f"TASK: Personalize this advisory for the farmer above. "
            f"Reference specific days from the forecast. "
            f"Keep it 4-6 sentences, practical and actionable.\n\n"
        )

        if station.language != "en":
            prompt += (
                f"Respond in this exact format:\n"
                f"ENGLISH: [personalized advisory in English]\n"
                f"{target_lang.upper()}: [same advisory translated to {target_lang}]\n"
            )
        else:
            prompt += "Respond with just the personalized advisory in English.\n"

        return prompt

    # ------------------------------------------------------------------
    # Response parsing
    # ------------------------------------------------------------------

    def _parse_response(self, text: str, language: str) -> Dict[str, str]:
        """Parse Llama output into English + local advisory."""
        if language == "en":
            return {"advisory_en": text.strip(), "advisory_local": text.strip()}

        lang_label = LANG_NAMES.get(language, language).upper()

        advisory_en = text.strip()
        advisory_local = text.strip()

        # Try to split on ENGLISH: / LANG: markers
        if "ENGLISH:" in text:
            parts = text.split("ENGLISH:", 1)
            rest = parts[1] if len(parts) > 1 else text
            if f"{lang_label}:" in rest:
                en_part, local_part = rest.split(f"{lang_label}:", 1)
                advisory_en = en_part.strip()
                advisory_local = local_part.strip()
            else:
                advisory_en = rest.strip()
                advisory_local = rest.strip()

        return {"advisory_en": advisory_en, "advisory_local": advisory_local}

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    async def generate_advisory(
        self,
        forecasts: Union[Dict[str, Any], List[Dict[str, Any]]],
        station: StationConfig,
    ) -> Dict[str, Any]:
        """Generate personalized + translated advisory via Llama."""
        if isinstance(forecasts, dict):
            forecasts = [forecasts]

        # Step 1: Get the English master advisory (zero cost — curated matrix)
        master = self._get_master_advisory(forecasts, station)

        # Step 2: Personalize + translate via Llama
        prompt = self._build_prompt(master, forecasts, station)
        client = self._get_client()

        # huggingface_hub InferenceClient is sync, so run in executor
        loop = asyncio.get_running_loop()
        response = await loop.run_in_executor(
            None,
            lambda: client.text_generation(
                prompt,
                max_new_tokens=512,
                temperature=0.7,
                do_sample=True,
            ),
        )

        parsed = self._parse_response(response, station.language)

        return {
            "advisory_en":    parsed["advisory_en"],
            "advisory_local": parsed["advisory_local"],
            "language":       station.language,
            "provider":       "llama_hf",
            "retrieval_docs": 0,
        }
