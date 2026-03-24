"""Shared helpers for database submodules.

Provides PgConnection — a thin wrapper around psycopg2 that preserves
the conn.execute(sql, params).fetchall() pattern used throughout the codebase.
"""

from __future__ import annotations
import os
from datetime import datetime
from typing import Any, Dict, List, Optional


def _now() -> str:
    return datetime.utcnow().isoformat()


def get_database_url() -> str:
    """Return DATABASE_URL from environment, or raise with setup instructions."""
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        raise RuntimeError(
            "DATABASE_URL not set. Export your Neon connection string:\n"
            "  export DATABASE_URL='postgresql://user:pass@ep-xxx.region.aws.neon.tech/neondb?sslmode=require'"
        )
    return url


class PgConnection:
    """Wraps psycopg2 connection to mimic DuckDB's conn.execute() one-liner.

    DuckDB:    rows = conn.execute(sql, [p1, p2]).fetchall()
    Postgres:  rows = conn.execute(sql, [p1, p2]).fetchall()  # same API
    """

    def __init__(self, dsn: str):
        import psycopg2
        self._conn = psycopg2.connect(dsn)
        self._conn.autocommit = True
        self._last_cur: Optional[Any] = None

    def execute(self, sql: str, params=None):
        """Execute SQL, converting ? placeholders to %s for psycopg2."""
        cur = self._conn.cursor()
        if params is not None:
            sql = sql.replace("?", "%s")
            cur.execute(sql, params)
        else:
            cur.execute(sql)
        self._last_cur = cur
        return cur

    @property
    def description(self):
        """Column metadata from last execute() — used by _rows_to_dicts."""
        return self._last_cur.description if self._last_cur else None

    @property
    def raw(self):
        """Underlying psycopg2 connection (for pd.read_sql)."""
        return self._conn

    def close(self):
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def _rows_to_dicts(conn, rows: list) -> List[Dict[str, Any]]:
    """Convert fetchall() result to list of dicts using cursor description."""
    if not rows:
        return []
    desc = conn.description
    if desc is None:
        return []
    cols = [d[0] for d in desc]
    return [dict(zip(cols, r)) for r in rows]
