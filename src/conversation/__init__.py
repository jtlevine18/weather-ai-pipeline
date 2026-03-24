"""
ConversationalAgent — wraps NLAgent with farmer context, persistent memory,
state machine, proactive follow-ups, and native language support.
"""

from __future__ import annotations
import json
import logging
import time
import uuid
from typing import Any, Dict, List, Optional

from src.conversation.state_machine import ConversationState, next_state
from src.conversation.language import resolve_language
from src.conversation.prompts import build_system_prompt
from src.conversation.tools import CONVERSATION_TOOLS, execute_conversation_tool

log = logging.getLogger(__name__)


class ConversationalAgent:
    def __init__(self, config):
        self.config = config
        self._farmer_profile = None
        self._state = ConversationState.ONBOARDING
        self._language = "en"
        self._aadhaar_id = None
        self._phone = None

    @property
    def state(self) -> ConversationState:
        return self._state

    @property
    def farmer_profile(self):
        return self._farmer_profile

    async def identify(self, phone: str) -> bool:
        """Identify farmer by phone, assemble profile, transition to ACTIVE."""
        from src.dpi import DPIAgent
        dpi = DPIAgent()
        profile = await dpi.get_or_create_profile(phone)
        if profile is None:
            return False
        self._farmer_profile = profile
        self._aadhaar_id = profile.aadhaar.aadhaar_id
        self._phone = phone
        self._language = profile.aadhaar.language
        self._state = ConversationState.ACTIVE
        self._save_session()
        return True

    def chat(self, user_message: str, history: List[Dict] = None,
             session_id: Optional[str] = None) -> str:
        """Main entry point — state-aware, farmer-aware, language-aware chat."""
        import anthropic
        from src.nl_agent import TOOLS as NL_TOOLS, _execute_tool as nl_execute

        client = anthropic.Anthropic(api_key=self.config.anthropic_key)
        _session_id = session_id or str(uuid.uuid4())

        # Detect language from message
        detected_lang = resolve_language(user_message, self._language)
        self._language = detected_lang

        # Update state
        identity_verified = self._farmer_profile is not None
        self._state = next_state(self._state, user_message, identity_verified)

        # Build context blocks
        farmer_ctx = ""
        memory_ctx = ""
        followup_ctx = ""

        if self._farmer_profile:
            from src.dpi import DPIAgent
            dpi = DPIAgent()
            farmer_ctx = dpi.profile_to_context(self._farmer_profile)

        if self._aadhaar_id:
            try:
                from src.database import init_db
                from src.conversation.memory import build_memory_context
                from src.conversation.followup import get_pending_followups, followups_to_context
                conn = init_db()
                try:
                    memory_ctx = build_memory_context(conn, self._aadhaar_id)
                    followup_ctx = followups_to_context(get_pending_followups(conn, self._aadhaar_id))
                finally:
                    conn.close()
            except Exception as exc:
                log.debug("Context loading failed: %s", exc)

        # Build system prompt
        system = build_system_prompt(
            self._state, farmer_ctx, memory_ctx, followup_ctx, self._language
        )

        # Combine all tools: existing 5 + new 6
        all_tools = list(NL_TOOLS) + list(CONVERSATION_TOOLS)

        messages = list(history or [])
        messages.append({"role": "user", "content": user_message})

        self._log_to_db(_session_id, "user", content=user_message)

        while True:
            t0 = time.time()
            response = client.messages.create(
                model=self.config.translation.model,
                max_tokens=1024,
                system=system,
                tools=all_tools,
                messages=messages,
            )
            latency_ms = int((time.time() - t0) * 1000)
            tokens_in = getattr(response.usage, "input_tokens", None)
            tokens_out = getattr(response.usage, "output_tokens", None)

            if response.stop_reason == "end_turn":
                text_blocks = [b.text for b in response.content if hasattr(b, "text")]
                reply = "\n".join(text_blocks)
                self._log_to_db(_session_id, "assistant",
                                content=reply, tokens_in=tokens_in,
                                tokens_out=tokens_out, latency_ms=latency_ms)
                self._try_extract_memories(client, user_message, reply, _session_id)
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

                        conv_tool_names = {t["name"] for t in CONVERSATION_TOOLS}
                        if block.name in conv_tool_names:
                            result = execute_conversation_tool(
                                block.name, block.input, _session_id
                            )
                        else:
                            result = nl_execute(
                                block.name, block.input, self.config,
                            )

                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result,
                        })
                        self._log_to_db(_session_id, "tool_result",
                                        tool_name=block.name,
                                        content=(result[:2000] if result else None))
                messages.append({"role": "user", "content": tool_results})
                continue

            break

        return "I'm not sure how to answer that."

    def _try_extract_memories(self, client, user_msg: str, reply: str,
                               session_id: str) -> None:
        if not self._aadhaar_id:
            return
        try:
            from src.database import init_db
            from src.conversation.memory import extract_memories, save_memories
            memories = extract_memories(user_msg, reply, client, self.config.translation.model)
            if memories:
                conn = init_db()
                try:
                    save_memories(conn, self._aadhaar_id, session_id, memories)
                finally:
                    conn.close()
        except Exception as exc:
            log.debug("Memory save failed: %s", exc)

    def _save_session(self) -> None:
        try:
            from src.database import init_db
            conn = init_db()
            try:
                conn.execute(
                    """INSERT INTO conversation_sessions
                       (id, aadhaar_id, phone, state, language, context_json, updated_at)
                       VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                    [str(uuid.uuid4()),
                     self._aadhaar_id or "",
                     self._phone or "",
                     self._state.value,
                     self._language,
                     json.dumps({"has_profile": self._farmer_profile is not None}),
                     time.strftime("%Y-%m-%dT%H:%M:%S")],
                )
            finally:
                conn.close()
        except Exception as exc:
            log.debug("Session save failed: %s", exc)

    def _log_to_db(self, session_id: str, role: str,
                    content: Optional[str] = None,
                    tool_name: Optional[str] = None,
                    tool_input: Optional[str] = None,
                    tokens_in: Optional[int] = None,
                    tokens_out: Optional[int] = None,
                    latency_ms: Optional[int] = None) -> None:
        try:
            from src.database import init_db, insert_conversation_log
            conn = init_db()
            try:
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
            finally:
                conn.close()
        except Exception as exc:
            log.debug("Conversation logging failed: %s", exc)
