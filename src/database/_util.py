"""Shared helpers for database submodules."""

from __future__ import annotations
from datetime import datetime
from typing import Any, Dict, List

import duckdb


def _now() -> str:
    return datetime.utcnow().isoformat()


def _rows_to_dicts(conn: duckdb.DuckDBPyConnection, rows: list) -> List[Dict[str, Any]]:
    """Convert DuckDB fetchall() result to list of dicts using cursor description."""
    if not rows:
        return []
    cols = [d[0] for d in conn.description]
    return [dict(zip(cols, r)) for r in rows]
