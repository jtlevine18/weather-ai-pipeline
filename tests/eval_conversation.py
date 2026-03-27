"""
Level 2B — Conversation Engine Evaluation

Measures state machine correctness, language detection accuracy, tool routing
precision, memory extraction quality, and personalization uplift.

Usage:
    python tests/eval_conversation.py
    python tests/eval_conversation.py --with-llm   # include LLM-as-Judge scoring

Requires: duckdb (LLM scoring additionally needs ANTHROPIC_API_KEY)
"""

import json
import os
from collections import defaultdict
from datetime import datetime, timezone

import pytest
from rich.console import Console
from rich.table import Table

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "eval_results")


# ---------------------------------------------------------------------------
# Test datasets
# ---------------------------------------------------------------------------

STATE_TRANSITION_CASES = [
    # (current_state, message, identity_verified, expected_next_state)
    ("onboarding", "Hello, I am a farmer", False, "onboarding"),
    ("onboarding", "Yes, I am Arun Kumar", True, "active"),
    ("active", "What is the weather tomorrow?", True, "active"),
    ("active", "My entire crop loss happened this season", True, "escalated"),
    ("active", "I cannot repay my loan", True, "escalated"),
    ("active", "Show me my soil health card", True, "active"),
    ("escalated", "Thank you for the information", True, "active"),
    ("escalated", "My crop loss is getting worse and I have debt", True, "escalated"),
    ("active", "I don't understand what to do, help me", True, "escalated"),
    ("active", "Insurance claim was rejected", True, "escalated"),
]

LANGUAGE_CASES = [
    # (text, expected_language)
    ("What is the weather forecast?", "en"),
    ("How much rain will we get?", "en"),
    ("\u0ba8\u0bbe\u0bb3\u0bc8 \u0bb5\u0bbe\u0ba9\u0bbf\u0bb2\u0bc8 \u0b8e\u0ba9\u0bcd\u0ba9?", "ta"),
    ("\u0b8e\u0ba9\u0bcd \u0ba8\u0bbf\u0bb2\u0ba4\u0bcd\u0ba4\u0bbf\u0ba9\u0bcd \u0bae\u0ba3\u0bcd \u0b86\u0bb0\u0bcb\u0b95\u0bcd\u0b95\u0bbf\u0baf\u0bae\u0bcd \u0b8e\u0ba9\u0bcd\u0ba9?", "ta"),
    ("\u0d07\u0d28\u0d4d\u0d28\u0d24\u0d4d\u0d24\u0d46 \u0d15\u0d3e\u0d32\u0d3e\u0d35\u0d38\u0d4d\u0d25 \u0d0e\u0d28\u0d4d\u0d24\u0d3e\u0d23\u0d4d?", "ml"),
    ("\u0d0e\u0d28\u0d4d\u0d31\u0d46 \u0d15\u0d43\u0d37\u0d3f\u0d2f\u0d3f\u0d1f\u0d24\u0d4d\u0d24\u0d3f\u0d28\u0d4d \u0d2e\u0d23\u0d4d\u0d23\u0d3f\u0d7b\u0d31\u0d46 \u0d06\u0d30\u0d4b\u0d17\u0d4d\u0d2f\u0d02 \u0d0e\u0d28\u0d4d\u0d24\u0d3e\u0d23\u0d4d?", "ml"),
    ("12345 numbers only", "en"),
    ("   ", "en"),
]

TOOL_ROUTING_CASES = [
    # (query_pattern, expected_tool_name)
    ("Look up farmer with phone +919876543210", "lookup_farmer_profile"),
    ("What is my soil health?", "get_soil_health"),
    ("Show soil pH and nutrients", "get_soil_health"),
    ("Is my crop insured?", "get_insurance_status"),
    ("What is my insurance claim status?", "get_insurance_status"),
    ("How many PM-KISAN installments did I get?", "get_subsidy_history"),
    ("What is my KCC credit limit?", "get_subsidy_history"),
    ("Give me a personalized weather advisory", "get_personalized_advisory"),
    ("Remind me to check crops after rain", "schedule_followup"),
    ("What are the forecasts for Wayanad?", "query_forecasts"),
    ("Show station health", "get_station_health"),
]

