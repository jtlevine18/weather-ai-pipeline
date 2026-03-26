"""
NL (Natural Language) agent — Claude tool-use orchestration.
Allows users to query the pipeline state in natural language.
"""

from __future__ import annotations
import json
import logging
import time
import uuid
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)


TOOLS = [
    {
        "name": "query_forecasts",
        "description": "Get recent weather forecasts for one or all stations",
        "input_schema": {
            "type": "object",
            "properties": {
                "station_id": {"type": "string",
                               "description": "Station ID (e.g. KL_TVM) or 'all'"},
                "limit":      {"type": "integer", "description": "Max records", "default": 10},
            },
            "required": ["station_id"],
        },
    },
    {
        "name": "query_alerts",
        "description": "Get recent agricultural advisories",
        "input_schema": {
            "type": "object",
            "properties": {
                "station_id": {"type": "string", "description": "Station ID or 'all'"},
                "limit":      {"type": "integer", "default": 5},
            },
            "required": ["station_id"],
        },
    },
    {
        "name": "get_station_health",
        "description": "Check health status of all weather stations",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "run_pipeline",
        "description": "Trigger a full pipeline run",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_architecture",
        "description": "Describe the pipeline architecture",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
]


def _execute_tool(tool_name: str, tool_input: Dict[str, Any],
                   config) -> str:
    from src.database import get_recent_forecasts, get_recent_alerts
    from src.monitor  import StationMonitor
    from src.architecture import get_architecture_text
    from src.database._util import PgConnection, get_database_url

    if tool_name == "get_architecture":
        return get_architecture_text()

    if tool_name == "get_station_health":
        monitor = StationMonitor()
        statuses = monitor.check_all()
        return json.dumps(statuses, default=str, indent=2)

    if tool_name == "query_forecasts":
        with PgConnection(get_database_url()) as conn:
            sid   = tool_input.get("station_id", "all")
            limit = tool_input.get("limit", 10)
            rows  = get_recent_forecasts(conn, limit=50)
            if sid != "all":
                rows = [r for r in rows if r.get("station_id") == sid]
            return json.dumps(rows[:limit], default=str, indent=2)

    if tool_name == "query_alerts":
        with PgConnection(get_database_url()) as conn:
            sid   = tool_input.get("station_id", "all")
            limit = tool_input.get("limit", 5)
            rows  = get_recent_alerts(conn, limit=50)
            if sid != "all":
                rows = [r for r in rows if r.get("station_id") == sid]
            return json.dumps(rows[:limit], default=str, indent=2)

    if tool_name == "run_pipeline":
        import asyncio
        from src.pipeline import WeatherPipeline
        pipeline = WeatherPipeline(config)
        try:
            return json.dumps(asyncio.run(pipeline.run()), default=str)
        except Exception as exc:
            return f"Pipeline run failed: {exc}"

    return f"Unknown tool: {tool_name}"


class NLAgent:
    def __init__(self, config):
        self.config = config

    def _log_to_db(self, session_id: str, role: str,
                    content: Optional[str] = None,
                    tool_name: Optional[str] = None,
                    tool_input: Optional[str] = None,
                    tokens_in: Optional[int] = None,
                    tokens_out: Optional[int] = None,
                    latency_ms: Optional[int] = None) -> None:
        try:
            from src.database import insert_conversation_log
            from src.database._util import PgConnection, get_database_url
            with PgConnection(get_database_url()) as conn:
                insert_conversation_log(conn, {
                    "id": str(uuid.uuid4()),
                    "session_id": session_id,
                    "role": role,
                    "content": (content[:2000] if content else None),
                    "tool_name": tool_name,
                    "tool_input": (tool_input[:2000] if tool_input else None),
                    "tokens_in": tokens_in,
                    "tokens_out": tokens_out,
                    "latency_ms": latency_ms,
                })
        except Exception as exc:
            log.debug("Conversation logging failed: %s", exc)

    def chat(self, user_message: str, history: List[Dict] = None,
             session_id: Optional[str] = None) -> str:
        import anthropic
        client = anthropic.Anthropic(api_key=self.config.anthropic_key)

        _session_id = session_id or str(uuid.uuid4())

        messages = list(history or [])
        messages.append({"role": "user", "content": user_message})

        # Log user message
        self._log_to_db(_session_id, "user", content=user_message)

        system = (
            "You are a weather pipeline assistant for Kerala and Tamil Nadu, India. "
            "You help farmers and agronomists understand weather forecasts, "
            "station health, and agricultural advisories. "
            "Use the provided tools to answer questions with real data. "
            "Be concise and helpful."
        )

        while True:
            t0 = time.time()
            response = client.messages.create(
                model=self.config.translation.model,
                max_tokens=1024,
                system=system,
                tools=TOOLS,
                messages=messages,
            )
            latency_ms = int((time.time() - t0) * 1000)
            tokens_in = getattr(response.usage, "input_tokens", None)
            tokens_out = getattr(response.usage, "output_tokens", None)

            if response.stop_reason == "end_turn":
                text_blocks = [b.text for b in response.content
                               if hasattr(b, "text")]
                reply = "\n".join(text_blocks)
                self._log_to_db(_session_id, "assistant",
                                content=reply, tokens_in=tokens_in,
                                tokens_out=tokens_out, latency_ms=latency_ms)
                return reply

            if response.stop_reason == "tool_use":
                messages.append({"role": "assistant", "content": response.content})
                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        self._log_to_db(_session_id, "tool_use",
                                        tool_name=block.name,
                                        tool_input=json.dumps(block.input, default=str),
                                        tokens_in=tokens_in, tokens_out=tokens_out,
                                        latency_ms=latency_ms)
                        result = _execute_tool(
                            block.name, block.input, self.config,
                        )
                        tool_results.append({
                            "type":       "tool_result",
                            "tool_use_id": block.id,
                            "content":     result,
                        })
                        self._log_to_db(_session_id, "tool_result",
                                        tool_name=block.name,
                                        content=(result[:2000] if result else None))
                messages.append({"role": "user", "content": tool_results})
                continue

            break

        return "I'm not sure how to answer that."
