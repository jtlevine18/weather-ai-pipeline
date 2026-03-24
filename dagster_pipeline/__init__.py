"""
Dagster definitions — registers all assets, resources, schedules, sensors, and checks.

Run locally with:
    dagster dev -f dagster_pipeline/__init__.py
"""

import os
from dagster import Definitions

from dagster_pipeline.assets import (
    raw_telemetry, clean_telemetry, forecasts,
    downscaled_forecasts, agricultural_alerts, delivery_log,
)
from dagster_pipeline.resources import (
    PostgresResource, TomorrowIOResource, OpenMeteoResource,
    NASAPowerResource, AnthropicResource,
)
from dagster_pipeline.io_manager import postgres_io_manager
from dagster_pipeline.schedules import hourly_pipeline_schedule
from dagster_pipeline.checks import (
    check_clean_row_count, check_clean_temp_nulls,
    check_clean_temp_range, check_forecast_confidence,
)
from dagster_pipeline.sensors import forecast_complete_sensor
from dagster_pipeline.hooks import pipeline_success_hook, pipeline_failure_hook  # noqa: F401

# NOTE: Dagster hooks (pipeline_success_hook, pipeline_failure_hook) are
# applied per-asset via @asset(op_tags=...) or via @graph, not in Definitions().
# They are imported here so they are available for individual asset decoration.


defs = Definitions(
    assets=[
        raw_telemetry,
        clean_telemetry,
        forecasts,
        downscaled_forecasts,
        agricultural_alerts,
        delivery_log,
    ],
    asset_checks=[
        check_clean_row_count,
        check_clean_temp_nulls,
        check_clean_temp_range,
        check_forecast_confidence,
    ],
    resources={
        "postgres": PostgresResource(database_url=os.getenv("DATABASE_URL", "")),
        "postgres_io": postgres_io_manager,
        "tomorrow_io": TomorrowIOResource(
            api_key=os.getenv("TOMORROW_IO_API_KEY", ""),
        ),
        "open_meteo": OpenMeteoResource(),
        "nasa_power": NASAPowerResource(),
        "anthropic": AnthropicResource(
            api_key=os.getenv("ANTHROPIC_API_KEY", ""),
        ),
    },
    schedules=[hourly_pipeline_schedule],
    sensors=[forecast_complete_sensor],
)
