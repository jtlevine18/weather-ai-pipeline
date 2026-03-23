"""Step 1: Ingest synthetic telemetry data."""

from dagster import asset, AssetExecutionContext
from typing import Any, Dict, List

from config import STATIONS, PipelineConfig
from src.ingestion import generate_synthetic_reading
from src.models import RawReading


@asset(
    description="Synthetic weather station readings with configurable fault injection.",
    group_name="pipeline",
)
def raw_telemetry(context: AssetExecutionContext) -> List[Dict[str, Any]]:
    config = PipelineConfig()
    readings = []
    for station in STATIONS:
        reading = generate_synthetic_reading(station, config.weather.fault_config)
        readings.append(reading)

    # Validate via Pydantic
    readings = [RawReading(**r).model_dump() for r in readings]

    faults = sum(1 for r in readings if r.get("fault_type"))
    context.log.info(f"Ingested {len(readings)} readings | {faults} faults injected")
    return readings
