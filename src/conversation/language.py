"""Script-based language detection for Tamil/Malayalam/English."""

from __future__ import annotations


# Unicode block ranges
_TAMIL_RANGE     = (0x0B80, 0x0BFF)
_MALAYALAM_RANGE = (0x0D00, 0x0D7F)


def _script_ratio(text: str, start: int, end: int) -> float:
    if not text:
        return 0.0
    count = sum(1 for ch in text if start <= ord(ch) <= end)
    return count / len(text)


def detect_language(text: str) -> str:
    """Detect language from script. Returns 'ta', 'ml', or 'en'."""
    tamil_r = _script_ratio(text, *_TAMIL_RANGE)
    malay_r = _script_ratio(text, *_MALAYALAM_RANGE)

    if tamil_r > 0.15:
        return "ta"
    if malay_r > 0.15:
        return "ml"
    return "en"


def resolve_language(text: str, profile_language: str = "") -> str:
    """Profile language takes priority over detected language."""
    if profile_language in ("ta", "ml"):
        return profile_language
    return detect_language(text)


def language_name(code: str) -> str:
    return {"ta": "Tamil", "ml": "Malayalam", "en": "English"}.get(code, "English")
