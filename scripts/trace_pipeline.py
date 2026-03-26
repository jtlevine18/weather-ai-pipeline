#!/usr/bin/env python3
"""
Step-by-step pipeline demo showing data at each boundary.
Useful for understanding what each step does to the data.

Usage:
    python trace_pipeline.py           # interactive (pauses between steps)
    python trace_pipeline.py --no-pause  # non-interactive (CI/bash)
"""

import argparse
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from rich.console import Console
from rich.panel   import Panel
from rich.syntax  import Syntax
from rich.table   import Table

console = Console()


def _show_records(title: str, records, max_show: int = 3):
    if not records:
        console.print(f"[yellow]  (no {title} records)[/yellow]")
        return
    sample = records[:max_show]
    # Pretty-print first record
    console.print(f"\n[bold]Sample {title} ({len(records)} total, showing {len(sample)}):[/bold]")
    for r in sample:
        clean = {k: v for k, v in r.items()
                 if v is not None and k not in ("created_at",)}
        console.print(Syntax(json.dumps(clean, indent=2, default=str),
                              "json", theme="monokai", line_numbers=False))


def _pause(interactive: bool, message: str = "Press Enter to continue..."):
    if interactive:
        try:
            input(f"\n[dim]{message}[/dim] ")
        except EOFError:
            pass
    else:
        console.print(f"\n[dim]--- {message} ---[/dim]")


async def trace(interactive: bool = True):
    from config import get_config, STATIONS, STATION_MAP
    from src.database import (init_db, get_recent_forecasts, get_recent_alerts,
                               get_all_clean_telemetry)
    from src.weather_clients import TomorrowIOClient, OpenMeteoClient, NASAPowerClient
    from src.healing         import RuleBasedFallback
    from src.forecasting     import create_forecast_model, PersistenceModel, run_forecast_step
    from src.downscaling     import IDWDownscaler
    from src.translation     import get_provider, generate_advisory
    from src.ingestion       import ingest_all_stations, generate_synthetic_reading

    config = get_config()
    conn   = init_db(":memory:")  # use in-memory DB for trace

    console.rule("[bold cyan]PIPELINE TRACE[/bold cyan]")
    console.print("This demo shows data at each step boundary.\n")

    # ---- Step 1 ----
    mode = config.weather.ingestion_source
    label = "Real IMD" if mode == "real" else "Synthetic Generator"
    console.rule(f"[bold blue]Step 1: Ingest ({label})[/bold blue]")
    console.print(f"Ingesting {mode} readings for 20 stations...")
    raw = await ingest_all_stations(config, conn)
    faults = [(r["station_id"], r["fault_type"]) for r in raw if r.get("fault_type")]
    console.print(f"  Generated {len(raw)} readings, {len(faults)} faults:")
    for sid, ft in faults[:5]:
        console.print(f"    [yellow]{sid}[/yellow]: fault_type=[red]{ft}[/red]")
    _show_records("raw_telemetry", raw)
    _pause(interactive, "Step 1 done → Step 2")

    # ---- Step 2 ----
    console.rule("[bold blue]Step 2: Heal (Tomorrow.io reference)[/bold blue]")
    from src.pipeline import WeatherPipeline
    pipeline = WeatherPipeline(config)
    pipeline.conn = conn
    clean = await pipeline.step_heal(raw)
    healed = [r for r in clean if r.get("heal_action") != "none"]
    console.print(f"  Clean: {len(clean)}, Healed: {len(healed)}")
    _show_records("clean_telemetry (healed)", healed)
    _pause(interactive, "Step 2 done → Step 3")

    # ---- Step 3 ----
    console.rule("[bold blue]Step 3: Forecast (Open-Meteo NWP + XGBoost)[/bold blue]")
    forecasts = await pipeline.step_forecast()
    mos = [f for f in forecasts if f.get("model_used") == "hybrid_mos"]
    console.print(f"  Forecasts: {len(forecasts)}, MOS: {len(mos)}, Persistence: {len(forecasts)-len(mos)}")
    _show_records("forecasts", forecasts)
    _pause(interactive, "Step 3 done → Step 4")

    # ---- Step 4 ----
    console.rule("[bold blue]Step 4: Downscale (NASA POWER IDW)[/bold blue]")
    downscaled = await pipeline.step_downscale(forecasts)
    ds_count = sum(1 for f in downscaled if f.get("downscaled"))
    console.print(f"  Downscaled: {ds_count}/{len(downscaled)}")
    # Show one with delta
    for f in downscaled:
        if f.get("downscaled") and f.get("lapse_delta"):
            console.print(f"  [green]{f['station_id']}[/green]: "
                          f"station_temp={f.get('nwp_temp'):.1f}°C → "
                          f"farmer_temp={f.get('temperature'):.1f}°C "
                          f"(lapse_delta={f['lapse_delta']:.2f}°C, "
                          f"alt_delta={f.get('alt_delta_m'):.0f}m)")
            break
    _pause(interactive, "Step 4 done → Step 5")

    # ---- Step 5 ----
    console.rule("[bold blue]Step 5: Translate (RAG + Claude)[/bold blue]")
    alerts = await pipeline.step_translate(downscaled)
    rag = [a for a in alerts if a.get("provider") == "rag_claude"]
    console.print(f"  Alerts: {len(alerts)}, RAG+Claude: {len(rag)}, Rule-based: {len(alerts)-len(rag)}")
    for alert in alerts[:2]:
        console.print(Panel(
            f"[bold]{alert['station_id']}[/bold] | {alert.get('condition')} | lang={alert.get('language')}\n"
            f"[green]EN:[/green] {alert.get('advisory_en', '')[:120]}\n"
            f"[cyan]LOCAL:[/cyan] {alert.get('advisory_local', '')[:120]}",
            title="Advisory Sample",
        ))
    _pause(interactive, "Step 5 done → Step 6")

    # ---- Step 6 ----
    console.rule("[bold blue]Step 6: Deliver (Console + dry-run SMS)[/bold blue]")
    await pipeline.step_deliver(alerts)
    console.rule("[bold green]Trace complete![/bold green]")


def main():
    parser = argparse.ArgumentParser(description="Pipeline trace demo")
    parser.add_argument("--no-pause", action="store_true",
                        help="Non-interactive mode (no input() calls)")
    args = parser.parse_args()
    asyncio.run(trace(interactive=not args.no_pause))


if __name__ == "__main__":
    main()
