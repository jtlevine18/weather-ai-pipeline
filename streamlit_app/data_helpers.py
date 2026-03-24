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
import streamlit as st
from contextlib import contextmanager
from typing import Any, Dict, List, Optional

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "weather.duckdb")


def get_conn():
    return duckdb.connect(DB_PATH, read_only=True)


@contextmanager
def _db():
    """Context manager that ensures conn.close() even on exceptions."""
    conn = get_conn()
    try:
        yield conn
    finally:
        conn.close()


def table_exists(conn, name: str) -> bool:
    try:
        conn.execute(f"SELECT 1 FROM {name} LIMIT 1")
        return True
    except Exception:
        return False


@st.cache_data(ttl=60)
def load_forecasts(limit: int = 200) -> pd.DataFrame:
    try:
        with _db() as conn:
            if not table_exists(conn, "forecasts"):
                return pd.DataFrame()
            return conn.execute(
                "SELECT * FROM forecasts ORDER BY issued_at DESC LIMIT ?", [limit]
            ).df()
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=60)
def load_alerts(limit: int = 100) -> pd.DataFrame:
    try:
        with _db() as conn:
            if not table_exists(conn, "agricultural_alerts"):
                return pd.DataFrame()
            return conn.execute(
                "SELECT * FROM agricultural_alerts ORDER BY issued_at DESC LIMIT ?", [limit]
            ).df()
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=60)
def load_clean_telemetry(limit: int = 500) -> pd.DataFrame:
    try:
        with _db() as conn:
            if not table_exists(conn, "clean_telemetry"):
                return pd.DataFrame()
            return conn.execute(
                "SELECT * FROM clean_telemetry ORDER BY ts DESC LIMIT ?", [limit]
            ).df()
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=60)
def load_raw_telemetry(limit: int = 200) -> pd.DataFrame:
    try:
        with _db() as conn:
            if not table_exists(conn, "raw_telemetry"):
                return pd.DataFrame()
            return conn.execute(
                "SELECT * FROM raw_telemetry ORDER BY ts DESC LIMIT ?", [limit]
            ).df()
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=60)
def load_delivery_log(limit: int = 100) -> pd.DataFrame:
    try:
        with _db() as conn:
            if not table_exists(conn, "delivery_log"):
                return pd.DataFrame()
            return conn.execute(
                "SELECT * FROM delivery_log ORDER BY delivered_at DESC LIMIT ?", [limit]
            ).df()
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=60)
def load_pipeline_runs(limit: int = 20) -> pd.DataFrame:
    try:
        with _db() as conn:
            if not table_exists(conn, "pipeline_runs"):
                return pd.DataFrame()
            return conn.execute(
                "SELECT * FROM pipeline_runs ORDER BY started_at DESC LIMIT ?", [limit]
            ).df()
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=60)
def load_station_health() -> pd.DataFrame:
    try:
        from config import STATIONS
        valid_ids = [s.station_id for s in STATIONS]
        with _db() as conn:
            if not table_exists(conn, "clean_telemetry"):
                return pd.DataFrame()
            return conn.execute("""
                SELECT station_id,
                       MAX(ts) as last_seen,
                       COUNT(*) as record_count,
                       AVG(quality_score) as avg_quality,
                       SUM(CASE WHEN heal_action != 'none' THEN 1 ELSE 0 END) as healed_count
                FROM clean_telemetry
                WHERE station_id IN (SELECT UNNEST(?::VARCHAR[]))
                GROUP BY station_id
            """, [valid_ids]).df()
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=300)
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


@st.cache_data(ttl=300)
def get_station_name_map() -> Dict[str, str]:
    """Return {station_id: name} lookup. Shared across all pages."""
    from config import STATIONS
    return {s.station_id: s.name for s in STATIONS}


@st.cache_data(ttl=60)
def load_conversation_log(limit: int = 200) -> pd.DataFrame:
    try:
        with _db() as conn:
            if not table_exists(conn, "conversation_log"):
                return pd.DataFrame()
            return conn.execute(
                "SELECT * FROM conversation_log ORDER BY created_at DESC LIMIT ?", [limit]
            ).df()
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=60)
def load_delivery_metrics(limit: int = 500) -> pd.DataFrame:
    try:
        with _db() as conn:
            if not table_exists(conn, "delivery_metrics"):
                return pd.DataFrame()
            return conn.execute(
                "SELECT * FROM delivery_metrics ORDER BY created_at DESC LIMIT ?", [limit]
            ).df()
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


