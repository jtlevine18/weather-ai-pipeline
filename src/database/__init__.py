"""DuckDB schema and CRUD helpers for the weather pipeline.

This package splits database operations by domain. All public names are
re-exported here so existing ``from src.database import X`` continues to work.
"""

from __future__ import annotations
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

CREATE TABLE IF NOT EXISTS healing_log (
    id              VARCHAR PRIMARY KEY,
    pipeline_run_id VARCHAR,
    reading_id      VARCHAR NOT NULL,
    station_id      VARCHAR NOT NULL,
    assessment      VARCHAR,
    reasoning       VARCHAR,
    corrections     VARCHAR,
    quality_score   DOUBLE,
    tools_used      VARCHAR,
    original_values VARCHAR,
    model           VARCHAR,
    tokens_in       INTEGER,
    tokens_out      INTEGER,
    latency_s       DOUBLE,
    fallback_used   BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMP DEFAULT current_timestamp
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

CREATE TABLE IF NOT EXISTS conversation_log (
    id          VARCHAR PRIMARY KEY,
    session_id  VARCHAR NOT NULL,
    role        VARCHAR NOT NULL,
    content     VARCHAR,
    tool_name   VARCHAR,
    tool_input  VARCHAR,
    tokens_in   INTEGER,
    tokens_out  INTEGER,
    latency_ms  INTEGER,
    created_at  TIMESTAMP DEFAULT current_timestamp
);

CREATE TABLE IF NOT EXISTS delivery_metrics (
    id                   VARCHAR PRIMARY KEY,
    pipeline_run_id      VARCHAR,
    station_id           VARCHAR NOT NULL,
    forecasts_generated  INTEGER DEFAULT 0,
    advisories_generated INTEGER DEFAULT 0,
    deliveries_attempted INTEGER DEFAULT 0,
    deliveries_succeeded INTEGER DEFAULT 0,
    channels_used        VARCHAR,
    created_at           TIMESTAMP DEFAULT current_timestamp
);

CREATE TABLE IF NOT EXISTS feedback_responses (
    id             VARCHAR PRIMARY KEY,
    delivery_id    VARCHAR,
    station_id     VARCHAR,
    question       VARCHAR,
    response       VARCHAR,
    response_value INTEGER,
    received_at    TIMESTAMP DEFAULT current_timestamp
);

CREATE TABLE IF NOT EXISTS farmer_profiles (
    id              VARCHAR PRIMARY KEY,
    aadhaar_id      VARCHAR,
    phone           VARCHAR,
    name            VARCHAR,
    district        VARCHAR,
    station_id      VARCHAR,
    primary_crops   VARCHAR,
    total_area      DOUBLE,
    profile_json    VARCHAR,
    cached_at       TIMESTAMP DEFAULT current_timestamp
);

CREATE TABLE IF NOT EXISTS farmer_land_records (
    id              VARCHAR PRIMARY KEY,
    aadhaar_id      VARCHAR NOT NULL,
    survey_number   VARCHAR,
    area_hectares   DOUBLE,
    soil_type       VARCHAR,
    irrigation_type VARCHAR,
    gps_lat         DOUBLE,
    gps_lon         DOUBLE,
    crops           VARCHAR,
    station_id      VARCHAR,
    created_at      TIMESTAMP DEFAULT current_timestamp
);

CREATE TABLE IF NOT EXISTS farmer_soil_health (
    id              VARCHAR PRIMARY KEY,
    aadhaar_id      VARCHAR NOT NULL,
    card_number     VARCHAR,
    pH              DOUBLE,
    nitrogen_kg_ha  DOUBLE,
    phosphorus_kg_ha DOUBLE,
    potassium_kg_ha DOUBLE,
    organic_carbon  DOUBLE,
    classification  VARCHAR,
    created_at      TIMESTAMP DEFAULT current_timestamp
);

CREATE TABLE IF NOT EXISTS conversation_sessions (
    id              VARCHAR PRIMARY KEY,
    aadhaar_id      VARCHAR,
    phone           VARCHAR,
    state           VARCHAR DEFAULT 'onboarding',
    language        VARCHAR DEFAULT 'en',
    context_json    VARCHAR,
    updated_at      TIMESTAMP DEFAULT current_timestamp
);

CREATE TABLE IF NOT EXISTS conversation_memory (
    id              VARCHAR PRIMARY KEY,
    aadhaar_id      VARCHAR NOT NULL,
    session_id      VARCHAR,
    memory_type     VARCHAR,
    content         VARCHAR,
    expires_at      TIMESTAMP,
    created_at      TIMESTAMP DEFAULT current_timestamp
);

CREATE TABLE IF NOT EXISTS scheduled_followups (
    id              VARCHAR PRIMARY KEY,
    aadhaar_id      VARCHAR NOT NULL,
    session_id      VARCHAR,
    trigger_type    VARCHAR,
    trigger_value   VARCHAR,
    message_template VARCHAR,
    status          VARCHAR DEFAULT 'pending',
    fired_at        TIMESTAMP,
    created_at      TIMESTAMP DEFAULT current_timestamp
);
"""


def init_db(db_path: str = "weather.duckdb") -> duckdb.DuckDBPyConnection:
    conn = duckdb.connect(db_path)
    conn.execute(DDL)
    return conn


from src.database._util import _now, _rows_to_dicts  # noqa: F401


# ---------------------------------------------------------------------------
# Re-exports — keeps ``from src.database import X`` working everywhere
# ---------------------------------------------------------------------------

from src.database.telemetry import (  # noqa: E402, F401
    insert_raw_telemetry,
    insert_clean_telemetry,
    get_latest_clean_for_station,
    get_all_clean_telemetry,
    get_clean_history_for_station,
    get_paired_raw_clean,
)
from src.database.forecasts import (  # noqa: E402, F401
    insert_forecast,
    get_recent_forecasts,
    get_forecast_actuals,
)
from src.database.alerts import (  # noqa: E402, F401
    insert_alert,
    get_recent_alerts,
)
from src.database.delivery import (  # noqa: E402, F401
    insert_delivery_log,
    insert_delivery_metrics,
)
from src.database.pipeline_runs import (  # noqa: E402, F401
    start_pipeline_run,
    finish_pipeline_run,
)
from src.database.conversation import (  # noqa: E402, F401
    insert_conversation_log,
)
from src.database.health import (  # noqa: E402, F401
    get_station_health,
)
from src.database.healing import (  # noqa: E402, F401
    insert_healing_log,
    get_healing_log,
    get_healing_log_for_reading,
    get_healing_stats,
)
