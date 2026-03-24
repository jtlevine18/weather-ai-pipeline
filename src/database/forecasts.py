"""CRUD helpers for the forecasts table."""

from __future__ import annotations
from typing import Any, Dict, List

from src.database._util import _rows_to_dicts


def insert_forecast(conn: Any, record: Dict[str, Any]) -> None:
    conn.execute(
        """INSERT INTO forecasts
           (id, station_id, issued_at, valid_for_ts, temperature, humidity,
            wind_speed, rainfall, condition, model_used, nwp_source, nwp_temp,
            correction, confidence)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT (id) DO NOTHING""",
        [record["id"], record["station_id"], record["issued_at"], record["valid_for_ts"],
         record.get("temperature"), record.get("humidity"), record.get("wind_speed"),
         record.get("rainfall"), record.get("condition", "clear"),
         record.get("model_used", "persistence"),
         record.get("nwp_source", "open_meteo"),
         record.get("nwp_temp"), record.get("correction", 0.0),
         record.get("confidence", 0.7)],
    )


def get_recent_forecasts(conn: Any,
                          limit: int = 100) -> List[Dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM forecasts ORDER BY issued_at DESC LIMIT ?", [limit]
    ).fetchall()
    return _rows_to_dicts(conn, rows)


def get_forecast_actuals(conn: Any,
                          limit: int = 1000) -> tuple:
    """Get forecasts and clean_telemetry separately for accuracy eval."""
    rows = conn.execute(
        "SELECT * FROM forecasts ORDER BY issued_at DESC LIMIT ?", [limit]
    ).fetchall()
    forecasts = _rows_to_dicts(conn, rows)
    if not forecasts:
        return [], []

    rows2 = conn.execute(
        "SELECT * FROM clean_telemetry ORDER BY ts DESC LIMIT ?", [limit * 2]
    ).fetchall()
    actuals = _rows_to_dicts(conn, rows2)
    return forecasts, actuals
