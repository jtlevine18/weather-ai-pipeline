"""CRUD helpers for the forecasts table."""

from __future__ import annotations
from typing import Any, Dict, Iterable, List, Optional, Tuple

from src.database._util import _rows_to_dicts


def insert_forecast(conn: Any, record: Dict[str, Any]) -> None:
    """Insert a forecast row.

    The 8 GenCast columns (rain_p10/p50/p90, rain_prob_1mm/5mm/15mm,
    ensemble_size, nwp_model_version) are optional keyword-equivalent keys on
    ``record`` and default to NULL. Existing callers that don't pass them
    continue to work unchanged — the schema keeps all new columns nullable.
    """
    conn.execute(
        """INSERT INTO forecasts
           (id, station_id, issued_at, valid_for_ts, temperature, humidity,
            wind_speed, rainfall, condition, model_used, nwp_source, nwp_temp,
            correction, confidence, forecast_day,
            rain_p10, rain_p50, rain_p90,
            rain_prob_1mm, rain_prob_5mm, rain_prob_15mm,
            ensemble_size, nwp_model_version)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT (id) DO NOTHING""",
        [record["id"], record["station_id"], record["issued_at"], record["valid_for_ts"],
         record.get("temperature"), record.get("humidity"), record.get("wind_speed"),
         record.get("rainfall"), record.get("condition", "clear"),
         record.get("model_used", "persistence"),
         record.get("nwp_source", "open_meteo"),
         record.get("nwp_temp"), record.get("correction", 0.0),
         record.get("confidence", 0.7),
         record.get("forecast_day", 0),
         record.get("rain_p10"), record.get("rain_p50"), record.get("rain_p90"),
         record.get("rain_prob_1mm"), record.get("rain_prob_5mm"), record.get("rain_prob_15mm"),
         record.get("ensemble_size"), record.get("nwp_model_version")],
    )


def update_forecast_downscaled(
    conn: Any,
    forecast_id: str,
    temperature: float,
    condition: str,
) -> None:
    """Update forecast row with downscaled (NASA POWER + lapse-rate) values.

    step_forecast inserts the raw GraphCast NWP temperature, which has a known
    cold bias at longer lead times (and a daily-max undershoot from sampling
    6h timesteps only). step_downscale then computes a station-local
    temperature from NASA POWER 5x5 IDW + lapse-rate correction that matches
    the recent observed climatology; this helper writes that corrected value
    back so the Vercel frontend / LMB consumers see the realistic number.
    """
    conn.execute(
        "UPDATE forecasts SET temperature = ?, condition = ? WHERE id = ?",
        [temperature, condition, forecast_id],
    )


def update_forecast_probabilistic(
    conn: Any,
    forecast_id: str,
    *,
    rain_p10: Optional[float] = None,
    rain_p50: Optional[float] = None,
    rain_p90: Optional[float] = None,
    rain_prob_1mm: Optional[float] = None,
    rain_prob_5mm: Optional[float] = None,
    rain_prob_15mm: Optional[float] = None,
    ensemble_size: Optional[int] = None,
    nwp_model_version: Optional[str] = None,
) -> None:
    """Update the GenCast probabilistic columns on an existing forecast row.

    Used by the pipeline after GenCast runs — the forecast row is already
    inserted by GraphCast; GenCast only enriches the probabilistic fields.
    """
    conn.execute(
        """UPDATE forecasts
              SET rain_p10          = ?,
                  rain_p50          = ?,
                  rain_p90          = ?,
                  rain_prob_1mm     = ?,
                  rain_prob_5mm     = ?,
                  rain_prob_15mm    = ?,
                  ensemble_size     = ?,
                  nwp_model_version = ?
            WHERE id = ?""",
        [rain_p10, rain_p50, rain_p90,
         rain_prob_1mm, rain_prob_5mm, rain_prob_15mm,
         ensemble_size, nwp_model_version,
         forecast_id],
    )


def insert_forecast_ensemble(
    conn: Any,
    forecast_id: str,
    members: Iterable[Tuple[int, float]],
) -> None:
    """Insert ensemble member rainfall values for one forecast.

    ``members`` is an iterable of ``(member_idx, rainfall_mm)`` tuples. The
    table has a composite primary key (forecast_id, member_idx); repeat inserts
    are a no-op via ON CONFLICT DO NOTHING so the call stays idempotent.
    """
    for member_idx, rainfall in members:
        conn.execute(
            """INSERT INTO forecast_ensembles (forecast_id, member_idx, rainfall)
               VALUES (?, ?, ?)
               ON CONFLICT (forecast_id, member_idx) DO NOTHING""",
            [forecast_id, member_idx, rainfall],
        )


def get_recent_forecasts(conn: Any,
                          limit: int = 100) -> List[Dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM forecasts ORDER BY issued_at DESC LIMIT ?", [limit]
    ).fetchall()
    return _rows_to_dicts(conn, rows)


def get_forecast_actuals(conn: Any,
                          limit: int = 1000) -> tuple:
    """Get forecasts and clean_telemetry separately for accuracy eval."""
    rows = conn.execute(
        "SELECT * FROM forecasts ORDER BY issued_at DESC LIMIT ?", [limit]
    ).fetchall()
    forecasts = _rows_to_dicts(conn, rows)
    if not forecasts:
        return [], []

    rows2 = conn.execute(
        "SELECT * FROM clean_telemetry ORDER BY ts DESC LIMIT ?", [limit * 2]
    ).fetchall()
    actuals = _rows_to_dicts(conn, rows2)
    return forecasts, actuals


def insert_gencast_temp_validation(
    conn: Any, rows: Iterable[Dict[str, Any]]
) -> None:
    """Bulk-insert GenCast temperature validation rows (scratch experiment).

    One row per (station, time_step, member). Idempotent — the row id is
    ``{target_date}_{station_id}_{step_idx}_{member_idx}`` so re-running the
    same pipeline against the same target_date is a no-op.
    """
    for row in rows:
        conn.execute(
            """INSERT INTO gencast_temp_validation
               (id, pipeline_run_id, station_id, station_lat, station_lon,
                target_date, forecast_day, time_step_idx, member_idx,
                temperature_c, model_version)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT (id) DO NOTHING""",
            [row["id"], row.get("pipeline_run_id"), row["station_id"],
             row.get("station_lat"), row.get("station_lon"),
             row.get("target_date"), row.get("forecast_day"),
             row["time_step_idx"], row["member_idx"],
             row.get("temperature_c"), row.get("model_version")],
        )
