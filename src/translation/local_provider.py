"""
Rule-based advisory provider — no API required.
Used as fallback when Claude API is unavailable.
"""

from __future__ import annotations
from typing import Any, Dict

from src.translation.curated_advisories import get_advisory
from config import StationConfig


# Simple translation stubs (key phrases in Tamil and Malayalam)
_CONDITION_LABELS = {
    "heavy_rain":    {"ta": "கனமழை",         "ml": "ശക്തമായ മഴ"},
    "moderate_rain": {"ta": "மிதமான மழை",     "ml": "മിതമായ മഴ"},
    "heat_stress":   {"ta": "வெப்ப அழுத்தம்", "ml": "ചൂട് സമ്മർദ്ദം"},
    "drought_risk":  {"ta": "வறட்சி அபாயம்",  "ml": "വരൾച്ച അപകടം"},
    "frost_risk":    {"ta": "உறைபனி அபாயம்",  "ml": "മഞ്ഞ് അപകടം"},
    "high_wind":     {"ta": "பலத்த காற்று",    "ml": "ശക്തമായ കാറ്റ്"},
    "foggy":         {"ta": "மூடுபனி",         "ml": "മൂടൽ"},
    "clear":         {"ta": "தெளிவான வானிலை",  "ml": "തെളിഞ്ഞ കാലാവസ്ഥ"},
}


def _build_prefix(condition: str, language: str, temp: float, rain: float) -> str:
    label = _CONDITION_LABELS.get(condition, {}).get(language, condition.replace("_", " ").title())

    if language == "ta":
        return (f"வானிலை அறிவிப்பு: {label}. "
                f"வெப்பநிலை {temp:.1f}°C, மழை {rain:.1f}mm. ")
    elif language == "ml":
        return (f"കാലാവസ്ഥ അറിയിപ്പ്: {label}. "
                f"താപനില {temp:.1f}°C, മഴ {rain:.1f}mm. ")
    else:
        return (f"Weather alert: {condition.replace('_', ' ').title()}. "
                f"Temperature {temp:.1f}°C, Rainfall {rain:.1f}mm. ")


class LocalProvider:
    """Generate rule-based advisory without external APIs."""

    def generate_advisory(
        self,
        forecast: Dict[str, Any],
        station: StationConfig,
    ) -> Dict[str, Any]:
        condition   = forecast.get("condition", "clear")
        temp        = forecast.get("temperature", 25.0) or 25.0
        rain        = forecast.get("rainfall", 0.0) or 0.0
        lang        = station.language

        advisory_en = get_advisory(condition, station.crop_context)
        prefix      = _build_prefix(condition, lang, temp, rain)
        advisory_local = prefix + advisory_en  # simple prefix approach for fallback

        return {
            "advisory_en":    advisory_en,
            "advisory_local": advisory_local,
            "language":       lang,
            "provider":       "rule_based",
            "retrieval_docs": 0,
        }
