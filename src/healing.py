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
    """Deterministic anomaly detection, correction, and cross-validation."""

    TEMP_MIN, TEMP_MAX     = -5.0, 55.0
    TEMP_VALID_MIN = 0.0
    TEMP_VALID_MAX = 50.0
    RH_MIN, RH_MAX         = 0.0, 100.0
    WIND_MAX               = 150.0
    PRESSURE_MIN           = 850.0
    PRESSURE_MAX           = 1100.0

    # Thresholds for cross-validation against Tomorrow.io / NASA POWER
    CROSS_VAL_THRESHOLDS = {
        "temperature": 8.0,   # °C
        "humidity":    25.0,  # %
        "wind_speed":  15.0,  # km/h
        "pressure":    15.0,  # hPa
        "rainfall":    20.0,  # mm
    }

    WEATHER_FIELDS = ["temperature", "humidity", "wind_speed", "wind_dir", "pressure", "rainfall"]

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
        """Apply rule-based corrections for synthetic fault types. Returns healed copy."""
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

    # ------------------------------------------------------------------
    # Cross-validation against reference source (Tomorrow.io / NASA POWER)
    # ------------------------------------------------------------------

    def fill_nulls(self, reading: Dict[str, Any],
                   reference: Dict[str, Any]) -> tuple:
        """Fill NULL weather fields from reference. Returns (reading, filled_fields)."""
        filled = []
        for field in self.WEATHER_FIELDS:
            if reading.get(field) is None and reference.get(field) is not None:
                reading[field] = reference[field]
                filled.append(field)
        return reading, filled

    def cross_validate(self, reading: Dict[str, Any],
                       reference: Dict[str, Any]) -> Dict[str, Any]:
        """Cross-validate a reading against a reference, fill NULLs, compute quality.

        - Fills NULL fields from reference (never overwrites existing values)
        - Flags anomalies where reading diverges from reference beyond thresholds
        - Computes quality_score from agreement level
        - Returns modified copy of reading with heal_action, heal_source, quality_score
        """
        healed = dict(reading)
        ref_source = reference.get("source", "tomorrow_io")

        # Preserve any existing heal_action from Phase 1 (e.g. typo_corrected)
        prior_action = healed.get("heal_action", "none")

        # Phase 2: Fill NULL fields
        healed, filled_fields = self.fill_nulls(healed, reference)

        # Phase 3: Compare non-NULL fields against reference
        anomaly_fields = []
        agreements = []
        for field, threshold in self.CROSS_VAL_THRESHOLDS.items():
            reading_val = reading.get(field)   # original value (before fill)
            ref_val = reference.get(field)
            if reading_val is not None and ref_val is not None:
                diff = abs(reading_val - ref_val)
                agreement = max(0.0, 1.0 - diff / threshold)
                agreements.append((field, agreement))
                if diff > threshold:
                    anomaly_fields.append(field)

        # Determine heal_action
        actions = []
        if prior_action not in ("none", "original"):
            actions.append(prior_action)
        if filled_fields:
            actions.append("null_filled")
        if anomaly_fields:
            actions.append("anomaly_flagged")

        if actions:
            healed["heal_action"] = "+".join(actions)
            healed["heal_source"] = f"original+{ref_source}"
        elif prior_action in ("none", "original"):
            healed["heal_action"] = "cross_validated"
            healed["heal_source"] = f"original+{ref_source}"
        # else: keep prior_action as-is

        # Compute quality_score
        if agreements:
            # Weight temperature 2x
            total_w = 0.0
            weighted_sum = 0.0
            for field, score in agreements:
                w = 2.0 if field == "temperature" else 1.0
                weighted_sum += w * score
                total_w += w
            base_score = weighted_sum / total_w
        else:
            base_score = 1.0

        # Penalty for fields that are still NULL after filling
        null_count = sum(1 for f in ["temperature", "humidity", "wind_speed", "pressure", "rainfall"]
                         if healed.get(f) is None)
        penalty = null_count * 0.05

        # Filled fields are less trustworthy than independently measured
        fill_penalty = len(filled_fields) * 0.03

        healed["quality_score"] = round(max(0.3, min(1.0, base_score - penalty - fill_penalty)), 3)

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
