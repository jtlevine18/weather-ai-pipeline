"""IDW interpolation and lapse-rate elevation correction."""

from __future__ import annotations
import math
from typing import Any, Dict, List, Optional


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in km."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(a))


def idw_interpolate(
    grid: List[Dict[str, Any]],
    target_lat: float,
    target_lon: float,
    field: str = "temperature",
    power: float = 2.0,
    min_dist_km: float = 0.1,
) -> Optional[float]:
    """
    Inverse Distance Weighting interpolation.
    power=2 is standard. Returns None if no valid grid cells.
    """
    weights, values = [], []

    for cell in grid:
        val = cell.get(field)
        if val is None:
            continue
        dist_km = haversine_km(target_lat, target_lon,
                                cell["lat"], cell["lon"])
        dist_km = max(dist_km, min_dist_km)  # avoid division by zero
        w = 1.0 / (dist_km ** power)
        weights.append(w)
        values.append(val)

    if not weights:
        return None

    total_w = sum(weights)
    if total_w == 0:
        return None

    return sum(w * v for w, v in zip(weights, values)) / total_w


def apply_lapse_rate(
    temperature: float,
    source_alt_m: float,
    target_alt_m: float,
    lapse_rate: float = 0.0065,
) -> float:
    """
    Apply environmental lapse rate correction.
    lapse_rate: °C per meter (default 6.5°C/1000m = 0.0065°C/m)
    """
    delta = target_alt_m - source_alt_m
    return temperature - lapse_rate * delta
