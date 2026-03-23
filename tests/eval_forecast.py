"""
Level 1B — Forecast Accuracy Evaluation

Measures MAE, RMSE, bias per variable, per station, per model type.
Compares MOS-corrected vs raw NWP vs persistence baseline.

Usage:
    python tests/eval_forecast.py
"""

import json
import math
import os
from collections import defaultdict
from datetime import datetime

import pytest
from rich.console import Console
from rich.table import Table

from src.database import init_db

PROJECT_ROOT = os.path.join(os.path.dirname(__file__), "..")
DB_PATH = os.path.join(PROJECT_ROOT, "weather.duckdb")
RESULTS_DIR = os.path.join(os.path.dirname(__file__), "eval_results")


def pair_forecasts_with_actuals(conn, limit=2000):
    """Match forecasts with closest clean_telemetry observation per station."""
    forecasts_raw = conn.execute(
        "SELECT * FROM forecasts ORDER BY issued_at DESC LIMIT ?", [limit]
    ).fetchall()
    if not forecasts_raw:
        return []
    f_cols = [d[0] for d in conn.description]
    forecasts = [dict(zip(f_cols, r)) for r in forecasts_raw]

    actuals_raw = conn.execute(
        "SELECT * FROM clean_telemetry ORDER BY ts DESC LIMIT ?", [limit * 2]
    ).fetchall()
    if not actuals_raw:
        return []
    a_cols = [d[0] for d in conn.description]
    actuals = [dict(zip(a_cols, r)) for r in actuals_raw]

    actual_by_station = defaultdict(list)
    for a in actuals:
        actual_by_station[a["station_id"]].append(a)

    pairs = []
    for f in forecasts:
        sid = f["station_id"]
        candidates = actual_by_station.get(sid, [])
        if not candidates:
            continue

        f_ts = f.get("issued_at")
        if isinstance(f_ts, str):
            f_ts = datetime.fromisoformat(f_ts.replace("Z", ""))

        best, best_delta = None, float("inf")
        for c in candidates:
            c_ts = c.get("ts")
            if isinstance(c_ts, str):
                c_ts = datetime.fromisoformat(c_ts.replace("Z", ""))
            try:
                delta = abs((f_ts - c_ts).total_seconds())
            except Exception:
                continue
            if delta < best_delta:
                best_delta = delta
                best = c

        if best is not None and best_delta < 3600 * 12:
            pairs.append({
                "station_id": sid,
                "model_used": f.get("model_used", "unknown"),
                "forecast_temp": f.get("temperature"),
                "forecast_humidity": f.get("humidity"),
                "forecast_wind": f.get("wind_speed"),
                "forecast_rain": f.get("rainfall"),
                "nwp_temp": f.get("nwp_temp"),
                "correction": f.get("correction", 0),
                "confidence": f.get("confidence", 0.7),
                "actual_temp": best.get("temperature"),
                "actual_humidity": best.get("humidity"),
                "actual_wind": best.get("wind_speed"),
                "actual_rain": best.get("rainfall"),
                "time_delta_s": best_delta,
            })
    return pairs


def compute_metrics(errors):
    """Compute MAE, RMSE, bias from a list of (predicted - actual) errors."""
    if not errors:
        return {"mae": None, "rmse": None, "bias": None, "n": 0}
    n = len(errors)
    return {
        "mae": sum(abs(e) for e in errors) / n,
        "rmse": math.sqrt(sum(e ** 2 for e in errors) / n),
        "bias": sum(errors) / n,
        "n": n,
    }


def _fmt(val, fmt=".2f"):
    return f"{val:{fmt}}" if val is not None else "---"


