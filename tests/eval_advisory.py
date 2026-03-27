"""
Level 1D — Advisory Quality Evaluation

Scores generated advisories using LLM-as-Judge (Claude):
  Accuracy (0-5), Actionability (0-5), Safety (-5 to +5),
  Cultural Appropriateness (0-5)

Usage:
    python tests/eval_advisory.py
    python tests/eval_advisory.py --max-cases 10   # limit for cost control

Requires: ANTHROPIC_API_KEY
"""

import json
import os
import re
from datetime import datetime, timezone

import pytest
from rich.console import Console
from rich.table import Table

from config import get_config, STATION_MAP
from src.translation.local_provider import LocalProvider

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "eval_results")
GOLDEN_SET = os.path.join(os.path.dirname(__file__), "eval_advisory_golden_set.json")

JUDGE_SYSTEM = (
    "You are an agricultural advisory quality evaluator for smallholder farmers "
    "in South India. Score the advisory on four criteria. "
    "Return ONLY four lines, no other text.\n\n"
    "ACCURACY: N  (0-5: does advisory match the weather condition?)\n"
    "ACTIONABILITY: N  (0-5: specific actions, chemical names/rates, timing?)\n"
    "SAFETY: N  (-5 to +5: -5=dangerous advice, 0=neutral, +5=explicitly safe)\n"
    "CULTURAL_APPROPRIATENESS: N  (0-5: specific to the crops and region?)"
)


def judge_advisory(client, model, case, advisory_text):
    """Use Claude to score an advisory. Returns dict of scores."""
    user = (
        f"Weather: {case['condition'].replace('_', ' ')}, "
        f"Temp {case['temperature']}C, Rain {case['rainfall']}mm, "
        f"Wind {case['wind_speed']}km/h\n"
        f"Region: {case['state']}\n"
        f"Crops: {case['crop_context']}\n\n"
        f"Advisory to evaluate:\n\"{advisory_text}\""
    )
    msg = client.messages.create(
        model=model, max_tokens=100, system=JUDGE_SYSTEM,
        messages=[{"role": "user", "content": user}],
    )
    text = msg.content[0].text.strip()
    scores = {}
    for line in text.splitlines():
        for key in ("ACCURACY", "ACTIONABILITY", "SAFETY", "CULTURAL_APPROPRIATENESS"):
            if line.upper().startswith(key):
                match = re.search(r"(-?\d+(?:\.\d+)?)", line)
                if match:
                    scores[key.lower()] = float(match.group(1))
    return scores


def make_forecast(case):
    """Convert golden test case to forecast dict."""
    return {
        "condition": case["condition"],
        "temperature": case["temperature"],
        "rainfall": case["rainfall"],
        "humidity": case["humidity"],
        "wind_speed": case["wind_speed"],
    }


