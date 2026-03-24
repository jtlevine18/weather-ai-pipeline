"""Station health monitor — detects stale data and offline stations."""

from __future__ import annotations
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List

from rich.console import Console
from rich.table   import Table

from config import STATIONS, STATION_MAP
from src.database import get_station_health

log     = logging.getLogger(__name__)
console = Console()

STALE_THRESHOLD_HOURS = 2


class StationMonitor:
    def __init__(self, stale_hours: int = STALE_THRESHOLD_HOURS):
        self.stale_hours = stale_hours

    def check_all(self) -> List[Dict[str, Any]]:
        """Return health status for all stations."""
        from src.database import init_db
        conn    = init_db()
        health  = {r["station_id"]: r for r in get_station_health(conn)}
        now     = datetime.utcnow()
        cutoff  = now - timedelta(hours=self.stale_hours)
        results = []

        for station in STATIONS:
            sid    = station.station_id
            record = health.get(sid)

            if record is None:
                status = "never_seen"
            else:
                try:
                    last = datetime.fromisoformat(str(record["last_seen"]).replace("Z",""))
                    status = "ok" if last >= cutoff else "stale"
                except Exception:
                    status = "unknown"

            results.append({
                "station_id":   sid,
                "name":         station.name,
                "state":        station.state,
                "status":       status,
                "last_seen":    record["last_seen"] if record else None,
                "record_count": record["record_count"] if record else 0,
                "avg_quality":  record["avg_quality"] if record else None,
            })

        return results

    def print_table(self):
        statuses = self.check_all()
        table = Table(title="Station Health Monitor", show_lines=True)
        table.add_column("ID",          style="dim")
        table.add_column("Name")
        table.add_column("State")
        table.add_column("Status")
        table.add_column("Last Seen")
        table.add_column("Records")
        table.add_column("Avg Quality")

        for s in statuses:
            color = {"ok": "green", "stale": "yellow",
                     "never_seen": "red", "unknown": "dim"}.get(s["status"], "white")
            table.add_row(
                s["station_id"],
                s["name"],
                s["state"],
                f"[{color}]{s['status']}[/{color}]",
                str(s["last_seen"] or "—"),
                str(s["record_count"]),
                f"{s['avg_quality']:.2f}" if s["avg_quality"] else "—",
            )

        console.print(table)