def run_forecast_eval(db_path=DB_PATH):
    console = Console()
    conn = init_db(db_path)
    pairs = pair_forecasts_with_actuals(conn, limit=2000)
    conn.close()

    if not pairs:
        console.print("[yellow]No forecast-actual pairs found in database.[/yellow]")
        console.print("Run the pipeline a few times first: python run_pipeline.py")
        return None

    console.print(f"\n[bold]Level 1B — Forecast Accuracy Eval[/bold]")
    console.print(f"Paired records: {len(pairs)}\n")

    # Overall by variable
    variables = [
        ("temperature", "forecast_temp", "actual_temp"),
        ("humidity", "forecast_humidity", "actual_humidity"),
        ("wind_speed", "forecast_wind", "actual_wind"),
        ("rainfall", "forecast_rain", "actual_rain"),
    ]
    overall = {}
    tbl = Table(title="Overall Forecast Accuracy")
    tbl.add_column("Variable", style="bold")
    tbl.add_column("N", justify="right")
    tbl.add_column("MAE", justify="right")
    tbl.add_column("RMSE", justify="right")
    tbl.add_column("Bias", justify="right")
    for vname, fk, ak in variables:
        errors = [p[fk] - p[ak] for p in pairs
                  if p[fk] is not None and p[ak] is not None]
        m = compute_metrics(errors)
        overall[vname] = m
        tbl.add_row(vname, str(m["n"]), _fmt(m["mae"]), _fmt(m["rmse"]),
                     _fmt(m["bias"], "+.2f") if m["bias"] is not None else "---")
    console.print(tbl)

    # By model type (temperature only)
    model_types = sorted(set(p["model_used"] for p in pairs))
    by_model = {}
    tbl2 = Table(title="\nTemperature Accuracy by Model Type")
    tbl2.add_column("Model", style="bold")
    tbl2.add_column("N", justify="right")
    tbl2.add_column("MAE (C)", justify="right")
    tbl2.add_column("RMSE (C)", justify="right")
    tbl2.add_column("Bias (C)", justify="right")
    for mt in model_types:
        errors = [p["forecast_temp"] - p["actual_temp"]
                  for p in pairs if p["model_used"] == mt
                  and p["forecast_temp"] is not None and p["actual_temp"] is not None]
        m = compute_metrics(errors)
        by_model[mt] = m
        tbl2.add_row(mt, str(m["n"]), _fmt(m["mae"]), _fmt(m["rmse"]),
                     _fmt(m["bias"], "+.2f") if m["bias"] is not None else "---")
    console.print(tbl2)

    # NWP vs MOS comparison
    nwp_errors = [p["nwp_temp"] - p["actual_temp"] for p in pairs
                  if p["nwp_temp"] is not None and p["actual_temp"] is not None]
    mos_errors = [p["forecast_temp"] - p["actual_temp"] for p in pairs
                  if p["nwp_temp"] is not None and p["forecast_temp"] is not None
                  and p["actual_temp"] is not None]
    nwp_m, mos_m = compute_metrics(nwp_errors), compute_metrics(mos_errors)

    console.print(f"\n[bold]NWP vs MOS-Corrected (temperature)[/bold]")
    console.print(f"  Raw NWP:       MAE={_fmt(nwp_m['mae'])}C  "
                  f"RMSE={_fmt(nwp_m['rmse'])}C  (n={nwp_m['n']})")
    console.print(f"  MOS-Corrected: MAE={_fmt(mos_m['mae'])}C  "
                  f"RMSE={_fmt(mos_m['rmse'])}C  (n={mos_m['n']})")
    if nwp_m["mae"] and mos_m["mae"]:
        imp = (nwp_m["mae"] - mos_m["mae"]) / nwp_m["mae"] * 100
        console.print(f"  MOS improvement: {imp:+.1f}% MAE reduction")

    # By station
    stations = sorted(set(p["station_id"] for p in pairs))
    by_station = {}
    tbl3 = Table(title="\nTemperature Accuracy by Station")
    tbl3.add_column("Station", style="bold")
    tbl3.add_column("N", justify="right")
    tbl3.add_column("MAE (C)", justify="right")
    tbl3.add_column("RMSE (C)", justify="right")
    tbl3.add_column("Bias (C)", justify="right")
    for sid in stations:
        errors = [p["forecast_temp"] - p["actual_temp"]
                  for p in pairs if p["station_id"] == sid
                  and p["forecast_temp"] is not None and p["actual_temp"] is not None]
        m = compute_metrics(errors)
        by_station[sid] = m
        if m["n"] > 0:
            tbl3.add_row(sid, str(m["n"]), _fmt(m["mae"]), _fmt(m["rmse"]),
                         _fmt(m["bias"], "+.2f") if m["bias"] is not None else "---")
    console.print(tbl3)

    # Save
    os.makedirs(RESULTS_DIR, exist_ok=True)
    results = {
        "eval_name": "forecast",
        "timestamp": datetime.utcnow().isoformat(),
        "total_pairs": len(pairs),
        "overall": overall,
        "by_model": by_model,
        "nwp_vs_mos": {"nwp": nwp_m, "mos": mos_m},
        "by_station": by_station,
    }
    out = os.path.join(RESULTS_DIR, "forecast.json")
    with open(out, "w") as f:
        json.dump(results, f, indent=2, default=str)
    console.print(f"\n[dim]Results saved to {out}[/dim]")
    return results


@pytest.mark.slow
@pytest.mark.offline
def test_eval_forecast():
    """Pytest wrapper for standalone eval script."""
    results = run_forecast_eval()
    assert results is not None


if __name__ == "__main__":
    run_forecast_eval()
