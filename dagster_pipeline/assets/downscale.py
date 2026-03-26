"""Step 4: Spatial downscaling to farmer GPS coordinates (grouped by station)."""

import asyncio
from collections import defaultdict
from dagster import asset, AssetExecutionContext, AssetIn
from typing import Any, Dict, List

from config import STATION_MAP
from src.downscaling import IDWDownscaler
from src.delivery import DEFAULT_RECIPIENTS
from src.forecasting import classify_condition
from dagster_pipeline.resources import NASAPowerResource


@asset(
    ins={"forecasts": AssetIn()},
    description="Forecasts downscaled to farmer GPS via IDW interpolation + lapse-rate correction.",
    group_name="pipeline",
)
def downscaled_forecasts(
    context: AssetExecutionContext,
    forecasts: List[Dict[str, Any]],
    nasa_power: NASAPowerResource,
) -> List[Dict[str, Any]]:
    downscaler = IDWDownscaler(nasa_power.get_client())
    recipient_map = {r.station_id: r for r in DEFAULT_RECIPIENTS}

    async def _run():
        # Group forecasts by station — fetch NASA grid once per station, not per forecast
        station_groups: Dict[str, List[int]] = defaultdict(list)
        for idx, fc in enumerate(forecasts):
            station_groups[fc["station_id"]].append(idx)

        ds_tasks = []
        ds_indices = []
        for sid, indices in station_groups.items():
            station = STATION_MAP.get(sid)
            if station is None:
                continue
            recipient = recipient_map.get(sid)
            farmer_lat = recipient.lat if hasattr(recipient, "lat") else station.lat + 0.05
            farmer_lon = recipient.lon if hasattr(recipient, "lon") else station.lon + 0.05
            farmer_alt = recipient.alt_m if recipient else None
            # Downscale one representative forecast per station
            ds_tasks.append(downscaler.downscale(
                forecasts[indices[0]], station, farmer_lat, farmer_lon, farmer_alt
            ))
            ds_indices.append((sid, indices))

        adjustments = await asyncio.gather(*ds_tasks, return_exceptions=True)

        # Apply same spatial adjustment to all forecasts for each station
        downscaled = list(forecasts)
        for adj, (sid, indices) in zip(adjustments, ds_indices):
            if isinstance(adj, Exception):
                context.log.warning(f"Downscale failed for {sid}: {adj}")
                continue
            for idx in indices:
                result = dict(downscaled[idx])
                result["farmer_lat"] = adj["farmer_lat"]
                result["farmer_lon"] = adj["farmer_lon"]
                result["downscaled"] = True
                result["idw_temp"] = adj["idw_temp"]
                result["lapse_delta"] = adj["lapse_delta"]
                result["alt_delta_m"] = adj["alt_delta_m"]
                if adj["idw_temp"] is not None and adj["lapse_delta"] is not None:
                    result["temperature"] = round(adj["idw_temp"] + adj["lapse_delta"], 2)
                    result["condition"] = classify_condition(result)
                downscaled[idx] = result

        return downscaled

    result = asyncio.run(_run())
    n_ds = sum(1 for f in result if isinstance(f, dict) and f.get("downscaled"))
    context.log.info(f"Downscaled {len(result)} forecasts | {n_ds} spatially adjusted")
    return result
