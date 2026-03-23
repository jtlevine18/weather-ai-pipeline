"""Step 2: Heal anomalies via cross-validation."""

import asyncio
from dagster import asset, AssetExecutionContext, AssetIn
from typing import Any, Dict, List

from config import STATION_MAP
from src.healing import RuleBasedFallback
from src.models import CleanReading
from dagster_pipeline.resources import TomorrowIOResource, NASAPowerResource


async def _heal_async(
    raw_readings: List[Dict[str, Any]],
    tomorrow_io_client,
    nasa_client,
) -> List[Dict[str, Any]]:
    """Async healing logic — reuses the same algorithm as pipeline.py."""
    rule_healer = RuleBasedFallback()
    clean = []

    # Fetch references
    references: Dict[str, Any] = {}
    station_ids = [r["station_id"] for r in raw_readings if r["station_id"] in STATION_MAP]
    batch_size = 3
    for i in range(0, len(station_ids), batch_size):
        batch = station_ids[i:i + batch_size]
        results = await asyncio.gather(*[
            tomorrow_io_client.get_current(STATION_MAP[sid].lat, STATION_MAP[sid].lon)
            for sid in batch
        ], return_exceptions=True)
        for sid, res in zip(batch, results):
            references[sid] = res if isinstance(res, dict) else None
        if i + batch_size < len(station_ids):
            await asyncio.sleep(1.0)

    for reading in raw_readings:
        ref = references.get(reading["station_id"])
        fault = reading.get("fault_type")

        # Phase 1: Fault-based healing (synthetic faults only)
        if fault is not None:
            healed = rule_healer.heal(reading, ref)
            if healed is None:
                station = STATION_MAP.get(reading["station_id"])
                if station:
                    nasa_ref = await nasa_client.get_current(station.lat, station.lon)
                    if nasa_ref:
                        healed = rule_healer.heal(reading, nasa_ref)
                        ref = ref or nasa_ref
                if healed is None:
                    continue
        else:
            healed = dict(reading)

        # Phase 2+3: Cross-validate against reference (all readings)
        if ref is not None:
            healed = rule_healer.cross_validate(healed, ref)
        else:
            station = STATION_MAP.get(reading["station_id"])
            if station and fault is None:
                nasa_ref = await nasa_client.get_current(station.lat, station.lon)
                if nasa_ref:
                    healed = rule_healer.cross_validate(healed, nasa_ref)
            if "quality_score" not in healed:
                healed["heal_action"] = healed.get("heal_action", "none")
                healed["heal_source"] = healed.get("heal_source", "original")
                null_count = sum(1 for f in ["temperature", "humidity", "wind_speed", "pressure", "rainfall"]
                                 if healed.get(f) is None)
                healed["quality_score"] = max(0.5, 1.0 - null_count * 0.1)

        if "id" not in healed:
            healed["id"] = reading.get("id", "unknown")
        clean.append(healed)

    return clean


@asset(
    ins={"raw_telemetry": AssetIn()},
    description="Healed telemetry with quality scores — anomalies corrected via Tomorrow.io/NASA POWER.",
    group_name="pipeline",
)
def clean_telemetry(
    context: AssetExecutionContext,
    raw_telemetry: List[Dict[str, Any]],
    tomorrow_io: TomorrowIOResource,
    nasa_power: NASAPowerResource,
) -> List[Dict[str, Any]]:
    clean = asyncio.run(_heal_async(
        raw_telemetry,
        tomorrow_io.get_client(),
        nasa_power.get_client(),
    ))

    # Validate via Pydantic
    clean = [CleanReading(**r).model_dump() for r in clean]

    healed = sum(1 for r in clean if r.get("heal_action") != "none")
    context.log.info(f"Healed {len(clean)} records | {healed} corrected")
    return clean
