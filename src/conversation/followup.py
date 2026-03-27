"""
Proactive follow-up scheduling and firing.
Supports time-based, weather-event, and pipeline-run triggers.
"""

from __future__ import annotations
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List


TRIGGER_TYPES = ("time", "weather_event", "pipeline_run")


def schedule_followup(conn, aadhaar_id: str, trigger_type: str,
                      trigger_value: str, message_template: str,
                      session_id: str = "") -> str:
    """Schedule a proactive follow-up. Returns followup ID."""
    fid = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO scheduled_followups
           (id, aadhaar_id, session_id, trigger_type, trigger_value,
            message_template, status, created_at)
           VALUES (?,?,?,?,?,?,?,?)""",
        [fid, aadhaar_id, session_id, trigger_type, trigger_value,
         message_template, "pending", datetime.now(timezone.utc).isoformat()],
    )
    return fid


def check_and_fire(conn, current_time: datetime = None) -> List[Dict[str, Any]]:
    """Return followups that are due. Marks them as fired."""
    now = current_time or datetime.now(timezone.utc)
    due = []

    # Time-based triggers: trigger_value is an ISO timestamp
    rows = conn.execute(
        """SELECT id, aadhaar_id, trigger_type, trigger_value,
                  message_template, session_id
           FROM scheduled_followups
           WHERE status = 'pending' AND trigger_type = 'time'
             AND trigger_value <= ?""",
        [now.isoformat()],
    ).fetchall()

    cols = ["id", "aadhaar_id", "trigger_type", "trigger_value",
            "message_template", "session_id"]
    for row in rows:
        entry = dict(zip(cols, row))
        due.append(entry)
        conn.execute(
            "UPDATE scheduled_followups SET status = 'fired', fired_at = ? WHERE id = ?",
            [now.isoformat(), entry["id"]],
        )

    return due


def get_pending_followups(conn, aadhaar_id: str) -> List[Dict[str, Any]]:
    """Get all pending followups for a farmer (for system prompt injection)."""
    rows = conn.execute(
        """SELECT trigger_type, trigger_value, message_template, created_at
           FROM scheduled_followups
           WHERE aadhaar_id = ? AND status = 'pending'
           ORDER BY created_at DESC""",
        [aadhaar_id],
    ).fetchall()
    cols = ["trigger_type", "trigger_value", "message_template", "created_at"]
    return [dict(zip(cols, r)) for r in rows]


def followups_to_context(followups: List[Dict[str, Any]]) -> str:
    """Format pending followups for system prompt."""
    if not followups:
        return ""
    lines = ["PENDING FOLLOW-UPS for this farmer:"]
    for f in followups:
        created = str(f['created_at'])[:10]
        lines.append(f"  - [{f['trigger_type']}] {f['message_template']} (scheduled: {created})")
    return "\n".join(lines)
