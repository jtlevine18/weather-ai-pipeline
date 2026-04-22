"""Shared helpers for database submodules.

Provides PgConnection — a thin wrapper around psycopg2 that preserves
the conn.execute(sql, params).fetchall() pattern used throughout the codebase.
Uses SimpleConnectionPool to reuse connections instead of creating new ones each time.
"""

from __future__ import annotations
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from psycopg2.pool import SimpleConnectionPool


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_database_url() -> str:
    """Return DATABASE_URL from environment, or raise with setup instructions."""
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        raise RuntimeError(
            "DATABASE_URL not set. Export your Neon connection string:\n"
            "  export DATABASE_URL='postgresql://user:pass@ep-xxx.region.aws.neon.tech/neondb?sslmode=require'"
        )
    return url


_pool = None


def _get_pool(dsn: str) -> SimpleConnectionPool:
    global _pool
    if _pool is None or _pool.closed:
        _pool = SimpleConnectionPool(minconn=2, maxconn=10, dsn=dsn)
    return _pool


class PgConnection:
    """Thin psycopg2 wrapper providing conn.execute(sql, params).fetchall() pattern.

    Converts ? placeholders to %s for psycopg2 compatibility.
    """

    def __init__(self, dsn: str):
        pool = _get_pool(dsn)
        # Validate on acquire: the pool may hold connections Neon closed
        # server-side during idle. getconn() returns them without checking,
        # and the first real query fails with "SSL connection has been closed
        # unexpectedly". Cycle up to 3 times to skip dead conns.
        last_exc: Optional[BaseException] = None
        for _ in range(3):
            conn = pool.getconn()
            try:
                conn.autocommit = True
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    cur.fetchone()
                self._conn = conn
                self._pool = pool
                self._last_cur: Optional[Any] = None
                return
            except Exception as exc:
                last_exc = exc
                try:
                    pool.putconn(conn, close=True)
                except Exception:
                    pass
        raise RuntimeError(
            f"Could not acquire a healthy DB connection after 3 attempts: {last_exc}"
        )

    def _refresh_conn(self) -> None:
        """Swap in a fresh connection from the pool on stale-socket errors.

        Neon auto-suspends idle connections; a long GPU step (e.g. 6-min
        GraphCast inference) leaves the pooled conn's TCP socket dead.
        The next .execute() raises ``OperationalError: SSL connection has
        been closed unexpectedly``. We return the dead conn to the pool
        with close=True, grab a new one, and validate with SELECT 1.
        """
        last_exc: Optional[BaseException] = None
        for _ in range(3):
            try:
                self._pool.putconn(self._conn, close=True)
            except Exception:
                pass
            try:
                new_conn = self._pool.getconn()
                new_conn.autocommit = True
                with new_conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    cur.fetchone()
                self._conn = new_conn
                self._last_cur = None
                return
            except Exception as exc:
                last_exc = exc
        raise RuntimeError(
            f"Could not refresh DB connection after 3 attempts: {last_exc}"
        )

    def execute(self, sql: str, params=None):
        """Execute SQL, converting ? placeholders to %s for psycopg2.

        If the socket is dead (Neon idle-suspend during long GPU step),
        refresh the connection and retry once.
        """
        if params is not None:
            sql = sql.replace("?", "%s")

        def _run():
            cur = self._conn.cursor()
            if params is not None:
                cur.execute(sql, params)
            else:
                cur.execute(sql)
            return cur

        try:
            cur = _run()
        except Exception as first_exc:
            import psycopg2
            # Only retry on connection-level failures, not on syntax/data errors.
            if not isinstance(first_exc, (psycopg2.OperationalError, psycopg2.InterfaceError)):
                raise
            self._refresh_conn()
            cur = _run()

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
        if self._pool and self._conn:
            self._pool.putconn(self._conn)
            self._conn = None

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
