"""CRUD helpers for delivery_log and delivery_metrics tables."""

from __future__ import annotations
from typing import Any, Dict


def insert_delivery_log(conn: Any, record: Dict[str, Any]) -> None:
    conn.execute(
        """INSERT INTO delivery_log
           (id, alert_id, station_id, channel, recipient, status, message)
           VALUES (?,?,?,?,?,?,?)
           ON CONFLICT (id) DO NOTHING""",
        [record["id"], record.get("alert_id"), record.get("station_id"),
         record.get("channel"), record.get("recipient"),
         record.get("status", "sent"), record.get("message", "")],
    )


def insert_delivery_metrics(conn: Any,
                              record: Dict[str, Any]) -> None:
    conn.execute(
        """INSERT INTO delivery_metrics
           (id, pipeline_run_id, station_id, forecasts_generated,
            advisories_generated, deliveries_attempted, deliveries_succeeded,
            channels_used)
           VALUES (?,?,?,?,?,?,?,?)
           ON CONFLICT (id) DO NOTHING""",
        [record["id"], record.get("pipeline_run_id"), record["station_id"],
         record.get("forecasts_generated", 0), record.get("advisories_generated", 0),
         record.get("deliveries_attempted", 0), record.get("deliveries_succeeded", 0),
         record.get("channels_used")],
    )
