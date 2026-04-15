"""CRUD helpers for the agricultural_alerts and personalized_advisories tables."""

from __future__ import annotations
import json
from typing import Any, Dict, List

from src.database._util import _rows_to_dicts


def insert_alert(conn: Any, record: Dict[str, Any]) -> None:
    # crop_sms is a dict in memory {lang: {crop: sms}} but stored as a JSON
    # string in the VARCHAR column. Callers either pass a dict or nothing.
    crop_sms_raw = record.get("crop_sms")
    crop_sms_str = (
        json.dumps(crop_sms_raw, ensure_ascii=False)
        if isinstance(crop_sms_raw, dict) and crop_sms_raw
        else None
    )
    conn.execute(
        """INSERT INTO agricultural_alerts
           (id, station_id, farmer_lat, farmer_lon, issued_at, condition,
            advisory_en, advisory_local, sms_en, sms_local, crop_sms,
            language, provider, retrieval_docs, forecast_days)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT (id) DO NOTHING""",
        [record["id"], record["station_id"],
         record.get("farmer_lat"), record.get("farmer_lon"),
         record["issued_at"], record.get("condition"),
         record.get("advisory_en"), record.get("advisory_local"),
         record.get("sms_en"), record.get("sms_local"), crop_sms_str,
         record.get("language", "en"), record.get("provider", "unknown"),
         record.get("retrieval_docs", 0),
         record.get("forecast_days", 1)],
    )


def get_recent_alerts(conn: Any,
                       limit: int = 50) -> List[Dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM agricultural_alerts ORDER BY issued_at DESC LIMIT ?", [limit]
    ).fetchall()
    return _rows_to_dicts(conn, rows)


def insert_personalized_advisory(conn: Any, record: Dict[str, Any]) -> None:
    """Insert a per-farmer personalized advisory generated from a station draft."""
    conn.execute(
        """INSERT INTO personalized_advisories
           (id, alert_id, station_id, farmer_phone, farmer_name,
            crops, soil_type, irrigation_type, area_hectares,
            advisory_en, advisory_local, sms_en, sms_local,
            language, model, tokens_in, tokens_out, cache_read)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT (id) DO NOTHING""",
        [record["id"], record["alert_id"], record["station_id"],
         record["farmer_phone"], record.get("farmer_name"),
         record.get("crops"), record.get("soil_type"),
         record.get("irrigation_type"), record.get("area_hectares"),
         record.get("advisory_en"), record.get("advisory_local"),
         record.get("sms_en"), record.get("sms_local"),
         record.get("language", "en"), record.get("model", ""),
         record.get("tokens_in", 0), record.get("tokens_out", 0),
         record.get("cache_read", 0)],
    )


def get_personalized_advisories(conn: Any, station_id: str | None = None,
                                  limit: int = 50) -> List[Dict[str, Any]]:
    if station_id:
        rows = conn.execute(
            """SELECT * FROM personalized_advisories
               WHERE station_id = ?
               ORDER BY generated_at DESC LIMIT ?""",
            [station_id, limit],
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM personalized_advisories ORDER BY generated_at DESC LIMIT ?",
            [limit],
        ).fetchall()
    return _rows_to_dicts(conn, rows)
