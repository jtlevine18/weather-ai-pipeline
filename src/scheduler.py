"""APScheduler wrapper for recurring pipeline runs."""

from __future__ import annotations
import asyncio
import logging
from typing import Optional

log = logging.getLogger(__name__)


class PipelineScheduler:
    def __init__(self, config, interval_minutes: int = 60,
                  live_delivery: bool = False):
        self.config           = config
        self.interval_minutes = interval_minutes
        self.live_delivery    = live_delivery
        self._scheduler       = None

    def _run_pipeline(self):
        from src.pipeline import WeatherPipeline
        pipeline = WeatherPipeline(self.config, self.live_delivery)
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(pipeline.run())
            log.info("Scheduled run complete: %s", result)
        except Exception as exc:
            log.error("Scheduled run failed: %s", exc)
        finally:
            try:
                loop.close()
            except Exception:
                pass

    def start(self):
        try:
            from apscheduler.schedulers.background import BackgroundScheduler
            self._scheduler = BackgroundScheduler()
            self._scheduler.add_job(
                self._run_pipeline,
                "interval",
                minutes=self.interval_minutes,
                id="weather_pipeline",
            )
            self._scheduler.start()
            log.info("Pipeline scheduler started: every %d minutes",
                     self.interval_minutes)
        except ImportError:
            log.warning("apscheduler not installed — scheduler disabled")

    def stop(self):
        if self._scheduler:
            try:
                self._scheduler.shutdown(wait=False)
            except Exception:
                pass
