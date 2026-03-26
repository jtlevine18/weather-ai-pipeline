"""
Direct Claude advisory generation — no RAG, no vector search.
Sends forecast + crop context directly to Claude and parses English + local language.
Used as fallback when RAGProvider fails.
"""

from __future__ import annotations
import logging
from typing import Any, Dict

log = logging.getLogger(__name__)

LANG_NAMES = {"ta": "Tamil", "ml": "Malayalam", "en": "English"}


class ClaudeProvider:
    def __init__(self, api_key: str, config):
        self.api_key = api_key
        self.config  = config
        self._client = None

    def _get_client(self):
        if self._client is None:
            import anthropic
            self._client = anthropic.AsyncAnthropic(api_key=self.api_key)
        return self._client

    async def generate_advisory(
        self,
        forecast: Dict[str, Any],
        station,
    ) -> Dict[str, Any]:
        condition  = forecast.get("condition", "clear").replace("_", " ")
        temp       = forecast.get("temperature", 25.0)
        rain       = forecast.get("rainfall", 0.0)
        wind       = forecast.get("wind_speed", 0.0)
        lang       = station.language
        lang_name  = LANG_NAMES.get(lang, "English")

        system = (
            "You are an agricultural extension advisor for smallholder farmers in South India. "
            "Write practical, actionable weather advisories specific to the crops and conditions. "
            "Be concise — each advisory should be 2-3 sentences."
        )

        if lang == "en":
            user = (
                f"Weather forecast for {station.name}, {station.state}:\n"
                f"  Condition: {condition}\n"
                f"  Temperature: {temp:.1f}°C\n"
                f"  Rainfall: {rain:.1f}mm\n"
                f"  Wind: {wind:.1f} km/h\n"
                f"  Crops: {station.crop_context}\n\n"
                "Write a 2-3 sentence actionable advisory for the farmer."
            )
        else:
            user = (
                f"Weather forecast for {station.name}, {station.state}:\n"
                f"  Condition: {condition}\n"
                f"  Temperature: {temp:.1f}°C\n"
                f"  Rainfall: {rain:.1f}mm\n"
                f"  Wind: {wind:.1f} km/h\n"
                f"  Crops: {station.crop_context}\n\n"
                f"Write a 2-3 sentence actionable advisory. "
                f"Respond in this exact format:\n"
                f"ENGLISH: [advisory in English]\n"
                f"{lang_name.upper()}: [same advisory translated to {lang_name}]"
            )

        client  = self._get_client()
        msg     = await client.messages.create(
            model=self.config.model,
            max_tokens=400,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        text = msg.content[0].text.strip()

        # Parse response
        advisory_en    = ""
        advisory_local = ""

        if lang == "en":
            advisory_en = advisory_local = text
        else:
            for line in text.splitlines():
                if line.upper().startswith("ENGLISH:"):
                    advisory_en = line[len("ENGLISH:"):].strip()
                elif line.upper().startswith(lang_name.upper() + ":"):
                    advisory_local = line[len(lang_name) + 1:].strip()
            # Fallbacks if parsing failed
            if not advisory_en:
                advisory_en = text
            if not advisory_local:
                advisory_local = advisory_en

        return {
            "advisory_en":    advisory_en,
            "advisory_local": advisory_local,
            "language":       lang,
            "provider":       "rag_claude",
            "retrieval_docs": 0,
        }
