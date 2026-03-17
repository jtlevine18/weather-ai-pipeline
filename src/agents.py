"""
Claude-based observability and self-healing agents.
Also provides a rule-based fallback for when Claude API is unavailable.
"""

from __future__ import annotations
import json
import logging
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Rule-based fallback (no API needed)
# ---------------------------------------------------------------------------

class RuleBasedFallback:
    """Deterministic anomaly detection and correction."""

    TEMP_MIN, TEMP_MAX     = -5.0, 55.0
    TEMP_VALID_MIN = 0.0
    TEMP_VALID_MAX = 50.0
    RH_MIN, RH_MAX         = 0.0, 100.0
    WIND_MAX               = 150.0
    PRESSURE_MIN           = 850.0
    PRESSURE_MAX           = 1100.0

    def detect_anomalies(self, readings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        anomalies = []
        for r in readings:
            issues = []
            temp = r.get("temperature")
            if temp is not None:
                if temp > 100:
                    issues.append({"field": "temperature", "type": "typo",
                                   "value": temp, "correction": temp / 10.0})
                elif not (self.TEMP_MIN <= temp <= self.TEMP_MAX):
                    issues.append({"field": "temperature", "type": "out_of_range",
                                   "value": temp, "correction": None})
            rh = r.get("humidity")
            if rh is not None and not (self.RH_MIN <= rh <= self.RH_MAX):
                issues.append({"field": "humidity", "type": "out_of_range",
                               "value": rh, "correction": max(0, min(100, rh))})
            ws = r.get("wind_speed")
            if ws is not None and ws > self.WIND_MAX:
                issues.append({"field": "wind_speed", "type": "out_of_range",
                               "value": ws, "correction": None})
            if issues:
                anomalies.append({"station_id": r["station_id"],
                                   "reading_id": r.get("id"),
                                   "issues": issues})
        return anomalies

    def heal(self, reading: Dict[str, Any],
              reference: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Apply rule-based corrections. Returns healed copy."""
        healed = dict(reading)
        healed["heal_action"] = "none"
        healed["heal_source"] = "original"

        temp = healed.get("temperature")

        # Typo: temperature 10× too high
        if temp is not None and temp > 100:
            healed["temperature"] = temp / 10.0
            healed["heal_action"] = "typo_corrected"
            healed["heal_source"] = "rule"
            return healed

        # All None → impute from reference if available
        if temp is None and reference and reference.get("temperature") is not None:
            healed["temperature"] = reference["temperature"]
            healed["humidity"]    = reference.get("humidity", healed.get("humidity"))
            healed["wind_speed"]  = reference.get("wind_speed", healed.get("wind_speed"))
            healed["pressure"]    = reference.get("pressure", healed.get("pressure"))
            healed["rainfall"]    = reference.get("rainfall", healed.get("rainfall", 0.0))
            healed["heal_action"] = "imputed_from_reference"
            healed["heal_source"] = reference.get("source", "reference")
            return healed

        if temp is None:
            # No reference and no data — skip record
            return None  # type: ignore

        return healed


# ---------------------------------------------------------------------------
# Observability agent (Claude)
# ---------------------------------------------------------------------------

class ObservabilityAgent:
    """Uses Claude to generate a structured anomaly report."""

    SYSTEM = (
        "You are a weather data quality agent. "
        "Analyze the provided sensor readings and return a JSON array of anomalies. "
        "Each element: {station_id, field, issue_type, details}. "
        "Issue types: typo, out_of_range, offline, drift, missing. "
        "Return ONLY valid JSON, no prose."
    )

    def __init__(self, api_key: str, model: str = "claude-haiku-4-5-20251001"):
        self.api_key = api_key
        self.model   = model
        self._client = None

    def _get_client(self):
        if self._client is None:
            import anthropic
            self._client = anthropic.Anthropic(api_key=self.api_key)
        return self._client

    def analyze(self, readings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not self.api_key:
            return []
        try:
            client = self._get_client()
            payload = json.dumps(readings[:10], default=str)  # limit context
            msg = client.messages.create(
                model=self.model,
                max_tokens=1024,
                system=self.SYSTEM,
                messages=[{"role": "user", "content": f"Readings:\n{payload}"}],
            )
            text = msg.content[0].text.strip()
            # Extract JSON if wrapped in markdown
            if "```" in text:
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            return json.loads(text)
        except Exception as exc:
            log.warning("ObservabilityAgent error: %s", exc)
            return []


# ---------------------------------------------------------------------------
# Self-Healing agent (Claude)
# ---------------------------------------------------------------------------

class SelfHealingAgent:
    """Uses Claude to generate healing instructions for anomalous readings."""

    SYSTEM = (
        "You are a weather data healing agent. "
        "Given a raw sensor reading and reference data (Tomorrow.io), produce a healed version. "
        "Return a JSON object with the corrected fields and 'heal_action' (typo_corrected, "
        "imputed_from_reference, drift_corrected, skipped) and 'heal_source'. "
        "NEVER fabricate data. If you cannot heal a field reliably, set it to null. "
        "Return ONLY valid JSON."
    )

    def __init__(self, api_key: str, model: str = "claude-haiku-4-5-20251001"):
        self.api_key = api_key
        self.model   = model
        self._client = None

    def _get_client(self):
        if self._client is None:
            import anthropic
            self._client = anthropic.Anthropic(api_key=self.api_key)
        return self._client

    def heal(self, reading: Dict[str, Any],
              reference: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        if not self.api_key:
            return None
        try:
            client = self._get_client()
            prompt = (
                f"Raw reading: {json.dumps(reading, default=str)}\n"
                f"Reference (Tomorrow.io): {json.dumps(reference, default=str) if reference else 'unavailable'}"
            )
            msg = client.messages.create(
                model=self.model,
                max_tokens=512,
                system=self.SYSTEM,
                messages=[{"role": "user", "content": prompt}],
            )
            text = msg.content[0].text.strip()
            if "```" in text:
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            healed = json.loads(text)
            # Merge with original to keep non-weather fields
            merged = dict(reading)
            merged.update({k: v for k, v in healed.items()
                           if k in ("temperature","humidity","wind_speed","wind_dir",
                                    "pressure","rainfall","heal_action","heal_source")})
            return merged
        except Exception as exc:
            log.warning("SelfHealingAgent error: %s", exc)
            return None
