"""CRUD helpers for the pipeline_runs table."""

from __future__ import annotations
from typing import Any

from src.database._util import _now


def start_pipeline_run(conn: Any, run_id: str) -> None:
    conn.execute(
        "INSERT INTO pipeline_runs (id, started_at) VALUES (?,?)",
        [run_id, _now()],
    )


def finish_pipeline_run(conn: Any, run_id: str,
                         status: str, steps_ok: int, steps_fail: int,
                         summary: str) -> None:
    conn.execute(
        """UPDATE pipeline_runs
           SET ended_at=?, status=?, steps_ok=?, steps_fail=?, summary=?
           WHERE id=?""",
        [_now(), status, steps_ok, steps_fail, summary, run_id],
    )
