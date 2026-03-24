"""Step 3: MOS forecasting — NeuralGCM primary, Open-Meteo fallback, XGBoost MOS."""

import asyncio
import logging
from dagster import asset, AssetExecutionContext, AssetIn
from typing import Any, Dict, List

from config import STATIONS, PipelineConfig
from src.forecasting import create_forecast_model, PersistenceModel, run_forecast_step
from src.models import Forecast
from src.database import get_latest_clean_for_station, get_clean_history_for_station
from dagster_pipeline.resources import OpenMeteoResource, NASAPowerResource, DuckDBResource

log = logging.getLogger(__name__)


@asset(
    ins={"clean_telemetry": AssetIn()},
    description="MOS-corrected weather forecasts — NeuralGCM or Open-Meteo NWP + XGBoost correction.",
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

    # Try NeuralGCM batch first
    neuralgcm_nwp: Dict[str, List[Dict[str, Any]]] = {}
    try:
        from src.neuralgcm_client import NeuralGCMClient, is_neuralgcm_available
        if config.neuralgcm.enabled and is_neuralgcm_available():
            ngcm = NeuralGCMClient(
                model_name=config.neuralgcm.model_name,
                forecast_hours=config.neuralgcm.forecast_hours,
            )
            ngcm_result, ngcm_meta = asyncio.run(ngcm.get_forecasts_batch(STATIONS))
            neuralgcm_nwp = ngcm_result
            context.log.info(
                f"NeuralGCM: {ngcm_meta.stations_extracted} stations | "
                f"inference={ngcm_meta.inference_time_s}s"
            )
    except Exception as e:
        context.log.warning(f"NeuralGCM failed, using Open-Meteo: {e}")

    conn = duckdb.get_connection()
    try:
        async def _run():
            tasks = []
            for station in STATIONS:
                obs = get_latest_clean_for_station(conn, station.station_id)
                history = get_clean_history_for_station(conn, station.station_id)
                precomputed = neuralgcm_nwp.get(station.station_id)
                tasks.append(run_forecast_step(
                    station, obs, om_client, forecast_model, persistence,
                    nasa_client=nasa_client, station_history=history,
                    precomputed_nwp=precomputed,
                ))
            return await asyncio.gather(*tasks, return_exceptions=True)

        results = asyncio.run(_run())
    finally:
        conn.close()

    forecast_list = []
    ngcm_count = 0
    mos_count = 0
    for station, result in zip(STATIONS, results):
        if isinstance(result, Exception):
            context.log.warning(f"Forecast failed for {station.station_id}: {result}")
            continue
        # run_forecast_step now returns List[Dict] (7 daily forecasts)
        if not result:
            continue
        fc_list = result if isinstance(result, list) else [result]
        for fc in fc_list:
            forecast_list.append(fc)
            if fc.get("nwp_source") == "neuralgcm":
                ngcm_count += 1
            if "mos" in fc.get("model_used", ""):
                mos_count += 1

    # Validate via Pydantic
    forecast_list = [Forecast(**f).model_dump() for f in forecast_list]

    n_stations = len(set(f["station_id"] for f in forecast_list))
    nwp_summary = (f"{ngcm_count} NeuralGCM + {len(forecast_list) - ngcm_count} Open-Meteo"
                   if ngcm_count else f"{len(forecast_list)} Open-Meteo")
    context.log.info(f"Generated {len(forecast_list)} daily forecasts ({n_stations} stations) | {nwp_summary} | {mos_count} MOS")
    return forecast_list
