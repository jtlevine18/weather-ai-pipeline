"""Tests for the conversation engine (state machine, language, memory, tools)."""

import pytest


def test_state_machine_transitions():
    from src.conversation.state_machine import (
        ConversationState, can_transition, transition, next_state,
    )
    # Valid transitions
    assert can_transition(ConversationState.ONBOARDING, ConversationState.ACTIVE)
    assert can_transition(ConversationState.ACTIVE, ConversationState.ESCALATED)
    assert can_transition(ConversationState.ESCALATED, ConversationState.ACTIVE)
    assert can_transition(ConversationState.ACTIVE, ConversationState.CLOSED)

    # Invalid transitions
    assert not can_transition(ConversationState.CLOSED, ConversationState.ACTIVE)
    assert not can_transition(ConversationState.ONBOARDING, ConversationState.ESCALATED)

    # Next state logic
    assert next_state(ConversationState.ONBOARDING, "hello", identity_verified=True) == ConversationState.ACTIVE
    assert next_state(ConversationState.ONBOARDING, "hello", identity_verified=False) == ConversationState.ONBOARDING
    assert next_state(ConversationState.ACTIVE, "normal question") == ConversationState.ACTIVE
    assert next_state(ConversationState.ACTIVE, "my crop loss is severe") == ConversationState.ESCALATED


def test_language_detection():
    from src.conversation.language import detect_language, resolve_language

    # English
    assert detect_language("What is the weather today?") == "en"

    # Tamil
    assert detect_language("\u0ba8\u0bbe\u0bb3\u0bc8 \u0bb5\u0bbe\u0ba9\u0bbf\u0bb2\u0bc8 \u0b8e\u0ba9\u0bcd\u0ba9?") == "ta"

    # Malayalam
    assert detect_language("\u0d07\u0d28\u0d4d\u0d28\u0d24\u0d4d\u0d24\u0d46 \u0d15\u0d3e\u0d32\u0d3e\u0d35\u0d38\u0d4d\u0d25 \u0d0e\u0d28\u0d4d\u0d24\u0d3e\u0d23\u0d4d?") == "ml"

    # Profile language takes priority
    assert resolve_language("hello", "ta") == "ta"
    assert resolve_language("hello", "ml") == "ml"
    assert resolve_language("hello", "") == "en"


def test_prompts():
    from src.conversation.state_machine import ConversationState
    from src.conversation.prompts import build_system_prompt

    # Onboarding prompt
    prompt = build_system_prompt(ConversationState.ONBOARDING)
    assert "ONBOARDING" in prompt
    assert "identity" in prompt.lower()

    # Active prompt with farmer context
    prompt = build_system_prompt(
        ConversationState.ACTIVE,
        farmer_context="FARMER PROFILE: Test Farmer",
        language="ta",
    )
    assert "ACTIVE" in prompt
    assert "Tamil" in prompt
    assert "Test Farmer" in prompt

    # Escalated prompt
    prompt = build_system_prompt(ConversationState.ESCALATED)
    assert "ESCALATED" in prompt
    assert "empathy" in prompt.lower()


def test_conversation_tools_definition():
    from src.conversation.tools import CONVERSATION_TOOLS
    assert len(CONVERSATION_TOOLS) == 6
    names = {t["name"] for t in CONVERSATION_TOOLS}
    expected = {
        "lookup_farmer_profile", "get_soil_health", "get_insurance_status",
        "get_subsidy_history", "get_personalized_advisory", "schedule_followup",
    }
    assert names == expected, f"Missing tools: {expected - names}"


def test_tool_execution_soil():
    from src.conversation.tools import execute_conversation_tool
    from src.dpi.simulator import get_registry
    import json

    reg = get_registry()
    farmers = reg.list_farmers()
    phone = farmers[0]["phone"]
    profile = reg.lookup_by_phone(phone)
    aadhaar_id = profile.aadhaar.aadhaar_id

    result = execute_conversation_tool("get_soil_health", {"aadhaar_id": aadhaar_id}, "weather.duckdb")
    data = json.loads(result)
    assert "pH" in data
    assert "nitrogen_kg_ha" in data


def test_tool_execution_insurance():
    from src.conversation.tools import execute_conversation_tool
    from src.dpi.simulator import get_registry
    import json

    reg = get_registry()
    farmers = reg.list_farmers()
    profile = reg.lookup_by_phone(farmers[0]["phone"])

    result = execute_conversation_tool("get_insurance_status", {"aadhaar_id": profile.aadhaar.aadhaar_id}, "weather.duckdb")
    data = json.loads(result)
    assert "status" in data
    assert "insured_crops" in data


def test_tool_execution_subsidy():
    from src.conversation.tools import execute_conversation_tool
    from src.dpi.simulator import get_registry
    import json

    reg = get_registry()
    farmers = reg.list_farmers()
    profile = reg.lookup_by_phone(farmers[0]["phone"])

    result = execute_conversation_tool("get_subsidy_history", {"aadhaar_id": profile.aadhaar.aadhaar_id}, "weather.duckdb")
    data = json.loads(result)
    assert "pmkisan" in data or "kcc" in data


def test_conversational_agent_init():
    from config import get_config
    from src.conversation import ConversationalAgent
    from src.conversation.state_machine import ConversationState

    config = get_config()
    agent = ConversationalAgent(config)
    assert agent.state == ConversationState.ONBOARDING
    assert agent.farmer_profile is None


def test_followup_scheduling():
    """Test followup scheduling (requires DB)."""
    import duckdb
    from src.conversation.followup import schedule_followup, get_pending_followups, followups_to_context

    conn = duckdb.connect(":memory:")
    conn.execute("""
        CREATE TABLE scheduled_followups (
            id VARCHAR PRIMARY KEY, aadhaar_id VARCHAR, session_id VARCHAR,
            trigger_type VARCHAR, trigger_value VARCHAR, message_template VARCHAR,
            status VARCHAR DEFAULT 'pending', fired_at TIMESTAMP, created_at TIMESTAMP
        )
    """)

    fid = schedule_followup(conn, "XXXX-XXXX-1234", "time", "2026-03-25T10:00:00",
                            "Check on your pepper crop after the heavy rain", "session-1")
    assert fid

    pending = get_pending_followups(conn, "XXXX-XXXX-1234")
    assert len(pending) == 1
    assert "pepper" in pending[0]["message_template"]

    ctx = followups_to_context(pending)
    assert "PENDING FOLLOW-UPS" in ctx


def test_memory_context_building():
    """Test memory context building (requires DB)."""
    import duckdb
    from src.conversation.memory import save_memories, build_memory_context

    conn = duckdb.connect(":memory:")
    conn.execute("""
        CREATE TABLE conversation_memory (
            id VARCHAR PRIMARY KEY, aadhaar_id VARCHAR, session_id VARCHAR,
            memory_type VARCHAR, content VARCHAR, expires_at TIMESTAMP, created_at TIMESTAMP
        )
    """)

    memories = [
        {"type": "topic", "content": "Asked about pepper disease management", "expires_days": None},
        {"type": "advisory_given", "content": "Recommended copper fungicide spray", "expires_days": 30},
    ]
    save_memories(conn, "XXXX-XXXX-1234", "session-1", memories)

    ctx = build_memory_context(conn, "XXXX-XXXX-1234")
    assert "CONVERSATION MEMORY" in ctx
    assert "pepper" in ctx
