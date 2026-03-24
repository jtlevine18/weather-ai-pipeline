"""CRUD helpers for the agricultural_alerts table."""

from __future__ import annotations
from typing import Any, Dict, List

from src.database._util import _rows_to_dicts


def insert_alert(conn: Any, record: Dict[str, Any]) -> None:
    conn.execute(
        """INSERT INTO agricultural_alerts
           (id, station_id, farmer_lat, farmer_lon, issued_at, condition,
            advisory_en, advisory_local, language, provider, retrieval_docs,
            forecast_days)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT (id) DO NOTHING""",
        [record["id"], record["station_id"],
         record.get("farmer_lat"), record.get("farmer_lon"),
         record["issued_at"], record.get("condition"),
         record.get("advisory_en"), record.get("advisory_local"),
         record.get("language", "en"), record.get("provider", "unknown"),
         record.get("retrieval_docs", 0),
         record.get("forecast_days", 1)],
    )


def get_recent_alerts(conn: Any,
                       limit: int = 50) -> List[Dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM agricultural_alerts ORDER BY issued_at DESC LIMIT ?", [limit]
    ).fetchall()
    return _rows_to_dicts(conn, rows)
