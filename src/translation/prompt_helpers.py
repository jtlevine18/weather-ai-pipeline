"""Translate probabilistic forecast values into farmer-legible natural language.

Never surfaces literal percentages — probability buckets instead.
"""
from typing import Optional


def describe_probabilistic_day(
    rain_prob_5mm: Optional[float],
    rain_p50: Optional[float] = None,
    rainfall_point: Optional[float] = None,  # deterministic fallback
) -> str:
    """Returns a phrase like 'likely moderate rain', 'possible rain', 'mostly dry'.

    Buckets:
      rain_prob_5mm >= 0.6  -> likely
      0.3 <= prob < 0.6     -> possible
      prob < 0.3            -> unlikely / mostly dry

    If ``rain_prob_5mm`` is None (deterministic-only fallback), uses
    ``rainfall_point`` with the existing threshold logic:
      >= 5 mm -> likely rain
      >= 1 mm -> possible rain
      else    -> mostly dry
    Intensity qualifier is added from ``rain_p50`` (or ``rainfall_point``
    on the fallback path) using standard meteorological bucketing:
      < 2.5 mm           -> light
      2.5 - 10 mm        -> moderate
      >= 10 mm           -> heavy
    """
    # Deterministic fallback path — no ensemble probability available.
    if rain_prob_5mm is None:
        amount = rainfall_point if rainfall_point is not None else 0.0
        if amount >= 5.0:
            return f"likely {_intensity(amount)} rain"
        if amount >= 1.0:
            return f"possible {_intensity(amount)} rain"
        return "mostly dry"

    # Probabilistic path.
    intensity = _intensity(rain_p50) if rain_p50 is not None else None
    if rain_prob_5mm >= 0.6:
        return f"likely {intensity} rain" if intensity else "likely rain"
    if rain_prob_5mm >= 0.3:
        return f"possible {intensity} rain" if intensity else "possible rain"
    return "mostly dry"


def _intensity(mm: Optional[float]) -> Optional[str]:
    """Map a rainfall amount (mm) to an intensity qualifier."""
    if mm is None:
        return None
    if mm >= 10.0:
        return "heavy"
    if mm >= 2.5:
        return "moderate"
    return "light"
