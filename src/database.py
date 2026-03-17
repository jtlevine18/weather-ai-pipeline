"""DuckDB schema and CRUD helpers for the weather pipeline."""

from __future__ import annotations
import json
from datetime import datetime
from typing import Any, Dict, List, Optional
import duckdb


# ---------------------------------------------------------------------------
# Schema DDL
# ---------------------------------------------------------------------------

DDL = """
CREATE TABLE IF NOT EXISTS raw_telemetry (
    id          VARCHAR PRIMARY KEY,
    station_id  VARCHAR NOT NULL,
    ts          TIMESTAMP NOT NULL,
    temperature DOUBLE,
    humidity    DOUBLE,
    wind_speed  DOUBLE,
    wind_dir    DOUBLE,
    pressure    DOUBLE,
    rainfall    DOUBLE,
    fault_type  VARCHAR,
    source      VARCHAR DEFAULT 'synthetic',
    created_at  TIMESTAMP DEFAULT current_timestamp
);

CREATE TABLE IF NOT EXISTS clean_telemetry (
    id           VARCHAR PRIMARY KEY,
    station_id   VARCHAR NOT NULL,
    ts           TIMESTAMP NOT NULL,
    temperature  DOUBLE,
    humidity     DOUBLE,
    wind_speed   DOUBLE,
    wind_dir     DOUBLE,
    pressure     DOUBLE,
    rainfall     DOUBLE,
    heal_action  VARCHAR,
    heal_source  VARCHAR,
    quality_score DOUBLE DEFAULT 1.0,
    created_at   TIMESTAMP DEFAULT current_timestamp
);

CREATE TABLE IF NOT EXISTS forecasts (
    id            VARCHAR PRIMARY KEY,
    station_id    VARCHAR NOT NULL,
    issued_at     TIMESTAMP NOT NULL,
    valid_for_ts  TIMESTAMP NOT NULL,
    temperature   DOUBLE,
    humidity      DOUBLE,
    wind_speed    DOUBLE,
    rainfall      DOUBLE,
    condition     VARCHAR,
    model_used    VARCHAR,
    nwp_temp      DOUBLE,
    correction    DOUBLE,
    confidence    DOUBLE DEFAULT 0.7,
    created_at    TIMESTAMP DEFAULT current_timestamp
);

CREATE TABLE IF NOT EXISTS agricultural_alerts (
    id             VARCHAR PRIMARY KEY,
    station_id     VARCHAR NOT NULL,
    farmer_lat     DOUBLE,
    farmer_lon     DOUBLE,
    issued_at      TIMESTAMP NOT NULL,
    condition      VARCHAR,
    advisory_en    VARCHAR,
    advisory_local VARCHAR,
    language       VARCHAR,
    provider       VARCHAR,
    retrieval_docs INTEGER DEFAULT 0,
    created_at     TIMESTAMP DEFAULT current_timestamp
);

CREATE TABLE IF NOT EXISTS delivery_log (
    id          VARCHAR PRIMARY KEY,
    alert_id    VARCHAR,
    station_id  VARCHAR,
    channel     VARCHAR,
    recipient   VARCHAR,
    status      VARCHAR,
    message     VARCHAR,
    delivered_at TIMESTAMP DEFAULT current_timestamp
);

CREATE TABLE IF NOT EXISTS pipeline_runs (
    id         VARCHAR PRIMARY KEY,
    started_at TIMESTAMP NOT NULL,
    ended_at   TIMESTAMP,
    status     VARCHAR DEFAULT 'running',
    steps_ok   INTEGER DEFAULT 0,
    steps_fail INTEGER DEFAULT 0,
    summary    VARCHAR
);
"""


def init_db(db_path: str = "weather.duckdb") -> duckdb.DuckDBPyConnection:
    conn = duckdb.connect(db_path)
    conn.execute(DDL)
    return conn


# ---------------------------------------------------------------------------
# Insert helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.utcnow().isoformat()


def insert_raw_telemetry(conn: duckdb.DuckDBPyConnection, records: List[Dict[str, Any]]) -> None:
    for r in records:
        conn.execute(
            """INSERT OR REPLACE INTO raw_telemetry
               (id, station_id, ts, temperature, humidity, wind_speed, wind_dir,
                pressure, rainfall, fault_type, source)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            [r["id"], r["station_id"], r["ts"],
             r.get("temperature"), r.get("humidity"), r.get("wind_speed"),
             r.get("wind_dir"), r.get("pressure"), r.get("rainfall"),
             r.get("fault_type"), r.get("source", "synthetic")],
        )


def insert_clean_telemetry(conn: duckdb.DuckDBPyConnection, records: List[Dict[str, Any]]) -> None:
    for r in records:
        conn.execute(
            """INSERT OR REPLACE INTO clean_telemetry
               (id, station_id, ts, temperature, humidity, wind_speed, wind_dir,
                pressure, rainfall, heal_action, heal_source, quality_score)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            [r["id"], r["station_id"], r["ts"],
             r.get("temperature"), r.get("humidity"), r.get("wind_speed"),
             r.get("wind_dir"), r.get("pressure"), r.get("rainfall"),
             r.get("heal_action", "none"), r.get("heal_source", "original"),
             r.get("quality_score", 1.0)],
        )


