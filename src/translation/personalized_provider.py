"""
Per-farmer personalized advisory provider using Claude Haiku 4.5.

This provider takes an already-generated station-level advisory and rewrites it
for a specific farmer using their DPI profile (crops, soil, irrigation, land
area). It is meant to run only for a handful of featured farmers in the weekly
pipeline — the rest of the 2,000-farmer pilot population can reuse it on demand
when a user clicks through in the UI.

Design notes
------------
- Haiku 4.5, not Sonnet: advisory rewriting from a draft is a template-fill task,
  not a reasoning task. Haiku handles it at ~3x lower cost. Reasoning lives in
  the station-level RAG advisory that seeds this provider.
- Prompt structure is cache-ready: the system prompt comes first with a
  `cache_control` marker so static content is cached when content size crosses
  Haiku's minimum (2048 tokens). Today's prompts are below that threshold so
  the marker is a no-op in practice — it'll activate automatically if the
  system prompt or station draft grows.
- Single call per farmer: English and local-language (Tamil/Malayalam) are
  generated in one shot with a structured output format, halving the calls
  vs a two-step generate→translate chain.
- Failure mode: any exception bubbles up to the caller, which should fall back
  to showing the station-level advisory unchanged. No retries here.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, Optional

log = logging.getLogger(__name__)


_SYSTEM_PROMPT = (
    "You are an agricultural extension advisor writing personalized weekly "
    "advisories for individual smallholder farmers in Kerala and Tamil Nadu. "
    "You are given a station-level weekly weather advisory that applies to "
    "the whole district, plus one specific farmer's profile (crops, soil, "
    "irrigation, land size). Rewrite the advisory so it is specifically about "
    "what THIS farmer should do this week, given their situation.\n\n"
    "Requirements:\n"
    "- 3 to 5 sentences total, in plain language.\n"
    "- Name the farmer's actual crops when giving advice.\n"
    "- If the station advisory references specific days (Day 3, Day 5), keep those.\n"
    "- Give one or two concrete actions — do/don't spray, irrigate, harvest, cover, etc.\n"
    "- Do not add caveats, disclaimers, or filler. Do not mention that this is personalized.\n"
    "- Write with empathy and directness — this is talking to one person, not a crowd.\n\n"
    "You must ALSO produce a short SMS version of the same advisory, 160 "
    "characters maximum, plain text (no markdown, no emoji), calling out the "
    "single most important action for this farmer this week. Generate an "
    "English SMS and a local-language SMS. Both SMS messages must stay under "
    "160 characters.\n\n"
    "Output format (exactly, four blocks, in this order):\n"
    "ENGLISH:\n"
    "<the English version, 3-5 sentences>\n\n"
    "LOCAL:\n"
    "<the same advisory in the requested local language, same length>\n\n"
    "SMS_ENGLISH:\n"
    "<<=160 char English SMS>\n\n"
    "SMS_LOCAL:\n"
    "<<=160 char SMS in the requested local language>"
)


@dataclass
class PersonalizedAdvisoryResult:
    advisory_en: str
    advisory_local: str
    model: str
    sms_en: Optional[str] = None
    sms_local: Optional[str] = None
    tokens_in: int = 0
    tokens_out: int = 0
    cache_read_tokens: int = 0


class PersonalizedAdvisoryProvider:
    """Rewrites a station-level advisory for a specific farmer via Haiku 4.5."""

    def __init__(self, api_key: str, model: str = "claude-haiku-4-5-20251001"):
        self.api_key = api_key
        self.model = model
        self._client = None

    def _get_client(self):
        if self._client is None:
            import anthropic
            self._client = anthropic.AsyncAnthropic(api_key=self.api_key)
        return self._client

    async def personalize(
        self,
        station_advisory_en: str,
        station,
        farmer_profile,
        language: str = "en",
    ) -> PersonalizedAdvisoryResult:
        """Generate a per-farmer advisory from a station draft + DPI profile."""
        lang_name = {"ml": "Malayalam", "ta": "Tamil", "en": "English"}.get(language, "English")

        # Extract farmer-specific context from the DPI profile. These are the
        # knobs that distinguish one farmer from another in the same village.
        land = farmer_profile.land_records[0] if farmer_profile.land_records else None
        crops = ", ".join(land.crops_registered) if land and land.crops_registered else "mixed crops"
        soil_type = land.soil_type if land else "unknown"
        irrigation = land.irrigation_type if land else "unknown"
        area = land.area_hectares if land else 0.0
        pH = farmer_profile.soil_health.pH if farmer_profile.soil_health else 7.0

        user_msg = (
            f"Station-level weekly advisory for {station.name}, {station.state}:\n"
            f"---\n{station_advisory_en}\n---\n\n"
            f"This farmer's profile:\n"
            f"- Crops grown: {crops}\n"
            f"- Soil type: {soil_type}\n"
            f"- Irrigation: {irrigation}\n"
            f"- Land area: {area:.2f} hectares\n"
            f"- Soil pH: {pH}\n\n"
            f"Rewrite the advisory for this specific farmer. Output BOTH an "
            f"English version AND a {lang_name} version, using the exact format "
            f"from your instructions."
        )

        # Cache-ready layout: system prompt (static) marked ephemeral. When the
        # static prefix grows past Haiku's 2048-token minimum, caching activates
        # automatically without any code change.
        system_blocks = [
            {
                "type": "text",
                "text": _SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ]

        client = self._get_client()
        msg = await client.messages.create(
            model=self.model,
            max_tokens=900,
            system=system_blocks,
            messages=[{"role": "user", "content": user_msg}],
        )
        text = msg.content[0].text.strip() if msg.content else ""
        advisory_en, advisory_local, sms_en, sms_local = _parse_quad_output(text)

        # For English stations, the "local" version is the English itself.
        if language == "en" and not advisory_local:
            advisory_local = advisory_en
        if language == "en" and not sms_local:
            sms_local = sms_en

        # Hard cap SMS at 160 chars — the prompt asks the model to self-limit,
        # but belt-and-suspenders keeps bad responses from breaking downstream
        # truncation assumptions.
        if sms_en and len(sms_en) > 160:
            sms_en = sms_en[:157].rstrip() + "..."
        if sms_local and len(sms_local) > 160:
            sms_local = sms_local[:157].rstrip() + "..."

        usage = getattr(msg, "usage", None)
        return PersonalizedAdvisoryResult(
            advisory_en=advisory_en or station_advisory_en,
            advisory_local=advisory_local or advisory_en or station_advisory_en,
            sms_en=sms_en or None,
            sms_local=sms_local or None,
            model=self.model,
            tokens_in=getattr(usage, "input_tokens", 0) if usage else 0,
            tokens_out=getattr(usage, "output_tokens", 0) if usage else 0,
            cache_read_tokens=getattr(usage, "cache_read_input_tokens", 0) if usage else 0,
        )


def _parse_quad_output(text: str) -> tuple[str, str, str, str]:
    """Split the model's ENGLISH:/LOCAL:/SMS_ENGLISH:/SMS_LOCAL: structured
    output into four strings.

    Falls back to (text, "", "", "") if the model ignored the format — which
    rarely happens with Haiku 4.5 on a task this structured, but we don't
    want to error out of the whole pipeline on a parse miss.
    """
    def _grab(label: str, stop: Optional[str]) -> str:
        if stop:
            pat = rf"{label}:\s*(.*?)(?:\n\s*{stop}:|$)"
        else:
            pat = rf"{label}:\s*(.*?)\s*$"
        m = re.search(pat, text, re.DOTALL | re.IGNORECASE)
        return m.group(1).strip() if m else ""

    en = _grab("ENGLISH", "LOCAL")
    local = _grab("LOCAL", "SMS_ENGLISH")
    sms_en = _grab("SMS_ENGLISH", "SMS_LOCAL")
    sms_local = _grab("SMS_LOCAL", None)
    if not en and not local and not sms_en and not sms_local:
        return text, "", "", ""
    return en, local, sms_en, sms_local
