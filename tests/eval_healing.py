"""
Level 1A — Self-Healing Data Quality Evaluation

Measures detection precision/recall per fault type and imputation accuracy
against synthetic ground truth. Evaluates both the AI healing agent
(Claude Sonnet with 5 investigation tools) and the rule-based fallback.

Usage:
    python tests/eval_healing.py              # Rule-based only
    python tests/eval_healing.py --ai         # AI agent (requires ANTHROPIC_API_KEY)
"""

import json
import math
import os
import random
from collections import defaultdict
from datetime import datetime

import pytest
from rich.console import Console
from rich.table import Table

from config import STATIONS, FaultInjectionConfig
from src.ingestion import _baseline, _inject_fault
from src.healing import RuleBasedFallback, HealingAgent

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "eval_results")
N_PER_STATION = 50


def generate_pair(station, fault_config):
    """Generate (faulted_reading, ground_truth) with known fault type."""
    baseline = _baseline(station)
    ground_truth = dict(baseline)

    reading = dict(baseline)
    reading["id"] = f"eval_{station.station_id}_{random.randint(0, 999999):06d}"
    reading["station_id"] = station.station_id
    reading["ts"] = datetime.utcnow().isoformat()
    reading["source"] = "eval"
    reading["fault_type"] = None
    reading = _inject_fault(reading, fault_config)
    return reading, ground_truth


def make_reference(ground_truth):
    """Simulate a reference source (Tomorrow.io / NASA POWER) with small noise."""
    return {
        "temperature": ground_truth["temperature"] + random.gauss(0, 0.3),
        "humidity": ground_truth["humidity"] + random.gauss(0, 1.0),
        "wind_speed": ground_truth["wind_speed"] + random.gauss(0, 0.2),
        "pressure": ground_truth.get("pressure", 1013.0),
        "rainfall": ground_truth.get("rainfall", 0.0),
        "source": "eval_reference",
    }


def _rmse(errors):
    return math.sqrt(sum(e ** 2 for e in errors) / len(errors)) if errors else float("nan")


def _mae(errors):
    return sum(abs(e) for e in errors) / len(errors) if errors else float("nan")


