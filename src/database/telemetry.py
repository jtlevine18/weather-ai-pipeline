"""CRUD helpers for raw_telemetry and clean_telemetry tables."""

from __future__ import annotations
from typing import Any, Dict, List, Optional

from src.database._util import _rows_to_dicts


def insert_raw_telemetry(conn: Any, records: List[Dict[str, Any]]) -> None:
    for r in records:
        conn.execute(
            """INSERT INTO raw_telemetry
               (id, station_id, ts, temperature, humidity, wind_speed, wind_dir,
                pressure, rainfall, fault_type, source)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT (id) DO NOTHING""",
            [r["id"], r["station_id"], r["ts"],
             r.get("temperature"), r.get("humidity"), r.get("wind_speed"),
             r.get("wind_dir"), r.get("pressure"), r.get("rainfall"),
             r.get("fault_type"), r.get("source", "synthetic")],
        )


def insert_clean_telemetry(conn: Any, records: List[Dict[str, Any]]) -> None:
    for r in records:
        conn.execute(
            """INSERT INTO clean_telemetry
               (id, station_id, ts, temperature, humidity, wind_speed, wind_dir,
                pressure, rainfall, heal_action, heal_source, quality_score)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT (id) DO NOTHING""",
            [r["id"], r["station_id"], r["ts"],
             r.get("temperature"), r.get("humidity"), r.get("wind_speed"),
             r.get("wind_dir"), r.get("pressure"), r.get("rainfall"),
             r.get("heal_action", "none"), r.get("heal_source", "original"),
             r.get("quality_score", 1.0)],
        )


def get_latest_clean_for_station(conn: Any,
                                  station_id: str) -> Optional[Dict[str, Any]]:
    rows = conn.execute(
        """SELECT * FROM clean_telemetry WHERE station_id=?
           ORDER BY ts DESC LIMIT 1""",
        [station_id],
    ).fetchall()
    result = _rows_to_dicts(conn, rows)
    return result[0] if result else None


def get_all_clean_telemetry(conn: Any) -> List[Dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM clean_telemetry ORDER BY ts DESC LIMIT 500"
    ).fetchall()
    return _rows_to_dicts(conn, rows)


def get_clean_history_for_station(conn: Any,
                                   station_id: str,
                                   limit: int = 200) -> List[Dict[str, Any]]:
    """Return all clean_telemetry rows for a station, oldest first."""
    rows = conn.execute(
        """SELECT * FROM clean_telemetry WHERE station_id=?
           ORDER BY ts ASC LIMIT ?""",
        [station_id, limit],
    ).fetchall()
    return _rows_to_dicts(conn, rows)


def get_paired_raw_clean(conn: Any,
                          limit: int = 500) -> List[Dict[str, Any]]:
    """Join raw_telemetry with clean_telemetry for healing evaluation."""
    rows = conn.execute("""
        SELECT r.id, r.station_id, r.ts,
               r.temperature AS raw_temp, r.humidity AS raw_humidity,
               r.wind_speed AS raw_wind, r.pressure AS raw_pressure,
               r.rainfall AS raw_rainfall,
               r.fault_type,
               c.temperature AS clean_temp, c.humidity AS clean_humidity,
               c.wind_speed AS clean_wind, c.pressure AS clean_pressure,
               c.rainfall AS clean_rainfall,
               c.heal_action, c.heal_source, c.quality_score
        FROM raw_telemetry r
        LEFT JOIN clean_telemetry c ON r.id = c.id
        ORDER BY r.ts DESC
        LIMIT ?
    """, [limit]).fetchall()
    return _rows_to_dicts(conn, rows)
