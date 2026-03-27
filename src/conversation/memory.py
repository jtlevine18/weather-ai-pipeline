"""
Persistent cross-session conversation memory.
After each turn, extracts structured memories; on each turn, recalls recent context.
"""

from __future__ import annotations
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)


MEMORY_TYPES = ("topic", "action_taken", "advisory_given", "followup_needed", "farmer_reported")


def extract_memories(user_message: str, assistant_reply: str,
                     client, model: str) -> List[Dict[str, Any]]:
    """Lightweight Claude call to extract structured memories from a conversation turn."""
    try:
        response = client.messages.create(
            model=model,
            max_tokens=512,
            system=(
                "Extract structured memories from this conversation turn. "
                "Return a JSON array of objects with keys: type, content, expires_days. "
                "Types: topic (what was discussed), action_taken (advice given that farmer acted on), "
                "advisory_given (specific advisory), followup_needed (something to check later), "
                "farmer_reported (farmer shared info about their situation). "
                "expires_days: null for permanent, or integer days until irrelevant. "
                "Return [] if nothing worth remembering. Only return the JSON array, no other text."
            ),
            messages=[{"role": "user", "content": (
                f"User said: {user_message[:500]}\n"
                f"Assistant replied: {assistant_reply[:500]}"
            )}],
        )
        text = response.content[0].text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0]
        memories = json.loads(text)
        if not isinstance(memories, list):
            return []
        return memories
    except Exception as exc:
        log.debug("Memory extraction failed: %s", exc)
        return []


def save_memories(conn, aadhaar_id: str, session_id: str,
                  memories: List[Dict[str, Any]]) -> None:
    """Persist extracted memories to conversation_memory table."""
    now = datetime.now(timezone.utc).isoformat()
    for mem in memories:
        expires_at = None
        if mem.get("expires_days"):
            expires_at = (datetime.now(timezone.utc) + timedelta(days=mem["expires_days"])).isoformat()
        conn.execute(
            """INSERT INTO conversation_memory
               (id, aadhaar_id, session_id, memory_type, content, expires_at, created_at)
               VALUES (?,?,?,?,?,?,?)
               ON CONFLICT (id) DO UPDATE SET
                 content = EXCLUDED.content,
                 expires_at = EXCLUDED.expires_at""",
            [str(uuid.uuid4()), aadhaar_id, session_id,
             mem.get("type", "topic"), mem.get("content", ""),
             expires_at, now],
        )


def build_memory_context(conn, aadhaar_id: str, limit: int = 20) -> str:
    """Assemble recent memories into text for system prompt injection."""
    try:
        rows = conn.execute(
            """SELECT memory_type, content, created_at FROM conversation_memory
               WHERE aadhaar_id = ?
                 AND (expires_at IS NULL OR expires_at > ?)
               ORDER BY created_at DESC LIMIT ?""",
            [aadhaar_id, datetime.now(timezone.utc).isoformat(), limit],
        ).fetchall()
    except Exception:
        return ""

    if not rows:
        return ""

    lines = ["CONVERSATION MEMORY (recent interactions with this farmer):"]
    for memory_type, content, created_at in rows:
        lines.append(f"  [{memory_type}] {content} ({str(created_at)[:10]})")
    return "\n".join(lines)