# ---------------------------------------------------------------------------
# New helpers for dashboard restructure
# ---------------------------------------------------------------------------

@st.cache_data(ttl=60)
def load_data_source_distribution() -> pd.DataFrame:
    """Source distribution from raw_telemetry (IMD API / imdlib / synthetic)."""
    try:
        with _db() as conn:
            if not table_exists(conn, "raw_telemetry"):
                return pd.DataFrame()
            return conn.execute(
                "SELECT source, COUNT(*) as count FROM raw_telemetry GROUP BY source ORDER BY count DESC"
            ).df()
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=60)
def load_per_station_source() -> pd.DataFrame:
    """Latest data source per station."""
    try:
        with _db() as conn:
            if not table_exists(conn, "raw_telemetry"):
                return pd.DataFrame()
            return conn.execute("""
                SELECT station_id, source, COUNT(*) as readings,
                       MAX(ts) as last_reading
                FROM raw_telemetry
                GROUP BY station_id, source
                ORDER BY station_id
            """).df()
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=60)
def load_advisory_lineage(limit: int = 50) -> pd.DataFrame:
    """Join alerts to forecasts by station_id + time proximity."""
    try:
        with _db() as conn:
            if not table_exists(conn, "agricultural_alerts") or not table_exists(conn, "forecasts"):
                return pd.DataFrame()
            return conn.execute("""
                WITH ranked AS (
                    SELECT a.station_id, a.condition as alert_condition,
                           a.advisory_en, a.advisory_local, a.language, a.provider,
                           a.issued_at as alert_time,
                           f.temperature as fc_temperature, f.rainfall as fc_rainfall,
                           f.condition as fc_condition, f.model_used as fc_model,
                           f.confidence as fc_confidence, f.issued_at as fc_time,
                           ROW_NUMBER() OVER (
                               PARTITION BY a.id
                               ORDER BY ABS(EPOCH(a.issued_at) - EPOCH(f.issued_at))
                           ) as rn
                    FROM agricultural_alerts a
                    LEFT JOIN forecasts f ON a.station_id = f.station_id
                        AND ABS(EPOCH(a.issued_at) - EPOCH(f.issued_at)) < 600
                )
                SELECT * FROM ranked WHERE rn = 1
                ORDER BY alert_time DESC
                LIMIT ?
            """, [limit]).df()
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=300)
def load_farmer_profiles() -> pd.DataFrame:
    """Load all simulated farmer profiles from DPI registry."""
    try:
        from src.dpi.simulator import get_registry
        registry = get_registry()
        farmers = registry.list_farmers()
        rows = []
        for f in farmers:
            profile = registry.lookup_by_phone(f["phone"])
            if profile:
                land = profile.land_records[0] if profile.land_records else None
                rows.append({
                    "phone": f["phone"],
                    "name": profile.aadhaar.name,
                    "name_local": profile.aadhaar.name_local,
                    "district": profile.aadhaar.district,
                    "state": profile.aadhaar.state,
                    "language": profile.aadhaar.language,
                    "station_id": f["station"],
                    "crops": ", ".join(f["crops"]),
                    "area_ha": f.get("area_ha", 0),
                    "gps_lat": land.gps_lat if land else None,
                    "gps_lon": land.gps_lon if land else None,
                    "soil_type": land.soil_type if land else None,
                    "irrigation": land.irrigation_type if land else None,
                })
        return pd.DataFrame(rows)
    except Exception:
        return pd.DataFrame()


def load_farmer_profile_detail(phone: str) -> Optional[Dict]:
    """Load full DPI detail for a single farmer."""
    try:
        from src.dpi.simulator import get_registry
        profile = get_registry().lookup_by_phone(phone)
        if not profile:
            return None
        return {
            "aadhaar": profile.aadhaar,
            "land_records": profile.land_records,
            "soil_health": profile.soil_health,
            "pmkisan": profile.pmkisan,
            "pmfby": profile.pmfby,
            "kcc": profile.kcc,
            "primary_crops": profile.primary_crops,
            "total_area": profile.total_area,
        }
    except Exception:
        return None


