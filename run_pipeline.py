#!/usr/bin/env python3
"""
Main CLI entry point for the Kerala/Tamil Nadu weather pipeline.

Usage:
    python run_pipeline.py                    # Single run (NeuralGCM + Open-Meteo fallback)
    python run_pipeline.py --no-neuralgcm     # Open-Meteo only (no GPU needed)
    python run_pipeline.py --live-delivery    # Enable real SMS
    python run_pipeline.py --schedule 60      # Run every 60 minutes
    python run_pipeline.py --step 1           # Run only step 1
"""

import argparse
import asyncio
import logging
import sys
import os

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(__file__))

from rich.logging import RichHandler

_log_level = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, _log_level, logging.INFO),
    format="%(message)s",
    handlers=[RichHandler(rich_tracebacks=True, show_path=False)],
)
log = logging.getLogger(__name__)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Kerala/Tamil Nadu Weather Forecasting Pipeline"
    )
    parser.add_argument("--live-delivery", action="store_true",
                        help="Actually send SMS/WhatsApp (default: dry-run)")
parser.add_argument("--step", type=int, choices=range(1, 7),
                        metavar="N", help="Run only step N (1-6)")
    parser.add_argument("--source", choices=["real", "synthetic"],
                        default="real",
                        help="Data source for Step 1 ingestion (default: real)")
    parser.add_argument("--no-neuralgcm", action="store_true",
                        help="Disable NeuralGCM and use Open-Meteo only")
    parser.add_argument("--verbose", "-v", action="store_true")
    return parser.parse_args()


async def run_once(config, live_delivery: bool):
    from src.pipeline import WeatherPipeline
    pipeline = WeatherPipeline(config, live_delivery=live_delivery)
    return await pipeline.run()


def main():
    args = parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    from config import get_config
    config = get_config()
    config.weather.ingestion_source = args.source
    if args.no_neuralgcm:
        config.neuralgcm.enabled = False

    result = asyncio.run(run_once(config, args.live_delivery))
    sys.exit(0 if result.get("status") in ("ok", "partial") else 1)


if __name__ == "__main__":
    main()