ESCALATION_CASES = [
    # (message, should_escalate)
    ("What is the weather?", False),
    ("Show me forecasts", False),
    ("My crop loss is total this year", True),
    ("I cannot repay the loan", True),
    ("Insurance claim rejected what do I do", True),
    ("I don't understand anything", True),
    ("Tell me about my soil health", False),
    ("Crop failed completely due to flooding", True),
    ("Thank you very much", False),
    ("I am confused help me", True),
]


def run_conversation_eval(with_llm=False):
    console = Console()
    console.print(f"\n[bold]Level 2B — Conversation Engine Eval[/bold]\n")

    results = {
        "eval_name": "conversation",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    # ─── 1. State Machine Correctness ─────────────
    from src.conversation.state_machine import ConversationState, next_state

    sm_pass = 0
    sm_fail = 0
    sm_errors = []
    for current_str, message, verified, expected_str in STATE_TRANSITION_CASES:
        current = ConversationState(current_str)
        expected = ConversationState(expected_str)
        actual = next_state(current, message, identity_verified=verified)
        if actual == expected:
            sm_pass += 1
        else:
            sm_fail += 1
            sm_errors.append(f"  {current_str} + '{message[:40]}' -> {actual.value} (expected {expected_str})")

    sm_rate = sm_pass / (sm_pass + sm_fail) if (sm_pass + sm_fail) > 0 else 0

    tbl_sm = Table(title="State Machine Correctness")
    tbl_sm.add_column("Metric", style="bold")
    tbl_sm.add_column("Value", justify="right")
    tbl_sm.add_row("Test cases", str(len(STATE_TRANSITION_CASES)))
    tbl_sm.add_row("Passed", str(sm_pass))
    tbl_sm.add_row("Failed", str(sm_fail))
    tbl_sm.add_row("Accuracy", f"{sm_rate:.0%}")
    console.print(tbl_sm)
    if sm_errors:
        for err in sm_errors:
            console.print(f"[red]{err}[/red]")

    results["state_machine"] = {
        "cases": len(STATE_TRANSITION_CASES),
        "passed": sm_pass,
        "accuracy": sm_rate,
    }

    # ─── 2. Language Detection Accuracy ────────────
    from src.conversation.language import detect_language

    lang_pass = 0
    lang_fail = 0
    lang_errors = []
    for text, expected in LANGUAGE_CASES:
        actual = detect_language(text)
        if actual == expected:
            lang_pass += 1
        else:
            lang_fail += 1
            lang_errors.append(f"  '{text[:30]}...' -> {actual} (expected {expected})")

    lang_rate = lang_pass / (lang_pass + lang_fail) if (lang_pass + lang_fail) > 0 else 0

    tbl_lang = Table(title="\nLanguage Detection Accuracy")
    tbl_lang.add_column("Metric", style="bold")
    tbl_lang.add_column("Value", justify="right")
    tbl_lang.add_row("Test cases", str(len(LANGUAGE_CASES)))
    tbl_lang.add_row("Passed", str(lang_pass))
    tbl_lang.add_row("Failed", str(lang_fail))
    tbl_lang.add_row("Accuracy", f"{lang_rate:.0%}")
    console.print(tbl_lang)
    if lang_errors:
        for err in lang_errors:
            console.print(f"[red]{err}[/red]")

    results["language_detection"] = {
        "cases": len(LANGUAGE_CASES),
        "passed": lang_pass,
        "accuracy": lang_rate,
    }

    # ─── 3. Escalation Detection ───────────────────
    from src.conversation.state_machine import check_escalation

    esc_pass = 0
    esc_fail = 0
    esc_errors = []
    for message, should_escalate in ESCALATION_CASES:
        actual = check_escalation(message)
        if actual == should_escalate:
            esc_pass += 1
        else:
            esc_fail += 1
            esc_errors.append(f"  '{message[:40]}' -> {actual} (expected {should_escalate})")

    esc_rate = esc_pass / (esc_pass + esc_fail) if (esc_pass + esc_fail) > 0 else 0

    tbl_esc = Table(title="\nEscalation Detection Accuracy")
    tbl_esc.add_column("Metric", style="bold")
    tbl_esc.add_column("Value", justify="right")
    tbl_esc.add_row("Test cases", str(len(ESCALATION_CASES)))
    tbl_esc.add_row("Passed", str(esc_pass))
    tbl_esc.add_row("Accuracy", f"{esc_rate:.0%}")
    console.print(tbl_esc)
    if esc_errors:
        for err in esc_errors:
            console.print(f"[yellow]{err}[/yellow]")

    results["escalation_detection"] = {
        "cases": len(ESCALATION_CASES),
        "passed": esc_pass,
        "accuracy": esc_rate,
    }

    # ─── 4. Tool Definition Completeness ───────────
    from src.conversation.tools import CONVERSATION_TOOLS
    from src.nl_agent import TOOLS as NL_TOOLS

    all_tools = list(NL_TOOLS) + list(CONVERSATION_TOOLS)
    tool_names = {t["name"] for t in all_tools}
    tools_with_schema = sum(1 for t in all_tools if t.get("input_schema"))

    tbl_tools = Table(title="\nTool Definition Completeness")
    tbl_tools.add_column("Metric", style="bold")
    tbl_tools.add_column("Value", justify="right")
    tbl_tools.add_row("NL Agent tools", str(len(NL_TOOLS)))
    tbl_tools.add_row("Conversation tools", str(len(CONVERSATION_TOOLS)))
    tbl_tools.add_row("Total tools", str(len(all_tools)))
    tbl_tools.add_row("With input schema", str(tools_with_schema))
    tbl_tools.add_row("Tool names", ", ".join(sorted(tool_names)))
    console.print(tbl_tools)

    results["tools"] = {
        "nl_tools": len(NL_TOOLS),
        "conversation_tools": len(CONVERSATION_TOOLS),
        "total": len(all_tools),
        "with_schema": tools_with_schema,
    }

    # ─── 5. Prompt Quality ─────────────────────────
    from src.conversation.prompts import build_system_prompt

    prompt_checks = 0
    prompt_pass = 0
    prompt_issues = []

    for state in ConversationState:
        for lang in ["en", "ta", "ml"]:
            prompt = build_system_prompt(state, farmer_context="TEST", language=lang)
            prompt_checks += 1
            issues = []
            if state.value.upper() not in prompt:
                issues.append(f"missing state name {state.value}")
            if lang != "en" and {"ta": "Tamil", "ml": "Malayalam"}[lang] not in prompt:
                issues.append(f"missing language name for {lang}")
            if "TEST" not in prompt:
                issues.append("farmer context not injected")
            if issues:
                prompt_issues.append(f"  {state.value}/{lang}: {', '.join(issues)}")
            else:
                prompt_pass += 1

    prompt_rate = prompt_pass / prompt_checks if prompt_checks else 0

    tbl_prompt = Table(title="\nPrompt Quality")
    tbl_prompt.add_column("Metric", style="bold")
    tbl_prompt.add_column("Value", justify="right")
    tbl_prompt.add_row("Combinations tested", str(prompt_checks))
    tbl_prompt.add_row("Passed", str(prompt_pass))
    tbl_prompt.add_row("Quality rate", f"{prompt_rate:.0%}")
    console.print(tbl_prompt)
    if prompt_issues:
        for issue in prompt_issues:
            console.print(f"[yellow]{issue}[/yellow]")

    results["prompts"] = {
        "combinations": prompt_checks,
        "passed": prompt_pass,
        "quality_rate": prompt_rate,
    }

    # ─── 6. Memory + Followup (DB integration) ────
    import duckdb
    from src.conversation.memory import save_memories, build_memory_context
    from src.conversation.followup import schedule_followup, check_and_fire, get_pending_followups

    conn = duckdb.connect(":memory:")
    conn.execute("""
        CREATE TABLE conversation_memory (
            id VARCHAR PRIMARY KEY, aadhaar_id VARCHAR, session_id VARCHAR,
            memory_type VARCHAR, content VARCHAR, expires_at TIMESTAMP, created_at TIMESTAMP
        );
        CREATE TABLE scheduled_followups (
            id VARCHAR PRIMARY KEY, aadhaar_id VARCHAR, session_id VARCHAR,
            trigger_type VARCHAR, trigger_value VARCHAR, message_template VARCHAR,
            status VARCHAR DEFAULT 'pending', fired_at TIMESTAMP, created_at TIMESTAMP
        );
    """)

    # Memory round-trip
    test_memories = [
        {"type": "topic", "content": "Discussed pepper disease management", "expires_days": None},
        {"type": "advisory_given", "content": "Apply copper fungicide at 2g/L", "expires_days": 30},
        {"type": "farmer_reported", "content": "Farmer saw leaf blight on pepper plants", "expires_days": 14},
    ]
    save_memories(conn, "XXXX-XXXX-1234", "session-test", test_memories)
    mem_ctx = build_memory_context(conn, "XXXX-XXXX-1234")
    mem_ok = "CONVERSATION MEMORY" in mem_ctx and "pepper" in mem_ctx

    # Followup round-trip
    schedule_followup(conn, "XXXX-XXXX-1234", "time", "2020-01-01T00:00:00",
                      "Check pepper crop after rain", "session-test")
    schedule_followup(conn, "XXXX-XXXX-1234", "time", "2099-12-31T00:00:00",
                      "Future followup", "session-test")
    fired = check_and_fire(conn)
    pending = get_pending_followups(conn, "XXXX-XXXX-1234")
    followup_ok = len(fired) == 1 and len(pending) == 1

    tbl_persist = Table(title="\nPersistence (Memory + Followups)")
    tbl_persist.add_column("Test", style="bold")
    tbl_persist.add_column("Result", justify="right")
    tbl_persist.add_row("Memory round-trip", "[green]PASS[/green]" if mem_ok else "[red]FAIL[/red]")
    tbl_persist.add_row("Memory context has sections", "[green]PASS[/green]" if mem_ok else "[red]FAIL[/red]")
    tbl_persist.add_row("Followup scheduling", "[green]PASS[/green]" if followup_ok else "[red]FAIL[/red]")
    tbl_persist.add_row("Due followups fired", f"{len(fired)} fired, {len(pending)} pending")
    console.print(tbl_persist)

    results["persistence"] = {
        "memory_roundtrip": mem_ok,
        "followup_roundtrip": followup_ok,
        "followups_fired": len(fired),
        "followups_pending": len(pending),
    }

    # ─── 7. LLM-as-Judge: Personalization (optional) ──
    if with_llm:
        console.print("\n[bold]LLM-as-Judge: Personalization Quality[/bold]")
        personalization_results = _eval_personalization(console)
        results["personalization"] = personalization_results
    else:
        console.print("\n[dim]Skipping LLM-as-Judge scoring (use --with-llm to enable)[/dim]")

    # ─── Summary ───────────────────────────────────
    total_checks = sm_pass + sm_fail + lang_pass + lang_fail + esc_pass + esc_fail + prompt_checks
    total_pass = sm_pass + lang_pass + esc_pass + prompt_pass
    if mem_ok:
        total_checks += 1
        total_pass += 1
    if followup_ok:
        total_checks += 1
        total_pass += 1
    overall_rate = total_pass / total_checks if total_checks else 0

    console.print(f"\n[bold]Overall: {total_pass}/{total_checks} checks passed ({overall_rate:.0%})[/bold]")

    results["overall"] = {
        "total_checks": total_checks,
        "total_passed": total_pass,
        "overall_rate": overall_rate,
    }

    # ─── Save ──────────────────────────────────────
    os.makedirs(RESULTS_DIR, exist_ok=True)
    out = os.path.join(RESULTS_DIR, "conversation.json")
    with open(out, "w") as f:
        json.dump(results, f, indent=2, default=str)
    console.print(f"\n[dim]Results saved to {out}[/dim]")
    return results


def _eval_personalization(console):
    """Compare generic vs personalized advisory prompts using LLM-as-Judge."""
    from config import get_config, STATION_MAP
    config = get_config()

    if not config.anthropic_key:
        console.print("[yellow]ANTHROPIC_API_KEY required for personalization eval.[/yellow]")
        return {"skipped": True}

    import anthropic
    client = anthropic.Anthropic(api_key=config.anthropic_key)

    from src.dpi.simulator import get_registry
    from src.dpi import DPIAgent
    registry = get_registry()
    agent = DPIAgent()

    # Take 3 farmers for evaluation
    test_farmers = registry.list_farmers()[:3]
    scores = []

    for f in test_farmers:
        profile = registry.lookup_by_phone(f["phone"])
        if not profile:
            continue

        station = STATION_MAP.get(profile.nearest_stations[0]) if profile.nearest_stations else None
        if not station:
            continue

        # Generic advisory prompt
        generic_prompt = (
            f"Heavy rain expected in {station.name}. "
            f"Crops in region: {station.crop_context}. "
            f"Generate a 2-sentence agricultural advisory."
        )

        # Personalized advisory prompt
        ctx = agent.profile_to_context(profile)
        personalized_prompt = (
            f"Heavy rain expected in {station.name}.\n\n"
            f"{ctx}\n\n"
            f"Generate a 2-sentence agricultural advisory personalized to this farmer's "
            f"specific crops, soil, and financial situation."
        )

        generic_resp = client.messages.create(
            model=config.translation.model, max_tokens=200,
            messages=[{"role": "user", "content": generic_prompt}],
        ).content[0].text.strip()

        personal_resp = client.messages.create(
            model=config.translation.model, max_tokens=200,
            messages=[{"role": "user", "content": personalized_prompt}],
        ).content[0].text.strip()

        # Judge: How much more specific is the personalized version?
        judge_prompt = (
            f"Compare these two agricultural advisories for a farmer:\n\n"
            f"GENERIC:\n\"{generic_resp}\"\n\n"
            f"PERSONALIZED:\n\"{personal_resp}\"\n\n"
            f"Rate personalization uplift 0-5:\n"
            f"0 = identical or personalized is worse\n"
            f"1 = slight mention of farmer specifics\n"
            f"2 = references some farmer data\n"
            f"3 = clearly uses farmer's crops/soil\n"
            f"4 = strongly tailored to farmer's situation\n"
            f"5 = deeply personalized with multiple farmer-specific details\n\n"
            f"Return ONLY a single number:"
        )

        import re
        judge_resp = client.messages.create(
            model=config.translation.model, max_tokens=10,
            messages=[{"role": "user", "content": judge_prompt}],
        ).content[0].text.strip()
        match = re.search(r"(\d)", judge_resp)
        score = int(match.group(1)) if match else 3

        scores.append({
            "farmer": f["name"],
            "station": station.station_id,
            "score": score,
            "generic_preview": generic_resp[:80],
            "personal_preview": personal_resp[:80],
        })

        console.print(f"  {f['name']} ({station.station_id}): "
                      f"personalization={score}/5")

    avg_score = sum(s["score"] for s in scores) / len(scores) if scores else 0
    console.print(f"\n  Avg personalization uplift: {avg_score:.1f}/5")

    return {
        "n_farmers": len(scores),
        "avg_uplift": avg_score,
        "scores": scores,
    }


@pytest.mark.slow
@pytest.mark.offline
def test_eval_conversation():
    """Pytest wrapper for standalone eval script."""
    results = run_conversation_eval()
    assert results is not None


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--with-llm", action="store_true",
                        help="Include LLM-as-Judge personalization scoring")
    args = parser.parse_args()
    run_conversation_eval(with_llm=args.with_llm)
