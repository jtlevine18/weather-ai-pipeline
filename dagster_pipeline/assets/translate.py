"""Step 5: Generate bilingual agricultural advisories (one per station, 7-day weekly)."""

import asyncio
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from dagster import asset, AssetExecutionContext, AssetIn
from typing import Any, Dict, List

from config import STATION_MAP, PipelineConfig
from src.translation import get_provider, generate_advisory
from src.translation.local_provider import LocalProvider
from src.models import Advisory
from dagster_pipeline.resources import AnthropicResource


@asset(
    ins={"downscaled_forecasts": AssetIn()},
    description="Bilingual agricultural advisories via RAG + Claude (or rule-based fallback).",
    group_name="pipeline",
)
def agricultural_alerts(
    context: AssetExecutionContext,
    downscaled_forecasts: List[Dict[str, Any]],
    anthropic: AnthropicResource,
) -> List[Dict[str, Any]]:
    config = PipelineConfig()
    provider = get_provider(anthropic.api_key, config.translation)

    async def _run():
        alerts = []
        tasks = []
        stations_list = []

        # Group forecasts by station — one advisory per station (weekly)
        station_forecasts: Dict[str, List[Dict]] = defaultdict(list)
        for fc in downscaled_forecasts:
            station_forecasts[fc["station_id"]].append(fc)

        for sid, fc_list in station_forecasts.items():
            station = STATION_MAP.get(sid)
            if station is None:
                continue
            fc_list.sort(key=lambda f: f.get("forecast_day", 0))
            tasks.append(generate_advisory(provider, fc_list, station))
            stations_list.append((fc_list, station))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for (fc_list, station), result in zip(stations_list, results):
            if isinstance(result, Exception):
                result = LocalProvider().generate_advisory(fc_list[0], station)

            alert = {
                "id": str(uuid.uuid4()),
                "station_id": station.station_id,
                "farmer_lat": fc_list[0].get("farmer_lat", station.lat),
                "farmer_lon": fc_list[0].get("farmer_lon", station.lon),
                "issued_at": datetime.now(timezone.utc).isoformat(),
                "condition": fc_list[0].get("condition"),
                "temperature": fc_list[0].get("temperature"),
                "rainfall": fc_list[0].get("rainfall"),
                "forecast_days": len(fc_list),
                **result,
            }
            alerts.append(alert)
        return alerts

    alerts = asyncio.run(_run())

    # Validate via Pydantic
    alerts = [Advisory(**a).model_dump() for a in alerts]

    rag_count = sum(1 for a in alerts if a.get("provider") == "rag_claude")
    context.log.info(f"Generated {len(alerts)} advisories | {rag_count} RAG | {len(alerts)-rag_count} rule-based")
    return alerts
