"""Singleton daily pipeline scheduler — runs inside the Streamlit process on HF Spaces.

Toggle on/off from the System → Scheduler tab. State persists in scheduler_state.json
so the scheduler auto-resumes after HF Spaces restarts.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from pathlib import Path

log = logging.getLogger(__name__)

_STATE_PATH = Path(__file__).resolve().parent.parent / "scheduler_state.json"
_scheduler = None
_lock = threading.Lock()


# ---------------------------------------------------------------------------
# State persistence
# ---------------------------------------------------------------------------

def _read_state() -> dict:
    try:
        return json.loads(_STATE_PATH.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {"enabled": False}


def _write_state(enabled: bool) -> None:
    _STATE_PATH.write_text(json.dumps({"enabled": enabled}, indent=2) + "\n")


def is_enabled() -> bool:
    return _read_state().get("enabled", False)


# ---------------------------------------------------------------------------
# Pipeline execution (runs in background thread)
# ---------------------------------------------------------------------------

def _run_pipeline() -> None:
    from config import get_config
    from src.pipeline import WeatherPipeline

    try:
        config = get_config()
        pipeline = WeatherPipeline(config)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(pipeline.run())
        log.info("Daily scheduled run complete: %s", result.get("status"))
    except Exception as exc:
        log.error("Daily scheduled run failed: %s", exc)
    finally:
        try:
            loop.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Scheduler lifecycle
# ---------------------------------------------------------------------------

def start() -> bool:
    """Start the daily scheduler. Returns True if started, False if already running."""
    global _scheduler
    with _lock:
        if _scheduler is not None:
            return False
        try:
            from apscheduler.schedulers.background import BackgroundScheduler
            from apscheduler.triggers.cron import CronTrigger

            _scheduler = BackgroundScheduler(daemon=True)
            _scheduler.add_job(
                _run_pipeline,
                CronTrigger(hour=0, minute=30),  # 00:30 UTC = 06:00 IST
                id="daily_pipeline",
                replace_existing=True,
            )
            _scheduler.start()
            _write_state(True)
            log.info("Daily scheduler started (06:00 IST / 00:30 UTC)")
            return True
        except ImportError:
            log.warning("apscheduler not installed — daily scheduler unavailable")
            return False


def stop() -> None:
    """Stop the daily scheduler."""
    global _scheduler
    with _lock:
        if _scheduler is not None:
            try:
                _scheduler.shutdown(wait=False)
            except Exception:
                pass
            _scheduler = None
        _write_state(False)
        log.info("Daily scheduler stopped")


def is_running() -> bool:
    return _scheduler is not None


def next_run_time():
    """Return the next scheduled run time, or None."""
    if _scheduler is None:
        return None
    try:
        job = _scheduler.get_job("daily_pipeline")
        return job.next_run_time if job else None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Auto-resume on import (covers HF Spaces restarts)
# ---------------------------------------------------------------------------
if is_enabled():
    start()
