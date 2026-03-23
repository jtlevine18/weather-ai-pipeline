"""Step 3: MOS forecasting via Open-Meteo + XGBoost."""

import asyncio
from dagster import asset, AssetExecutionContext, AssetIn
from typing import Any, Dict, List

from config import STATIONS, PipelineConfig
from src.forecasting import create_forecast_model, PersistenceModel, run_forecast_step
from src.models import Forecast
from dagster_pipeline.resources import OpenMeteoResource, NASAPowerResource, DuckDBResource


@asset(
    ins={"clean_telemetry": AssetIn()},
    description="MOS-corrected weather forecasts — NWP baseline + XGBoost correction.",
    group_name="pipeline",
)
def forecasts(
    context: AssetExecutionContext,
    clean_telemetry: List[Dict[str, Any]],
    open_meteo: OpenMeteoResource,
    nasa_power: NASAPowerResource,
    duckdb: DuckDBResource,
) -> List[Dict[str, Any]]:
    config = PipelineConfig()
    forecast_model = create_forecast_model(config.models_dir)
    persistence = PersistenceModel()
    om_client = open_meteo.get_client()
    nasa_client = nasa_power.get_client()

    conn = duckdb.get_connection()
    try:
        from src.database import get_latest_clean_for_station, get_clean_history_for_station

        async def _run():
            tasks = []
            for station in STATIONS:
                obs = get_latest_clean_for_station(conn, station.station_id)
                history = get_clean_history_for_station(conn, station.station_id)
                tasks.append(run_forecast_step(
                    station, obs, om_client, forecast_model, persistence,
                    nasa_client=nasa_client, station_history=history,
                ))
            return await asyncio.gather(*tasks, return_exceptions=True)

        results = asyncio.run(_run())
    finally:
        conn.close()

    forecast_list = []
    mos_count = 0
    for station, result in zip(STATIONS, results):
        if isinstance(result, Exception) or result is None:
            context.log.warning(f"Forecast failed for {station.station_id}: {result}")
            continue
        forecast_list.append(result)
        if result.get("model_used") == "hybrid_mos":
            mos_count += 1

    # Validate via Pydantic
    forecast_list = [Forecast(**f).model_dump() for f in forecast_list]

    context.log.info(f"Generated {len(forecast_list)} forecasts | {mos_count} MOS")
    return forecast_list
