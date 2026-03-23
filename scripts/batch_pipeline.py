#!/usr/bin/env python3
"""
Run the pipeline N times to accumulate training data for MOS model.

Usage:
    python scripts/batch_pipeline.py             # default 10 runs
    python scripts/batch_pipeline.py --runs 20   # 20 runs
"""

import argparse
import asyncio
import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from rich.console import Console
from rich.logging import RichHandler
from rich.table import Table

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[RichHandler(rich_tracebacks=True, show_path=False)],
)
log = logging.getLogger(__name__)
console = Console()


def parse_args():
    parser = argparse.ArgumentParser(description="Batch pipeline runner for data accumulation")
    parser.add_argument("--runs", type=int, default=10, help="Number of pipeline runs (default: 10)")
    parser.add_argument("--db", default="weather.duckdb", help="DuckDB path")
    return parser.parse_args()


async def main():
    args = parse_args()
    from config import get_config
    config = get_config()
    config.db_path = args.db

    console.rule(f"[bold cyan]Batch Pipeline: {args.runs} runs[/bold cyan]")

    results = []
    for i in range(args.runs):
        console.print(f"\n[bold]--- Run {i+1}/{args.runs} ---[/bold]")
        from src.pipeline import WeatherPipeline
        pipeline = WeatherPipeline(config)
        try:
            result = await pipeline.run()
            results.append(result)
        except Exception as exc:
            log.error("Run %d failed: %s", i + 1, exc)
            results.append({"status": "failed", "error": str(exc)})

    # Summary
    console.rule("[bold cyan]Batch Summary[/bold cyan]")
    ok = sum(1 for r in results if r.get("status") in ("ok", "partial"))
    console.print(f"Completed: {ok}/{args.runs} runs succeeded")

    # Table counts
    import duckdb
    conn = duckdb.connect(args.db, read_only=True)
    tables = ["raw_telemetry", "clean_telemetry", "forecasts",
              "agricultural_alerts", "delivery_log"]
    summary = Table(title="Table Record Counts")
    summary.add_column("Table")
    summary.add_column("Total Records", justify="right")
    for t in tables:
        try:
            count = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        except Exception:
            count = 0
        summary.add_row(t, str(count))
    console.print(summary)

    # Per-station counts in clean_telemetry
    try:
        rows = conn.execute("""
            SELECT station_id, COUNT(*) as n
            FROM clean_telemetry
            GROUP BY station_id
            ORDER BY station_id
        """).fetchall()
        station_table = Table(title="Clean Telemetry per Station")
        station_table.add_column("Station")
        station_table.add_column("Records", justify="right")
        for sid, n in rows:
            station_table.add_row(sid, str(n))
        console.print(station_table)
    except Exception:
        pass

    conn.close()
    console.rule("[bold green]Done[/bold green]")


if __name__ == "__main__":
    asyncio.run(main())