def insert_forecast(conn: duckdb.DuckDBPyConnection, record: Dict[str, Any]) -> None:
    conn.execute(
        """INSERT OR REPLACE INTO forecasts
           (id, station_id, issued_at, valid_for_ts, temperature, humidity,
            wind_speed, rainfall, condition, model_used, nwp_temp, correction, confidence)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        [record["id"], record["station_id"], record["issued_at"], record["valid_for_ts"],
         record.get("temperature"), record.get("humidity"), record.get("wind_speed"),
         record.get("rainfall"), record.get("condition", "clear"),
         record.get("model_used", "persistence"),
         record.get("nwp_temp"), record.get("correction", 0.0),
         record.get("confidence", 0.7)],
    )


def insert_alert(conn: duckdb.DuckDBPyConnection, record: Dict[str, Any]) -> None:
    conn.execute(
        """INSERT OR REPLACE INTO agricultural_alerts
           (id, station_id, farmer_lat, farmer_lon, issued_at, condition,
            advisory_en, advisory_local, language, provider, retrieval_docs)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        [record["id"], record["station_id"],
         record.get("farmer_lat"), record.get("farmer_lon"),
         record["issued_at"], record.get("condition"),
         record.get("advisory_en"), record.get("advisory_local"),
         record.get("language", "en"), record.get("provider", "unknown"),
         record.get("retrieval_docs", 0)],
    )


def insert_delivery_log(conn: duckdb.DuckDBPyConnection, record: Dict[str, Any]) -> None:
    conn.execute(
        """INSERT OR REPLACE INTO delivery_log
           (id, alert_id, station_id, channel, recipient, status, message)
           VALUES (?,?,?,?,?,?,?)""",
        [record["id"], record.get("alert_id"), record.get("station_id"),
         record.get("channel"), record.get("recipient"),
         record.get("status", "sent"), record.get("message", "")],
    )


def start_pipeline_run(conn: duckdb.DuckDBPyConnection, run_id: str) -> None:
    conn.execute(
        "INSERT INTO pipeline_runs (id, started_at) VALUES (?,?)",
        [run_id, _now()],
    )


def finish_pipeline_run(conn: duckdb.DuckDBPyConnection, run_id: str,
                         status: str, steps_ok: int, steps_fail: int,
                         summary: str) -> None:
    conn.execute(
        """UPDATE pipeline_runs
           SET ended_at=?, status=?, steps_ok=?, steps_fail=?, summary=?
           WHERE id=?""",
        [_now(), status, steps_ok, steps_fail, summary, run_id],
    )


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------

def get_latest_clean_for_station(conn: duckdb.DuckDBPyConnection,
                                  station_id: str) -> Optional[Dict[str, Any]]:
    row = conn.execute(
        """SELECT * FROM clean_telemetry WHERE station_id=?
           ORDER BY ts DESC LIMIT 1""",
        [station_id],
    ).fetchone()
    if row is None:
        return None
    cols = [d[0] for d in conn.description]
    return dict(zip(cols, row))


def get_recent_forecasts(conn: duckdb.DuckDBPyConnection,
                          limit: int = 100) -> List[Dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM forecasts ORDER BY issued_at DESC LIMIT ?", [limit]
    ).fetchall()
    if not rows:
        return []
    cols = [d[0] for d in conn.description]
    return [dict(zip(cols, r)) for r in rows]


def get_recent_alerts(conn: duckdb.DuckDBPyConnection,
                       limit: int = 50) -> List[Dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM agricultural_alerts ORDER BY issued_at DESC LIMIT ?", [limit]
    ).fetchall()
    if not rows:
        return []
    cols = [d[0] for d in conn.description]
    return [dict(zip(cols, r)) for r in rows]


def get_all_clean_telemetry(conn: duckdb.DuckDBPyConnection) -> List[Dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM clean_telemetry ORDER BY ts DESC LIMIT 500"
    ).fetchall()
    if not rows:
        return []
    cols = [d[0] for d in conn.description]
    return [dict(zip(cols, r)) for r in rows]


def get_station_health(conn: duckdb.DuckDBPyConnection) -> List[Dict[str, Any]]:
    rows = conn.execute("""
        SELECT station_id,
               MAX(ts) as last_seen,
               COUNT(*) as record_count,
               AVG(quality_score) as avg_quality
        FROM clean_telemetry
        GROUP BY station_id
    """).fetchall()
    if not rows:
        return []
    cols = [d[0] for d in conn.description]
    return [dict(zip(cols, r)) for r in rows]
