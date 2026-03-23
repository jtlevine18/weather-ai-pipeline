"""FastAPI health-check endpoint for the weather pipeline.

Exposes /health that reports DuckDB connectivity, pipeline freshness,
and table row counts.  The same logic is available via get_health_status()
for programmatic use (e.g. Streamlit sidebar widget).
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

import duckdb
from fastapi import FastAPI

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DB_PATH = Path("weather.duckdb")
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

# ---------------------------------------------------------------------------
# Core logic (no FastAPI dependency)
# ---------------------------------------------------------------------------


def get_health_status(db_path: Path = DB_PATH) -> Dict[str, Any]:
    """Return a dict describing pipeline health.

    Safe to call from Streamlit or any other context — no FastAPI
    objects involved.
    """
    checks: Dict[str, Any] = {
        "db_accessible": False,
        "pipeline_fresh": False,
        "tables_have_data": False,
    }
    table_counts: Dict[str, int] = {}
    last_run_ts: str | None = None
    status = "ok"
    errors: list[str] = []

    # --- DuckDB accessible? ---
    try:
        con = duckdb.connect(str(db_path), read_only=True)
    except Exception as exc:
        errors.append(f"Cannot open DuckDB: {exc}")
        return _build_response("degraded", checks, table_counts, last_run_ts, errors)

    try:
        # --- Table row counts ---
        for table in KEY_TABLES:
            try:
                (count,) = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
                table_counts[table] = count
            except duckdb.CatalogException:
                table_counts[table] = 0

        checks["db_accessible"] = True

        # --- Last pipeline run freshness ---
        try:
            row = con.execute(
                "SELECT started_at FROM pipeline_runs "
                "ORDER BY started_at DESC LIMIT 1"
            ).fetchone()
            if row:
                last_run_dt: datetime = row[0]
                # Normalise to UTC-aware for comparison
                if last_run_dt.tzinfo is None:
                    last_run_dt = last_run_dt.replace(tzinfo=timezone.utc)
                last_run_ts = last_run_dt.isoformat()
                age = (datetime.now(timezone.utc) - last_run_dt).total_seconds()
                checks["pipeline_fresh"] = age < STALE_THRESHOLD_SECONDS
            else:
                checks["pipeline_fresh"] = False
        except duckdb.CatalogException:
            checks["pipeline_fresh"] = False

        # --- Tables have data ---
        checks["tables_have_data"] = all(
            table_counts.get(t, 0) > 0 for t in KEY_TABLES
        )

    finally:
        con.close()

    # --- Overall status ---
    if not all(checks.values()):
        status = "degraded"

    return _build_response(status, checks, table_counts, last_run_ts, errors)


def _build_response(
    status: str,
    checks: Dict[str, Any],
    table_counts: Dict[str, int],
    last_pipeline_run: str | None,
    errors: list[str],
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


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(title="Weather Pipeline Health", docs_url=None, redoc_url=None)


@app.get("/health")
def health() -> Dict[str, Any]:
    return get_health_status()
