"""Dagster schedules — replaces APScheduler for orchestrated runs."""

from dagster import ScheduleDefinition, DefaultScheduleStatus
from dagster_pipeline.assets import (
    raw_telemetry, clean_telemetry, forecasts,
    downscaled_forecasts, agricultural_alerts, delivery_log,
)


# Run the full pipeline every hour
hourly_pipeline_schedule = ScheduleDefinition(
    name="hourly_pipeline",
    target=[
        raw_telemetry, clean_telemetry, forecasts,
        downscaled_forecasts, agricultural_alerts, delivery_log,
    ],
    cron_schedule="0 * * * *",  # Every hour at minute 0
    default_status=DefaultScheduleStatus.STOPPED,  # Start manually
)
