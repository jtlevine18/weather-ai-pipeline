"""Step 4: Spatial downscaling to farmer GPS coordinates."""

import asyncio
from dagster import asset, AssetExecutionContext, AssetIn
from typing import Any, Dict, List

from config import STATION_MAP
from src.downscaling import IDWDownscaler
from src.delivery import DEFAULT_RECIPIENTS
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

    async def _passthrough(f):
        return f

    async def _run():
        tasks = []
        for forecast in forecasts:
            sid = forecast["station_id"]
            station = STATION_MAP.get(sid)
            if station is None:
                tasks.append(_passthrough(forecast))
                continue

            recipient = recipient_map.get(sid)
            farmer_lat = recipient.lat if hasattr(recipient, "lat") else station.lat + 0.05
            farmer_lon = recipient.lon if hasattr(recipient, "lon") else station.lon + 0.05
            farmer_alt = recipient.alt_m if recipient else None

            tasks.append(downscaler.downscale(forecast, station, farmer_lat, farmer_lon, farmer_alt))
        return await asyncio.gather(*tasks)

    downscaled = list(asyncio.run(_run()))
    n_ds = sum(1 for f in downscaled if isinstance(f, dict) and f.get("downscaled"))
    context.log.info(f"Downscaled {len(downscaled)} forecasts | {n_ds} spatially adjusted")
    return downscaled
