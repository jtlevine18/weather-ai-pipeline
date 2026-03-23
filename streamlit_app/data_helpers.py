"""Shared database query helpers for Streamlit pages."""

from __future__ import annotations
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ---------------------------------------------------------------------------
# Inject Streamlit Cloud secrets into os.environ before anything reads them.
# On Streamlit Cloud, API keys are stored in the Secrets manager (not .env).
# This is a no-op locally when .env is already loaded by config.py.
# ---------------------------------------------------------------------------
def _inject_cloud_secrets() -> None:
    try:
        import streamlit as st
        for key in ("ANTHROPIC_API_KEY", "TOMORROW_IO_API_KEY",
                    "TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN"):
            if key in st.secrets and not os.environ.get(key):
                os.environ[key] = st.secrets[key]
    except Exception:
        pass

_inject_cloud_secrets()

import duckdb
import pandas as pd
from typing import Any, Dict, List, Optional

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "weather.duckdb")


def get_conn():
    return duckdb.connect(DB_PATH, read_only=True)


def table_exists(conn, name: str) -> bool:
    try:
        conn.execute(f"SELECT 1 FROM {name} LIMIT 1")
        return True
    except Exception:
        return False


def load_forecasts(limit: int = 200) -> pd.DataFrame:
    try:
        conn = get_conn()
        if not table_exists(conn, "forecasts"):
            return pd.DataFrame()
        df = conn.execute(
            "SELECT * FROM forecasts ORDER BY issued_at DESC LIMIT ?", [limit]
        ).df()
        conn.close()
        return df
    except Exception:
        return pd.DataFrame()


def load_alerts(limit: int = 100) -> pd.DataFrame:
    try:
        conn = get_conn()
        if not table_exists(conn, "agricultural_alerts"):
            return pd.DataFrame()
        df = conn.execute(
            "SELECT * FROM agricultural_alerts ORDER BY issued_at DESC LIMIT ?", [limit]
        ).df()
        conn.close()
        return df
    except Exception:
        return pd.DataFrame()


def load_clean_telemetry(limit: int = 500) -> pd.DataFrame:
    try:
        conn = get_conn()
        if not table_exists(conn, "clean_telemetry"):
            return pd.DataFrame()
        df = conn.execute(
            "SELECT * FROM clean_telemetry ORDER BY ts DESC LIMIT ?", [limit]
        ).df()
        conn.close()
        return df
    except Exception:
        return pd.DataFrame()


def load_raw_telemetry(limit: int = 200) -> pd.DataFrame:
    try:
        conn = get_conn()
        if not table_exists(conn, "raw_telemetry"):
            return pd.DataFrame()
        df = conn.execute(
            "SELECT * FROM raw_telemetry ORDER BY ts DESC LIMIT ?", [limit]
        ).df()
        conn.close()
        return df
    except Exception:
        return pd.DataFrame()


def load_delivery_log(limit: int = 100) -> pd.DataFrame:
    try:
        conn = get_conn()
        if not table_exists(conn, "delivery_log"):
            return pd.DataFrame()
        df = conn.execute(
            "SELECT * FROM delivery_log ORDER BY delivered_at DESC LIMIT ?", [limit]
        ).df()
        conn.close()
        return df
    except Exception:
        return pd.DataFrame()


def load_pipeline_runs(limit: int = 20) -> pd.DataFrame:
    try:
        conn = get_conn()
        if not table_exists(conn, "pipeline_runs"):
            return pd.DataFrame()
        df = conn.execute(
            "SELECT * FROM pipeline_runs ORDER BY started_at DESC LIMIT ?", [limit]
        ).df()
        conn.close()
        return df
    except Exception:
        return pd.DataFrame()


def load_station_health() -> pd.DataFrame:
    try:
        conn = get_conn()
        if not table_exists(conn, "clean_telemetry"):
            return pd.DataFrame()
        df = conn.execute("""
            SELECT station_id,
                   MAX(ts) as last_seen,
                   COUNT(*) as record_count,
                   AVG(quality_score) as avg_quality,
                   SUM(CASE WHEN heal_action != 'none' THEN 1 ELSE 0 END) as healed_count
            FROM clean_telemetry
            GROUP BY station_id
        """).df()
        conn.close()
        return df
    except Exception:
        return pd.DataFrame()


def get_station_coords() -> pd.DataFrame:
    """Return all stations with lat/lon for map display."""
    from config import STATIONS
    return pd.DataFrame([{
        "station_id": s.station_id,
        "name":       s.name,
        "state":      s.state,
        "lat":        s.lat,
        "lon":        s.lon,
        "altitude_m": s.altitude_m,
        "crop":       s.crop_context,
    } for s in STATIONS])


def load_conversation_log(limit: int = 200) -> pd.DataFrame:
    try:
        conn = get_conn()
        if not table_exists(conn, "conversation_log"):
            return pd.DataFrame()
        df = conn.execute(
            "SELECT * FROM conversation_log ORDER BY created_at DESC LIMIT ?", [limit]
        ).df()
        conn.close()
        return df
    except Exception:
        return pd.DataFrame()


def load_delivery_metrics(limit: int = 500) -> pd.DataFrame:
    try:
        conn = get_conn()
        if not table_exists(conn, "delivery_metrics"):
            return pd.DataFrame()
        df = conn.execute(
            "SELECT * FROM delivery_metrics ORDER BY created_at DESC LIMIT ?", [limit]
        ).df()
        conn.close()
        return df
    except Exception:
        return pd.DataFrame()


def load_eval_results() -> dict:
    """Load eval results from JSON files in tests/eval_results/."""
    import json as json_mod
    results_dir = os.path.join(os.path.dirname(__file__), "..", "tests", "eval_results")
    results = {}
    for name in ("healing", "forecast", "rag", "advisory", "translation", "dpi", "conversation"):
        path = os.path.join(results_dir, f"{name}.json")
        if os.path.exists(path):
            try:
                with open(path) as fh:
                    results[name] = json_mod.load(fh)
            except Exception:
                pass
    return results
