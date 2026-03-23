"""Dagster assets — one per pipeline stage."""

from dagster_pipeline.assets.ingest import raw_telemetry
from dagster_pipeline.assets.heal import clean_telemetry
from dagster_pipeline.assets.forecast import forecasts
from dagster_pipeline.assets.downscale import downscaled_forecasts
from dagster_pipeline.assets.translate import agricultural_alerts
from dagster_pipeline.assets.deliver import delivery_log
