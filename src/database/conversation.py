"""CRUD helpers for the conversation_log table."""

from __future__ import annotations
from typing import Any, Dict

import duckdb


def insert_conversation_log(conn: duckdb.DuckDBPyConnection,
                             record: Dict[str, Any]) -> None:
    conn.execute(
        """INSERT OR REPLACE INTO conversation_log
           (id, session_id, role, content, tool_name, tool_input,
            tokens_in, tokens_out, latency_ms)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        [record["id"], record["session_id"], record["role"],
         record.get("content"), record.get("tool_name"),
         record.get("tool_input"), record.get("tokens_in"),
         record.get("tokens_out"), record.get("latency_ms")],
    )
