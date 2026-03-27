"""SQL identifier validation — prevents SQL injection via table/column names.

All table and column names used in dynamic SQL must pass through safe_table()
or safe_column() before interpolation. These functions validate against a
known allowlist rather than using parameterized queries (SQL does not support
parameterized identifiers).
"""

from __future__ import annotations

VALID_TABLES: frozenset[str] = frozenset({
    "raw_telemetry",
    "clean_telemetry",
    "healing_log",
    "forecasts",
    "agricultural_alerts",
    "delivery_log",
    "delivery_metrics",
    "pipeline_runs",
    "conversation_log",
    "conversation_sessions",
    "conversation_memory",
    "scheduled_followups",
    "feedback_responses",
    "farmer_profiles",
    "farmer_land_records",
    "farmer_soil_health",
    "users",
})

VALID_COLUMNS: frozenset[str] = frozenset({
    # telemetry
    "temperature", "humidity", "rainfall", "wind_speed", "pressure",
    "quality_score", "ts", "created_at",
    # forecasts
    "confidence", "forecast_time", "issued_at",
    # alerts
    "generated_at",
    # pipeline
    "started_at", "finished_at",
    # delivery
    "sent_at",
})


def safe_table(name: str) -> str:
    """Return *name* unchanged if it is a known table, else raise ValueError."""
    if name not in VALID_TABLES:
        raise ValueError(f"Unknown table: {name!r}")
    return name


def safe_column(name: str) -> str:
    """Return *name* unchanged if it is a known column, else raise ValueError."""
    if name not in VALID_COLUMNS:
        raise ValueError(f"Unknown column: {name!r}")
    return name
