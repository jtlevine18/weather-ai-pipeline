"""Per-farmer advisory personalization via templates.

Approach: one Claude call per station -> template expansion per farmer -> zero extra API cost.
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional


def expand_advisory(
    station_advisory: Dict[str, Any],
    farmer_profile: Dict[str, Any],
) -> Dict[str, Any]:
    """Personalize a station-level advisory for a specific farmer.

    Takes the station advisory (generated once per station by Claude)
    and fills in farmer-specific details. No extra API calls required.
    """
    advisory_text = station_advisory.get("advisory_en", "")
    farmer_name = farmer_profile.get("name", "Farmer")
    crops = farmer_profile.get("primary_crops", [])
    area = farmer_profile.get("total_area", 0)
    soil_ph = farmer_profile.get("soil_ph")
    district = farmer_profile.get("district", "")
    language = farmer_profile.get("language", "en")

    crop_str = ", ".join(crops[:3]) if crops else "your crops"
    header = f"Advisory for {farmer_name}"
    if district:
        header += f" ({district})"
    header += f" — {area:.1f} ha of {crop_str}"

    condition = station_advisory.get("condition", "clear")
    temp = station_advisory.get("temperature", 25.0)
    rainfall = station_advisory.get("rainfall", 0.0)

    crop_notes = _crop_specific_notes(crops, condition, temp, rainfall, soil_ph)

    return {
        "farmer_name": farmer_name,
        "station_id": station_advisory.get("station_id", ""),
        "language": language,
        "header": header,
        "station_advisory": advisory_text,
        "crop_notes": crop_notes,
        "personalized_text": (
            f"{header}\n\n{advisory_text}\n\n{crop_notes}" if crop_notes
            else f"{header}\n\n{advisory_text}"
        ),
    }


def expand_for_station(
    station_advisory: Dict[str, Any],
    farmer_profiles: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Expand one station advisory for all farmers at that station."""
    return [expand_advisory(station_advisory, fp) for fp in farmer_profiles]


def _crop_specific_notes(
    crops: List[str],
    condition: str,
    temp: float,
    rainfall: float,
    soil_ph: Optional[float],
) -> str:
    """Generate crop-specific action items based on weather condition."""
    notes: List[str] = []

    for crop in crops[:3]:
        c = crop.lower()

        if condition == "heavy_rain" and rainfall > 50:
            if c in ("rice", "paddy"):
                notes.append(f"  - {crop}: Ensure field drainage; postpone fertilizer")
            elif c in ("coconut", "arecanut"):
                notes.append(f"  - {crop}: Check for waterlogging around root zone")
            elif c == "cotton":
                notes.append(f"  - {crop}: Spray fungicide within 24h if rain continues")
            else:
                notes.append(f"  - {crop}: Delay harvesting until dry spell")

        elif condition == "drought_risk":
            if c in ("rice", "paddy"):
                notes.append(f"  - {crop}: Alternate wetting-drying irrigation if possible")
            elif c == "coconut":
                notes.append(f"  - {crop}: Mulch basin to conserve moisture")
            else:
                notes.append(f"  - {crop}: Irrigate early morning to reduce evaporation")

        elif condition == "high_wind":
            if c == "banana":
                notes.append(f"  - {crop}: Prop up bunches; check guy wires")
            elif c == "sugarcane":
                notes.append(f"  - {crop}: Delay trash removal to reduce lodging risk")
            else:
                notes.append(f"  - {crop}: Secure shade-net structures if any")

        elif temp > 38:
            if c in ("rice", "paddy"):
                notes.append(f"  - {crop}: Maintain 5cm standing water to buffer heat")
            elif c in ("pepper", "cardamom"):
                notes.append(f"  - {crop}: Ensure shade canopy; spray water in afternoon")
            else:
                notes.append(f"  - {crop}: Irrigate in evening to prevent heat stress")

    if soil_ph is not None and soil_ph < 5.5:
        notes.append(f"  - Soil pH ({soil_ph:.1f}) is acidic — consider lime after monsoon")

    return "\n".join(notes) if notes else ""
