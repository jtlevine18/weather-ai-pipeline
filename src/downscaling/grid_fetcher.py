"""Fetch NASA POWER spatial grid for IDW interpolation."""

from __future__ import annotations
import logging
from typing import Any, Dict, List

log = logging.getLogger(__name__)


async def fetch_nasa_grid(
    nasa_client,
    lat: float,
    lon: float,
    radius_deg: float = 0.5,
) -> List[Dict[str, Any]]:
    """
    Fetch a 5×5 grid of NASA POWER points around (lat, lon).
    Returns list of {lat, lon, temperature, ...} dicts with valid data only.
    Filters out NASA's -999 missing value sentinel.
    """
    try:
        grid = await nasa_client.get_grid(lat, lon, radius_deg=radius_deg)
        # Filter out cells where temperature is None (NASA -999 already filtered in client)
        valid = [cell for cell in grid
                 if cell.get("temperature") is not None]
        if len(valid) < 2:
            log.warning("Only %d valid NASA POWER grid cells near (%.2f,%.2f)",
                        len(valid), lat, lon)
        return valid
    except Exception as exc:
        log.warning("fetch_nasa_grid error: %s", exc)
        return []