def run_advisory_eval(max_cases=None):
    console = Console()
    config = get_config()

    if not config.anthropic_key:
        console.print("[red]ANTHROPIC_API_KEY required for LLM-as-Judge scoring.[/red]")
        console.print("Set it in .env and re-run.")
        return None

    import anthropic
    client = anthropic.Anthropic(api_key=config.anthropic_key)

    with open(GOLDEN_SET) as f:
        golden = json.load(f)

    if max_cases:
        golden = golden[:max_cases]

    console.print(f"\n[bold]Level 1D — Advisory Quality Eval[/bold]")
    console.print(f"Test cases: {len(golden)}  |  "
                  f"Judge model: {config.translation.model}\n")

    local = LocalProvider()
    all_scores = []

    for i, case in enumerate(golden):
        forecast = make_forecast(case)
        station = STATION_MAP.get(case["station_id"])
        if station is None:
            continue

        result = local.generate_advisory(forecast, station)
        advisory = result.get("advisory_en", "")

        scores = judge_advisory(client, config.translation.model, case, advisory)
        scores["case_id"] = case["id"]
        scores["category"] = case["category"]
        scores["provider"] = "rule_based"
        scores["advisory_preview"] = advisory[:120]
        scores["safety_critical"] = case.get("safety_critical", False)
        all_scores.append(scores)

        if (i + 1) % 10 == 0:
            console.print(f"  Scored {i + 1}/{len(golden)} cases...")

    if not all_scores:
        console.print("[yellow]No scores generated.[/yellow]")
        return None

    # Aggregate
    by_provider = {
        "rule_based": {
            "n": len(all_scores),
            "avg_accuracy": sum(s.get("accuracy", 0) for s in all_scores) / len(all_scores),
            "avg_actionability": sum(s.get("actionability", 0) for s in all_scores) / len(all_scores),
            "avg_safety": sum(s.get("safety", 0) for s in all_scores) / len(all_scores),
            "avg_cultural": sum(s.get("cultural_appropriateness", 0) for s in all_scores) / len(all_scores),
        }
    }

    # Display
    tbl = Table(title="Advisory Quality by Provider")
    tbl.add_column("Provider", style="bold")
    tbl.add_column("N", justify="right")
    tbl.add_column("Accuracy", justify="right")
    tbl.add_column("Actionability", justify="right")
    tbl.add_column("Safety", justify="right")
    tbl.add_column("Cultural", justify="right")
    for prov, m in by_provider.items():
        tbl.add_row(prov, str(m["n"]),
                     f"{m['avg_accuracy']:.1f}/5", f"{m['avg_actionability']:.1f}/5",
                     f"{m['avg_safety']:+.1f}", f"{m['avg_cultural']:.1f}/5")
    console.print(tbl)

    # Safety concerns
    unsafe = [s for s in all_scores if s.get("safety", 0) < 0]
    if unsafe:
        console.print(f"\n[red]Safety concerns: {len(unsafe)} advisories scored negative[/red]")
        for s in unsafe[:5]:
            console.print(f"  {s['case_id']}: safety={s.get('safety', 0):+.0f}")
            console.print(f"    {s['advisory_preview']}...")

    # Safety-critical cases
    safety_critical = [s for s in all_scores if s.get("safety_critical")]
    if safety_critical:
        console.print(f"\n[bold]Safety-Critical Cases[/bold]")
        for s in safety_critical:
            console.print(f"  {s['case_id']}: safety={s.get('safety', 0):+.0f}  "
                          f"accuracy={s.get('accuracy', 0):.0f}/5")

    # By category
    cats = sorted(set(s["category"] for s in all_scores))
    tbl2 = Table(title="\nScores by Category")
    tbl2.add_column("Category", style="bold")
    tbl2.add_column("N", justify="right")
    tbl2.add_column("Avg Accuracy", justify="right")
    tbl2.add_column("Avg Actionability", justify="right")
    tbl2.add_column("Avg Safety", justify="right")
    for cat in cats:
        subset = [s for s in all_scores if s["category"] == cat]
        aa = sum(s.get("accuracy", 0) for s in subset) / len(subset)
        ab = sum(s.get("actionability", 0) for s in subset) / len(subset)
        sa = sum(s.get("safety", 0) for s in subset) / len(subset)
        tbl2.add_row(cat, str(len(subset)), f"{aa:.1f}/5", f"{ab:.1f}/5", f"{sa:+.1f}")
    console.print(tbl2)

    # Save
    os.makedirs(RESULTS_DIR, exist_ok=True)
    results = {
        "eval_name": "advisory",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "n_cases": len(golden),
        "by_provider": by_provider,
        "scores": all_scores,
    }
    out = os.path.join(RESULTS_DIR, "advisory.json")
    with open(out, "w") as f:
        json.dump(results, f, indent=2, default=str)
    console.print(f"\n[dim]Results saved to {out}[/dim]")
    return results


@pytest.mark.slow
@pytest.mark.api
def test_eval_advisory():
    """Pytest wrapper for standalone eval script."""
    results = run_advisory_eval()
    assert results is not None


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-cases", type=int, default=None,
                        help="Limit number of test cases (for cost control)")
    args = parser.parse_args()
    run_advisory_eval(max_cases=args.max_cases)
