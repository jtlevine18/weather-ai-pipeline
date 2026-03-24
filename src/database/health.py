"""Station health query helpers."""

from __future__ import annotations
from typing import Any, Dict, List

from src.database._util import _rows_to_dicts


def get_station_health(conn: Any) -> List[Dict[str, Any]]:
    rows = conn.execute("""
        SELECT station_id,
               MAX(ts) as last_seen,
               COUNT(*) as record_count,
               AVG(quality_score) as avg_quality
        FROM clean_telemetry
        GROUP BY station_id
    """).fetchall()
    return _rows_to_dicts(conn, rows)
