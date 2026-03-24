#!/usr/bin/env python3
"""Station health monitor CLI.

Usage:
    python run_monitor.py
    python run_monitor.py --watch 30   # refresh every 30s
"""

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))

from rich.console import Console
console = Console()


def parse_args():
    p = argparse.ArgumentParser(description="Station health monitor")
    p.add_argument("--watch", type=int, metavar="SECONDS",
                   help="Refresh every N seconds")
    return p.parse_args()


def main():
    args = parse_args()
    from src.monitor import StationMonitor
    monitor = StationMonitor()

    if args.watch:
        try:
            while True:
                console.clear()
                monitor.print_table()
                console.print(f"\n[dim]Refreshing every {args.watch}s — Ctrl+C to stop[/dim]")
                time.sleep(args.watch)
        except KeyboardInterrupt:
            pass
    else:
        monitor.print_table()


if __name__ == "__main__":
    main()
