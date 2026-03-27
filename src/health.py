"""Health-check endpoint for the weather pipeline.

get_health_status() is the core logic (no FastAPI dependency).
The FastAPI app below is kept for backward compatibility; the main
API entry point is now src/api.py.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import FastAPI

STALE_THRESHOLD_SECONDS = 2 * 60 * 60  # 2 hours

KEY_TABLES = [
    "raw_telemetry",
    "clean_telemetry",
    "forecasts",
    "agricultural_alerts",
    "delivery_log",
    "pipeline_runs",
]

_START_TIME = time.monotonic()


def get_health_status(database_url: str = "") -> Dict[str, Any]:
    """Return a dict describing pipeline health.

    Safe to call from Streamlit or any other context.
    """
    from src.database._util import PgConnection, get_database_url

    checks: Dict[str, Any] = {
        "db_accessible": False,
        "pipeline_fresh": False,
        "tables_have_data": False,
    }
    table_counts: Dict[str, int] = {}
    last_run_ts = None
    status = "ok"
    errors: list = []

    try:
        con = PgConnection(database_url or get_database_url())
    except Exception as exc:
        errors.append(f"Cannot connect to PostgreSQL: {exc}")
        return _build_response("degraded", checks, table_counts, last_run_ts, errors)

    try:
        from src.database.safe_sql import safe_table
        for table in KEY_TABLES:
            try:
                row = con.execute(f"SELECT COUNT(*) FROM {safe_table(table)}").fetchone()
                table_counts[table] = row[0] if row else 0
            except Exception:
                table_counts[table] = 0

        checks["db_accessible"] = True

        try:
            row = con.execute(
                "SELECT started_at FROM pipeline_runs "
                "ORDER BY started_at DESC LIMIT 1"
            ).fetchone()
            if row:
                last_run_dt = row[0]
                if last_run_dt.tzinfo is None:
                    last_run_dt = last_run_dt.replace(tzinfo=timezone.utc)
                last_run_ts = last_run_dt.isoformat()
                age = (datetime.now(timezone.utc) - last_run_dt).total_seconds()
                checks["pipeline_fresh"] = age < STALE_THRESHOLD_SECONDS
            else:
                checks["pipeline_fresh"] = False
        except Exception:
            checks["pipeline_fresh"] = False

        checks["tables_have_data"] = all(
            table_counts.get(t, 0) > 0 for t in KEY_TABLES
        )

    finally:
        con.close()

    if not all(checks.values()):
        status = "degraded"

    return _build_response(status, checks, table_counts, last_run_ts, errors)


def _build_response(
    status: str,
    checks: Dict[str, Any],
    table_counts: Dict[str, int],
    last_pipeline_run,
    errors: list,
) -> Dict[str, Any]:
    uptime_seconds = round(time.monotonic() - _START_TIME, 1)
    payload: Dict[str, Any] = {
        "status": status,
        "last_pipeline_run": last_pipeline_run,
        "table_counts": table_counts,
        "checks": checks,
        "uptime_seconds": uptime_seconds,
    }
    if errors:
        payload["errors"] = errors
    return payload


# Backward-compatible standalone app (main API is src/api.py)
app = FastAPI(title="Weather Pipeline Health", docs_url=None, redoc_url=None)


@app.get("/health")
def health() -> Dict[str, Any]:
    return get_health_status()
