"""Dagster asset checks — quality gates visible in the UI."""

from dagster import asset_check, AssetCheckResult, AssetCheckSeverity
from dagster_pipeline.resources import DuckDBResource
from src.quality_checks import check_row_count, check_null_rate, check_value_range


@asset_check(asset="clean_telemetry", description="Verify healed data has at least 10 records")
def check_clean_row_count(duckdb: DuckDBResource) -> AssetCheckResult:
    conn = duckdb.get_connection()
    try:
        passed, msg = check_row_count(conn, "clean_telemetry", 10)
        return AssetCheckResult(
            passed=passed,
            metadata={"detail": msg},
            severity=AssetCheckSeverity.WARN,
        )
    finally:
        conn.close()


@asset_check(asset="clean_telemetry", description="Temperature null rate below 10%")
def check_clean_temp_nulls(duckdb: DuckDBResource) -> AssetCheckResult:
    conn = duckdb.get_connection()
    try:
        passed, msg = check_null_rate(conn, "clean_telemetry", "temperature", 10.0)
        return AssetCheckResult(
            passed=passed,
            metadata={"detail": msg},
            severity=AssetCheckSeverity.WARN,
        )
    finally:
        conn.close()


@asset_check(asset="clean_telemetry", description="Temperature within physical bounds [-10, 55]")
def check_clean_temp_range(duckdb: DuckDBResource) -> AssetCheckResult:
    conn = duckdb.get_connection()
    try:
        passed, msg = check_value_range(conn, "clean_telemetry", "temperature", -10.0, 55.0)
        return AssetCheckResult(
            passed=passed,
            metadata={"detail": msg},
            severity=AssetCheckSeverity.ERROR,
        )
    finally:
        conn.close()


@asset_check(asset="forecasts", description="Confidence scores within [0, 1]")
def check_forecast_confidence(duckdb: DuckDBResource) -> AssetCheckResult:
    conn = duckdb.get_connection()
    try:
        passed, msg = check_value_range(conn, "forecasts", "confidence", 0.0, 1.0)
        return AssetCheckResult(
            passed=passed,
            metadata={"detail": msg},
            severity=AssetCheckSeverity.ERROR,
        )
    finally:
        conn.close()
