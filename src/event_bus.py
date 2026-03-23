"""
File-based event bus.

Events are JSON files written to an events directory.  Handlers subscribe
to event types and are dispatched when new matching files appear during
polling.  Processed files are moved to events/processed/.
"""

import glob
import json
import os
import shutil
import time
from datetime import datetime, timezone
from typing import Callable


class EventBus:
    """Publish / subscribe over a shared filesystem directory."""

    def __init__(self, events_dir: str = "events"):
        self.events_dir = events_dir
        self._handlers: dict[str, list[Callable]] = {}
        os.makedirs(self.events_dir, exist_ok=True)

    # ------------------------------------------------------------------
    # Publish
    # ------------------------------------------------------------------
    def publish(self, event_type: str, payload: dict) -> str:
        """Write an event file and return its path.

        Filename pattern: ``{event_type}.{iso-timestamp}.json``
        """
        now = datetime.now(timezone.utc)
        ts = now.strftime("%Y%m%dT%H%M%S%f")
        filename = f"{event_type}.{ts}.json"
        path = os.path.join(self.events_dir, filename)

        event = {
            "event_type": event_type,
            "timestamp": now.isoformat(),
            "payload": payload,
        }
        with open(path, "w") as f:
            json.dump(event, f, indent=2)
        return path

    # ------------------------------------------------------------------
    # Subscribe
    # ------------------------------------------------------------------
    def subscribe(self, event_type: str, handler: Callable):
        """Register *handler* to be called when events of *event_type* appear."""
        self._handlers.setdefault(event_type, []).append(handler)

    # ------------------------------------------------------------------
    # Poll
    # ------------------------------------------------------------------
    def poll(self, interval_seconds: int = 5, once: bool = False):
        """Watch events dir for new files and dispatch to handlers.

        Set *once=True* to do a single pass (useful for testing).
        """
        processed_dir = os.path.join(self.events_dir, "processed")
        os.makedirs(processed_dir, exist_ok=True)

        while True:
            pattern = os.path.join(self.events_dir, "*.json")
            for filepath in sorted(glob.glob(pattern)):
                try:
                    with open(filepath, "r") as f:
                        event = json.load(f)
                except (json.JSONDecodeError, OSError):
                    continue

                event_type = event.get("event_type", "")
                for handler in self._handlers.get(event_type, []):
                    handler(event)

                # Move to processed
                dest = os.path.join(processed_dir, os.path.basename(filepath))
                shutil.move(filepath, dest)

            if once:
                break
            time.sleep(interval_seconds)

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------
    def get_recent(self, event_type: str, limit: int = 10) -> list[dict]:
        """Return recent events of *event_type* from both live and processed dirs."""
        results: list[dict] = []
        search_dirs = [
            self.events_dir,
            os.path.join(self.events_dir, "processed"),
        ]
        for d in search_dirs:
            pattern = os.path.join(d, f"{event_type}.*.json")
            for filepath in glob.glob(pattern):
                try:
                    with open(filepath, "r") as f:
                        results.append(json.load(f))
                except (json.JSONDecodeError, OSError):
                    continue
        # Sort newest first and trim
        results.sort(key=lambda e: e.get("timestamp", ""), reverse=True)
        return results[:limit]


# ------------------------------------------------------------------
# Demo
# ------------------------------------------------------------------
if __name__ == "__main__":
    bus = EventBus()

    # Register a simple handler
    def on_test(event: dict):
        print(f"[handler] received: {json.dumps(event, indent=2)}")

    bus.subscribe("test", on_test)

    # Publish a test event
    path = bus.publish("test", {"message": "hello from event bus"})
    print(f"Published test event to {path}")

    # Single poll pass to pick it up
    bus.poll(once=True)
    print("Poll complete.")
