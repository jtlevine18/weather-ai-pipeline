"""Step 5: Generate bilingual agricultural advisories."""

import asyncio
import uuid
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

        for forecast in downscaled_forecasts:
            station = STATION_MAP.get(forecast["station_id"])
            if station is None:
                continue
            tasks.append(generate_advisory(provider, forecast, station))
            stations_list.append((forecast, station))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for (forecast, station), result in zip(stations_list, results):
            if isinstance(result, Exception):
                result = LocalProvider().generate_advisory(forecast, station)

            alert = {
                "id": str(uuid.uuid4()),
                "station_id": station.station_id,
                "farmer_lat": forecast.get("farmer_lat", station.lat),
                "farmer_lon": forecast.get("farmer_lon", station.lon),
                "issued_at": datetime.now(timezone.utc).isoformat(),
                "condition": forecast.get("condition"),
                "temperature": forecast.get("temperature"),
                "rainfall": forecast.get("rainfall"),
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
