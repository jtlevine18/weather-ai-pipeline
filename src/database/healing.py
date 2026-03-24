"""CRUD helpers for the healing_log table."""

from __future__ import annotations
from typing import Any, Dict, List

import duckdb

from src.database._util import _rows_to_dicts


def insert_healing_log(conn: duckdb.DuckDBPyConnection, records: List[Dict[str, Any]]) -> None:
    for r in records:
        conn.execute(
            """INSERT OR REPLACE INTO healing_log
               (id, pipeline_run_id, reading_id, station_id, assessment, reasoning,
                corrections, quality_score, tools_used, original_values,
                model, tokens_in, tokens_out, latency_s, fallback_used)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            [r["id"], r.get("pipeline_run_id"), r["reading_id"], r["station_id"],
             r.get("assessment"), r.get("reasoning"), r.get("corrections"),
             r.get("quality_score"), r.get("tools_used"), r.get("original_values"),
             r.get("model"), r.get("tokens_in"), r.get("tokens_out"),
             r.get("latency_s"), r.get("fallback_used", False)],
        )


def get_healing_log(conn: duckdb.DuckDBPyConnection, limit: int = 100) -> List[Dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM healing_log ORDER BY created_at DESC LIMIT ?", [limit]
    ).fetchall()
    return _rows_to_dicts(conn, rows)


def get_healing_log_for_reading(conn: duckdb.DuckDBPyConnection,
                                 reading_id: str) -> List[Dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM healing_log WHERE reading_id = ?", [reading_id]
    ).fetchall()
    return _rows_to_dicts(conn, rows)


def get_healing_stats(conn: duckdb.DuckDBPyConnection) -> Dict[str, Any]:
    """Aggregate healing stats for dashboard display."""
    # Assessment distribution
    dist_rows = conn.execute(
        """SELECT assessment, COUNT(*) as cnt, AVG(quality_score) as avg_q
           FROM healing_log GROUP BY assessment"""
    ).fetchall()
    dist = {r[0]: {"count": r[1], "avg_quality": round(r[2], 3) if r[2] else None}
            for r in dist_rows}

    # Tool usage frequency
    tool_rows = conn.execute(
        """SELECT tools_used FROM healing_log
           WHERE tools_used IS NOT NULL AND tools_used != ''"""
    ).fetchall()
    tool_counts: Dict[str, int] = {}
    for (tools_str,) in tool_rows:
        for t in tools_str.split(","):
            t = t.strip()
            if t:
                tool_counts[t] = tool_counts.get(t, 0) + 1

    # Latest run stats
    latest = conn.execute(
        """SELECT model, tokens_in, tokens_out, latency_s, fallback_used, created_at
           FROM healing_log ORDER BY created_at DESC LIMIT 1"""
    ).fetchall()
    latest_run = None
    if latest:
        r = latest[0]
        latest_run = {
            "model": r[0], "tokens_in": r[1], "tokens_out": r[2],
            "latency_s": r[3], "fallback_used": r[4], "created_at": r[5],
        }

    return {
        "assessment_distribution": dist,
        "tool_usage": tool_counts,
        "latest_run": latest_run,
        "total_assessments": sum(d["count"] for d in dist.values()),
    }
