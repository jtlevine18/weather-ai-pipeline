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

    Preferred grid: GraphCast 0.25° regional subgrid (~28km, from forecast model).
    Fallback grid: NASA POWER ~0.5° (~55km, from reanalysis — separate data source).
    """

    def __init__(self, nasa_client):
        self.nasa_client = nasa_client
        self.nwp_grid = None  # Set by pipeline from GraphCast regional extraction

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
        Uses GraphCast 0.25° grid if available, falls back to NASA POWER.
        """
        result = dict(station_forecast)
        result["farmer_lat"] = farmer_lat
        result["farmer_lon"] = farmer_lon
        result["downscaled"]  = False

        try:
            # Prefer GraphCast 0.25° grid (from forecast model, higher resolution)
            grid = self.nwp_grid
            grid_source = "graphcast_0.25"

            # Fall back to NASA POWER if no NWP grid
            if not grid:
                grid = await fetch_nasa_grid(self.nasa_client, farmer_lat, farmer_lon)
                grid_source = "nasa_power_0.5"

            if not grid:
                log.warning("No grid for (%.3f, %.3f) — using station forecast",
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

            downscaled_temp = interp_temp + lapse_delta

            result["temperature"]   = round(downscaled_temp, 2)
            result["downscaled"]    = True
            result["idw_temp"]      = round(interp_temp, 2)
            result["lapse_delta"]   = round(lapse_delta, 3)
            result["alt_delta_m"]   = round(alt_delta, 1)
            result["grid_source"]   = grid_source

            # Re-classify after downscaling (a 2.5°C change can shift the condition)
            result["condition"] = classify_condition(result)

        except Exception as exc:
            log.warning("Downscaling failed: %s — using station forecast", exc)

        return result