def run_healing_eval(n_per_station=N_PER_STATION, seed=42):
    random.seed(seed)
    console = Console()
    healer = RuleBasedFallback()

    # Elevated fault rates for eval (60% total fault rate)
    fault_config = FaultInjectionConfig(
        typo_rate=0.15, offline_rate=0.15, drift_rate=0.15, missing_rate=0.15
    )

    confusion = defaultdict(lambda: defaultdict(int))
    imputation_errors = defaultdict(list)
    quality_scores = defaultdict(list)
    total = 0

    for station in STATIONS:
        for _ in range(n_per_station):
            reading, ground_truth = generate_pair(station, fault_config)
            fault = reading.get("fault_type") or "clean"
            reference = make_reference(ground_truth)

            healed = healer.heal(reading, reference=reference)

            if healed is None:
                action = "skipped"
            else:
                action = healed.get("heal_action", "none")
                quality_scores[fault].append(healed.get("quality_score", 1.0))

            confusion[fault][action] += 1

            # Imputation error vs ground truth
            if healed is not None and fault != "clean":
                for field in ("temperature", "humidity", "wind_speed"):
                    gt = ground_truth.get(field)
                    hv = healed.get(field)
                    if gt is not None and hv is not None:
                        imputation_errors[fault].append(abs(hv - gt))

            total += 1

    # Binary detection: heal_action != "none" means fault detected
    tp = fp = fn = tn = 0
    fault_types = ["clean", "typo", "offline", "drift", "missing_field"]
    for fault in fault_types:
        for action, count in confusion[fault].items():
            detected = action not in ("none",)
            is_fault = fault != "clean"
            if detected and is_fault:
                tp += count
            elif detected and not is_fault:
                fp += count
            elif not detected and is_fault:
                fn += count
            else:
                tn += count

    prec = tp / (tp + fp) if (tp + fp) > 0 else 0
    rec = tp / (tp + fn) if (tp + fn) > 0 else 0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0

    # Per-fault-type accuracy (was the expected heal_action applied?)
    expected_map = {
        "clean": "none",
        "typo": "typo_corrected",
        "offline": "imputed_from_reference",
    }
    metrics = {}
    for fault in fault_types:
        total_f = sum(confusion[fault].values())
        expected = expected_map.get(fault)
        if expected:
            correct = confusion[fault].get(expected, 0)
            acc = correct / total_f if total_f > 0 else 0
        else:
            acc = None  # drift and missing_field not detectable by rule-based healer

        errs = imputation_errors.get(fault, [])
        qs = quality_scores.get(fault, [])
        metrics[fault] = {
            "count": total_f,
            "confusion": dict(confusion[fault]),
            "expected_action": expected,
            "accuracy": acc,
            "imputation_mae": _mae(errs) if errs else None,
            "imputation_rmse": _rmse(errs) if errs else None,
            "avg_quality_score": sum(qs) / len(qs) if qs else None,
        }

    # ── Terminal output ─────────────────────────────
    console.print(f"\n[bold]Level 1A — Self-Healing Eval[/bold]")
    console.print(f"Total readings: {total}\n")

    all_actions = sorted({a for f in confusion.values() for a in f})
    tbl = Table(title="Confusion Matrix: fault_type -> heal_action")
    tbl.add_column("fault_type", style="bold")
    for a in all_actions:
        tbl.add_column(a, justify="right")
    tbl.add_column("total", justify="right", style="dim")
    for fault in fault_types:
        row = [fault]
        rt = sum(confusion[fault].values())
        for a in all_actions:
            row.append(str(confusion[fault].get(a, 0)))
        row.append(str(rt))
        tbl.add_row(*row)
    console.print(tbl)

    console.print(f"\n[bold]Binary Detection[/bold]")
    console.print(f"  Precision: {prec:.1%}  |  Recall: {rec:.1%}  |  F1: {f1:.1%}")

    tbl2 = Table(title="\nPer-Fault-Type Metrics")
    tbl2.add_column("Fault Type", style="bold")
    tbl2.add_column("Count", justify="right")
    tbl2.add_column("Detection Rate", justify="right")
    tbl2.add_column("Imputation MAE", justify="right")
    tbl2.add_column("Imputation RMSE", justify="right")
    tbl2.add_column("Avg Quality Score", justify="right")
    for fault in fault_types:
        m = metrics[fault]
        det = f"{m['accuracy']:.1%}" if m["accuracy"] is not None else "not detectable"
        imp = f"{m['imputation_mae']:.2f}" if m["imputation_mae"] is not None else "---"
        rms = f"{m['imputation_rmse']:.2f}" if m["imputation_rmse"] is not None else "---"
        qs_str = f"{m['avg_quality_score']:.2f}" if m["avg_quality_score"] is not None else "---"
        tbl2.add_row(fault, str(m["count"]), det, imp, rms, qs_str)
    console.print(tbl2)

    # ── Save results ────────────────────────────────
    os.makedirs(RESULTS_DIR, exist_ok=True)
    results = {
        "eval_name": "healing",
        "timestamp": datetime.utcnow().isoformat(),
        "total_readings": total,
        "binary_detection": {
            "precision": prec, "recall": rec, "f1": f1,
            "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        },
        "per_fault_type": metrics,
    }
    out = os.path.join(RESULTS_DIR, "healing.json")
    with open(out, "w") as f:
        json.dump(results, f, indent=2, default=str)
    console.print(f"\n[dim]Results saved to {out}[/dim]")
    return results


def run_ai_healing_eval(n_per_station=5, seed=42):
    """Evaluate HealingAgent (Claude) on synthetic faulted readings.

    Uses a small sample (default 5 per station = 100 total) to control cost.
    Requires ANTHROPIC_API_KEY in environment.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        print("ANTHROPIC_API_KEY not set — skipping AI healing eval")
        return None

    random.seed(seed)
    console = Console()
    agent = HealingAgent(api_key)

    fault_config = FaultInjectionConfig(
        typo_rate=0.15, offline_rate=0.15, drift_rate=0.15, missing_rate=0.15
    )

    # Generate all readings + ground truth
    all_readings = []
    ground_truths = {}
    references = {}
    for station in STATIONS:
        for _ in range(n_per_station):
            reading, ground_truth = generate_pair(station, fault_config)
            all_readings.append(reading)
            ground_truths[reading["id"]] = ground_truth
            references[station.station_id] = make_reference(ground_truth)

    # Run AI agent (batch mode)
    import duckdb
    from src.database import DDL
    conn = duckdb.connect(":memory:")
    conn.execute(DDL)

    result = agent.heal_batch(all_readings, references, conn)
    conn.close()

    console.print(f"\n[bold]Level 1A — AI Healing Agent Eval[/bold]")
    console.print(f"Model: {result.model}")
    console.print(f"Tokens: {result.tokens_in} in / {result.tokens_out} out")
    console.print(f"Latency: {result.latency_s:.1f}s")
    console.print(f"Fallback used: {result.fallback_used}")
    console.print(f"Assessments: {len(result.assessments)}")

    # Confusion: fault_type -> assessment
    readings_by_id = {r["id"]: r for r in all_readings}
    confusion = defaultdict(lambda: defaultdict(int))
    imputation_errors = defaultdict(list)
    quality_scores = defaultdict(list)
    for a in result.assessments:
        rid = a.get("reading_id", "")
        gt = ground_truths.get(rid, {})
        orig_reading = readings_by_id.get(rid, {})
        fault = orig_reading.get("fault_type") or "clean"
        assessment = a.get("assessment", "unknown")
        confusion[fault][assessment] += 1
        quality_scores[fault].append(a.get("quality_score", 0))

        corrections = a.get("corrections", {})
        if isinstance(corrections, str):
            try:
                corrections = json.loads(corrections)
            except (json.JSONDecodeError, TypeError):
                corrections = {}

        for field in ("temperature", "humidity", "wind_speed"):
            gt_val = gt.get(field)
            corrected_val = corrections.get(field)
            if corrected_val is not None and gt_val is not None:
                imputation_errors[fault].append(abs(corrected_val - gt_val))

    # Assessment distribution table
    all_assessments = sorted({a for f in confusion.values() for a in f})
    tbl = Table(title="AI Agent: fault_type -> assessment")
    tbl.add_column("fault_type", style="bold")
    for a in all_assessments:
        tbl.add_column(a, justify="right")
    tbl.add_column("total", justify="right", style="dim")
    fault_types = ["clean", "typo", "offline", "drift", "missing_field"]
    for fault in fault_types:
        row = [fault]
        rt = sum(confusion[fault].values())
        for a in all_assessments:
            row.append(str(confusion[fault].get(a, 0)))
        row.append(str(rt))
        tbl.add_row(*row)
    console.print(tbl)

    # Tool usage summary
    tool_counts = defaultdict(int)
    for a in result.assessments:
        tools = a.get("tools_used", [])
        if isinstance(tools, str):
            tools = [t.strip() for t in tools.split(",") if t.strip()]
        for t in tools:
            tool_counts[t] += 1
    if tool_counts:
        console.print("\n[bold]Tool Usage[/bold]")
        for tool, cnt in sorted(tool_counts.items(), key=lambda x: -x[1]):
            console.print(f"  {tool}: {cnt}")

    # Save results
    os.makedirs(RESULTS_DIR, exist_ok=True)
    ai_results = {
        "eval_name": "healing_ai",
        "timestamp": datetime.utcnow().isoformat(),
        "model": result.model,
        "tokens_in": result.tokens_in,
        "tokens_out": result.tokens_out,
        "latency_s": result.latency_s,
        "fallback_used": result.fallback_used,
        "total_readings": len(all_readings),
        "total_assessments": len(result.assessments),
        "confusion": {f: dict(v) for f, v in confusion.items()},
        "tool_usage": dict(tool_counts),
    }
    out = os.path.join(RESULTS_DIR, "healing_ai.json")
    with open(out, "w") as f:
        json.dump(ai_results, f, indent=2, default=str)
    console.print(f"\n[dim]Results saved to {out}[/dim]")
    return ai_results


@pytest.mark.slow
@pytest.mark.offline
def test_eval_healing():
    """Pytest wrapper for standalone eval script."""
    results = run_healing_eval()
    assert results is not None


@pytest.mark.slow
def test_eval_healing_ai():
    """Pytest wrapper for AI agent eval (requires ANTHROPIC_API_KEY)."""
    if not os.getenv("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY not set")
    results = run_ai_healing_eval(n_per_station=2)
    assert results is not None
    assert results["total_assessments"] > 0


if __name__ == "__main__":
    import sys
    if "--ai" in sys.argv:
        run_ai_healing_eval()
    else:
        run_healing_eval()
