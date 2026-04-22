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
        Return a *location-based* downscaling adjustment for the farmer's GPS.

        Previously this replaced ``temperature`` with a static value derived
        from the day-0 grid, which is why every day in the 7-day forecast
        ended up with the same number. Now it computes a spatial delta
        (farmer-point minus station-point, both interpolated from the same
        grid) plus a lapse-rate delta, and returns those as separate fields
        without overwriting ``temperature``. step_downscale then adds the
        deltas to each day's ``nwp_temp`` so the per-day GraphCast variation
        is preserved in the final stored value.
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

            # Two IDW interpolations on the same grid: one at the farmer's GPS
            # and one at the station's coordinates. The difference is the pure
            # spatial gradient between the two points — time-independent on a
            # 0.25° grid over a ~10 km separation — so we can apply the same
            # delta to every forecast day without re-interpolating per-day.
            interp_farmer = idw_interpolate(
                grid, farmer_lat, farmer_lon, field="temperature"
            )
            interp_station = idw_interpolate(
                grid, station.lat, station.lon, field="temperature"
            )
            if interp_farmer is None or interp_station is None:
                return result
            spatial_delta = interp_farmer - interp_station

            # Apply lapse-rate correction if elevation data is available
            station_alt  = station.altitude_m
            farmer_alt   = farmer_alt_m if farmer_alt_m is not None else station_alt
            alt_delta    = farmer_alt - station_alt
            lapse_delta  = -LAPSE_RATE_C_PER_M * alt_delta

            result["downscaled"]    = True
            result["idw_temp"]      = round(interp_farmer, 2)
            result["spatial_delta"] = round(spatial_delta, 3)
            result["lapse_delta"]   = round(lapse_delta, 3)
            result["alt_delta_m"]   = round(alt_delta, 1)
            result["grid_source"]   = grid_source

        except Exception as exc:
            log.warning("Downscaling failed: %s — using station forecast", exc)

        return result
