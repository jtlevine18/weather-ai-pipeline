"""
Step 4: Downscaling — adjust station-level forecasts to farmer GPS coordinates.
Uses IDW interpolation on NASA POWER grid + lapse-rate elevation correction.
"""

from __future__ import annotations
import logging
from typing import Any, Dict, Optional

from src.downscaling.grid_fetcher import fetch_nasa_grid
from src.downscaling.interpolation import idw_interpolate
from src.forecasting import classify_condition

log = logging.getLogger(__name__)

# Lapse rate: temperature drops ~6.5°C per 1000m gain
LAPSE_RATE_C_PER_M = 0.0065


class IDWDownscaler:
    """
    Downscales station forecasts to farmer GPS location using IDW + lapse-rate.
    NASA POWER provides ~0.5° resolution grid (~55km); IDW gets us to ~5km.
    """

    def __init__(self, nasa_client):
        self.nasa_client = nasa_client

    async def downscale(
        self,
        station_forecast: Dict[str, Any],
        station,
        farmer_lat: float,
        farmer_lon: float,
        farmer_alt_m: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Returns a copy of station_forecast adjusted for the farmer's location.
        Falls back to station forecast if NASA POWER is unavailable.
        """
        result = dict(station_forecast)
        result["farmer_lat"] = farmer_lat
        result["farmer_lon"] = farmer_lon
        result["downscaled"]  = False

        try:
            grid = await fetch_nasa_grid(self.nasa_client, farmer_lat, farmer_lon)
            if not grid:
                log.warning("No NASA POWER grid for (%.3f, %.3f) — using station forecast",
                            farmer_lat, farmer_lon)
                return result

            # IDW interpolation for temperature at farmer's point
            interp_temp = idw_interpolate(
                grid, farmer_lat, farmer_lon, field="temperature"
            )
            if interp_temp is None:
                return result

            # Apply lapse-rate correction if elevation data is available
            station_alt  = station.altitude_m
            farmer_alt   = farmer_alt_m if farmer_alt_m is not None else station_alt
            alt_delta    = farmer_alt - station_alt
            lapse_delta  = -LAPSE_RATE_C_PER_M * alt_delta

            # Blend IDW result with lapse-rate correction
            # Use IDW temperature as the base, then add lapse-rate delta
            downscaled_temp = interp_temp + lapse_delta

            result["temperature"]   = round(downscaled_temp, 2)
            result["downscaled"]    = True
            result["idw_temp"]      = round(interp_temp, 2)
            result["lapse_delta"]   = round(lapse_delta, 3)
            result["alt_delta_m"]   = round(alt_delta, 1)

            # Re-classify after downscaling (a 2.5°C change can shift the condition)
            result["condition"] = classify_condition(result)

        except Exception as exc:
            log.warning("Downscaling failed: %s — using station forecast", exc)

        return result