@st.cache_data(ttl=60)
def load_healing_log(limit: int = 200) -> pd.DataFrame:
    """Load latest healing assessments with agent reasoning."""
    try:
        with _db() as conn:
            if not table_exists(conn, "healing_log"):
                return pd.DataFrame()
            return conn.execute(
                "SELECT * FROM healing_log ORDER BY created_at DESC LIMIT ?", [limit]
            ).df()
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=60)
def load_healing_stats() -> Dict[str, Any]:
    """Aggregate healing stats: assessment distribution, tool usage, avg quality."""
    try:
        with _db() as conn:
            if not table_exists(conn, "healing_log"):
                return {}

            # Assessment distribution
            dist_rows = conn.execute(
                """SELECT assessment, COUNT(*) as cnt, AVG(quality_score) as avg_q
                   FROM healing_log GROUP BY assessment"""
            ).fetchall()
            dist = {r[0]: {"count": r[1], "avg_quality": round(r[2], 3) if r[2] else None}
                    for r in dist_rows}

            # Tool usage frequency
            tool_rows = conn.execute(
                """SELECT tools_used FROM healing_log
                   WHERE tools_used IS NOT NULL AND tools_used != ''"""
            ).fetchall()
            tool_counts: Dict[str, int] = {}
            for (tools_str,) in tool_rows:
                for t in tools_str.split(","):
                    t = t.strip()
                    if t:
                        tool_counts[t] = tool_counts.get(t, 0) + 1

            # Latest run stats
            latest = conn.execute(
                """SELECT model, tokens_in, tokens_out, latency_s, fallback_used, created_at
                   FROM healing_log ORDER BY created_at DESC LIMIT 1"""
            ).fetchall()
            latest_run = None
            if latest:
                r = latest[0]
                latest_run = {
                    "model": r[0], "tokens_in": r[1], "tokens_out": r[2],
                    "latency_s": r[3], "fallback_used": r[4], "created_at": str(r[5]),
                }

            return {
                "assessment_distribution": dist,
                "tool_usage": tool_counts,
                "latest_run": latest_run,
                "total_assessments": sum(d["count"] for d in dist.values()),
            }
    except Exception:
        return {}


@st.cache_data(ttl=60)
def load_pipeline_stage_stats() -> Dict[str, Any]:
    """Load live counts for the home page pipeline diagram."""
    stats: Dict[str, Any] = {
        "stations": 20,
        "sources": "",
        "avg_quality": 0.0,
        "forecasts": 0,
        "mos_count": 0,
        "advisories": 0,
        "deliveries": 0,
        "last_run": None,
    }
    try:
        with _db() as conn:
            if table_exists(conn, "raw_telemetry"):
                src = conn.execute(
                    "SELECT source, COUNT(*) as n FROM raw_telemetry GROUP BY source ORDER BY n DESC LIMIT 5"
                ).fetchall()
                stats["sources"] = " · ".join(f"{s[0]}:{s[1]}" for s in src) if src else "no data"

            if table_exists(conn, "clean_telemetry"):
                row = conn.execute(
                    "SELECT AVG(quality_score) FROM clean_telemetry"
                ).fetchone()
                stats["avg_quality"] = round(row[0], 2) if row and row[0] else 0.0

            if table_exists(conn, "forecasts"):
                row = conn.execute("SELECT COUNT(*) FROM forecasts").fetchone()
                stats["forecasts"] = row[0] if row else 0
                row = conn.execute(
                    "SELECT COUNT(*) FROM forecasts WHERE model_used = 'hybrid_mos'"
                ).fetchone()
                stats["mos_count"] = row[0] if row else 0

            if table_exists(conn, "agricultural_alerts"):
                row = conn.execute("SELECT COUNT(*) FROM agricultural_alerts").fetchone()
                stats["advisories"] = row[0] if row else 0

            if table_exists(conn, "delivery_log"):
                row = conn.execute("SELECT COUNT(*) FROM delivery_log").fetchone()
                stats["deliveries"] = row[0] if row else 0

            if table_exists(conn, "pipeline_runs"):
                row = conn.execute(
                    "SELECT started_at, status, summary FROM pipeline_runs ORDER BY started_at DESC LIMIT 1"
                ).fetchone()
                if row:
                    stats["last_run"] = {"time": row[0], "status": row[1], "summary": row[2]}
    except Exception:
        pass
    return stats
