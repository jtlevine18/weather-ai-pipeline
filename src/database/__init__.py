"""PostgreSQL schema and CRUD helpers for the weather pipeline.

This package splits database operations by domain. All public names are
re-exported here so existing ``from src.database import X`` continues to work.
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Schema DDL (PostgreSQL)
# ---------------------------------------------------------------------------

DDL = """
CREATE TABLE IF NOT EXISTS raw_telemetry (
    id          VARCHAR PRIMARY KEY,
    station_id  VARCHAR NOT NULL,
    ts          TIMESTAMP NOT NULL,
    temperature DOUBLE PRECISION,
    humidity    DOUBLE PRECISION,
    wind_speed  DOUBLE PRECISION,
    wind_dir    DOUBLE PRECISION,
    pressure    DOUBLE PRECISION,
    rainfall    DOUBLE PRECISION,
    fault_type  VARCHAR,
    source      VARCHAR DEFAULT 'synthetic',
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS clean_telemetry (
    id           VARCHAR PRIMARY KEY,
    station_id   VARCHAR NOT NULL,
    ts           TIMESTAMP NOT NULL,
    temperature  DOUBLE PRECISION,
    humidity     DOUBLE PRECISION,
    wind_speed   DOUBLE PRECISION,
    wind_dir     DOUBLE PRECISION,
    pressure     DOUBLE PRECISION,
    rainfall     DOUBLE PRECISION,
    heal_action  VARCHAR,
    heal_source  VARCHAR,
    quality_score DOUBLE PRECISION DEFAULT 1.0,
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS healing_log (
    id              VARCHAR PRIMARY KEY,
    pipeline_run_id VARCHAR,
    reading_id      VARCHAR NOT NULL,
    station_id      VARCHAR NOT NULL,
    assessment      VARCHAR,
    reasoning       VARCHAR,
    corrections     VARCHAR,
    quality_score   DOUBLE PRECISION,
    tools_used      VARCHAR,
    original_values VARCHAR,
    model           VARCHAR,
    tokens_in       INTEGER,
    tokens_out      INTEGER,
    latency_s       DOUBLE PRECISION,
    fallback_used   BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS forecasts (
    id            VARCHAR PRIMARY KEY,
    station_id    VARCHAR NOT NULL,
    issued_at     TIMESTAMP NOT NULL,
    valid_for_ts  TIMESTAMP NOT NULL,
    temperature   DOUBLE PRECISION,
    humidity      DOUBLE PRECISION,
    wind_speed    DOUBLE PRECISION,
    rainfall      DOUBLE PRECISION,
    condition     VARCHAR,
    model_used    VARCHAR,
    nwp_source    VARCHAR DEFAULT 'open_meteo',
    nwp_temp      DOUBLE PRECISION,
    correction    DOUBLE PRECISION,
    confidence    DOUBLE PRECISION DEFAULT 0.7,
    forecast_day  INTEGER DEFAULT 0,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS agricultural_alerts (
    id             VARCHAR PRIMARY KEY,
    station_id     VARCHAR NOT NULL,
    farmer_lat     DOUBLE PRECISION,
    farmer_lon     DOUBLE PRECISION,
    issued_at      TIMESTAMP NOT NULL,
    condition      VARCHAR,
    advisory_en    VARCHAR,
    advisory_local VARCHAR,
    sms_en         VARCHAR,
    sms_local      VARCHAR,
    crop_sms       VARCHAR,
    language       VARCHAR,
    provider       VARCHAR,
    retrieval_docs INTEGER DEFAULT 0,
    forecast_days  INTEGER DEFAULT 1,
    created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS personalized_advisories (
    id              VARCHAR PRIMARY KEY,
    alert_id        VARCHAR NOT NULL,
    station_id      VARCHAR NOT NULL,
    farmer_phone    VARCHAR NOT NULL,
    farmer_name     VARCHAR,
    crops           VARCHAR,
    soil_type       VARCHAR,
    irrigation_type VARCHAR,
    area_hectares   DOUBLE PRECISION,
    advisory_en     VARCHAR,
    advisory_local  VARCHAR,
    sms_en          VARCHAR,
    sms_local       VARCHAR,
    language        VARCHAR,
    model           VARCHAR,
    tokens_in       INTEGER DEFAULT 0,
    tokens_out      INTEGER DEFAULT 0,
    cache_read      INTEGER DEFAULT 0,
    generated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS delivery_log (
    id          VARCHAR PRIMARY KEY,
    alert_id    VARCHAR,
    station_id  VARCHAR,
    channel     VARCHAR,
    recipient   VARCHAR,
    status      VARCHAR,
    message     VARCHAR,
    sms_text    VARCHAR,
    delivered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
    created_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS feedback_responses (
    id             VARCHAR PRIMARY KEY,
    delivery_id    VARCHAR,
    station_id     VARCHAR,
    question       VARCHAR,
    response       VARCHAR,
    response_value INTEGER,
    received_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS farmer_profiles (
    id              VARCHAR PRIMARY KEY,
    aadhaar_id      VARCHAR,
    phone           VARCHAR,
    name            VARCHAR,
    district        VARCHAR,
    station_id      VARCHAR,
    primary_crops   VARCHAR,
    total_area      DOUBLE PRECISION,
    profile_json    VARCHAR,
    cached_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS farmer_land_records (
    id              VARCHAR PRIMARY KEY,
    aadhaar_id      VARCHAR NOT NULL,
    survey_number   VARCHAR,
    area_hectares   DOUBLE PRECISION,
    soil_type       VARCHAR,
    irrigation_type VARCHAR,
    gps_lat         DOUBLE PRECISION,
    gps_lon         DOUBLE PRECISION,
    crops           VARCHAR,
    station_id      VARCHAR,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS farmer_soil_health (
    id              VARCHAR PRIMARY KEY,
    aadhaar_id      VARCHAR NOT NULL,
    card_number     VARCHAR,
    pH              DOUBLE PRECISION,
    nitrogen_kg_ha  DOUBLE PRECISION,
    phosphorus_kg_ha DOUBLE PRECISION,
    potassium_kg_ha DOUBLE PRECISION,
    organic_carbon  DOUBLE PRECISION,
    classification  VARCHAR,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS conversation_sessions (
    id              VARCHAR PRIMARY KEY,
    aadhaar_id      VARCHAR,
    phone           VARCHAR,
    state           VARCHAR DEFAULT 'onboarding',
    language        VARCHAR DEFAULT 'en',
    context_json    VARCHAR,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS conversation_memory (
    id              VARCHAR PRIMARY KEY,
    aadhaar_id      VARCHAR NOT NULL,
    session_id      VARCHAR,
    memory_type     VARCHAR,
    content         VARCHAR,
    expires_at      TIMESTAMP,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS users (
    id              VARCHAR PRIMARY KEY,
    username        VARCHAR UNIQUE NOT NULL,
    password_hash   VARCHAR NOT NULL,
    role            VARCHAR DEFAULT 'viewer',
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Performance indexes. We deliberately do NOT add a UNIQUE constraint on
-- raw_telemetry(station_id, ts): existing data may contain duplicates and
-- adding the constraint here could break init_db() against a live DB.
-- Dedup should happen upstream in ingestion.
CREATE INDEX IF NOT EXISTS idx_raw_telemetry_station_ts
    ON raw_telemetry (station_id, ts);
CREATE INDEX IF NOT EXISTS idx_forecasts_station_valid_for
    ON forecasts (station_id, valid_for_ts);
CREATE INDEX IF NOT EXISTS idx_delivery_log_delivered_at
    ON delivery_log (delivered_at);

-- Additive, idempotent column migrations. These run on every init_db() so
-- existing Neon databases pick up new columns without a manual migration.
-- ADD COLUMN IF NOT EXISTS is a no-op if the column already exists.
ALTER TABLE agricultural_alerts    ADD COLUMN IF NOT EXISTS sms_en    VARCHAR;
ALTER TABLE agricultural_alerts    ADD COLUMN IF NOT EXISTS sms_local VARCHAR;
ALTER TABLE agricultural_alerts    ADD COLUMN IF NOT EXISTS crop_sms  VARCHAR;
ALTER TABLE personalized_advisories ADD COLUMN IF NOT EXISTS sms_en    VARCHAR;
ALTER TABLE personalized_advisories ADD COLUMN IF NOT EXISTS sms_local VARCHAR;
ALTER TABLE delivery_log           ADD COLUMN IF NOT EXISTS sms_text  VARCHAR;

-- GenCast 1.0° probabilistic rainfall columns (Phase 2). All nullable so
-- historical rows stay valid; GenCast runs additively after GraphCast and
-- populates these via UPDATE. If GenCast fails or is disabled they remain NULL.
ALTER TABLE forecasts ADD COLUMN IF NOT EXISTS rain_p10          DOUBLE PRECISION;
ALTER TABLE forecasts ADD COLUMN IF NOT EXISTS rain_p50          DOUBLE PRECISION;
ALTER TABLE forecasts ADD COLUMN IF NOT EXISTS rain_p90          DOUBLE PRECISION;
ALTER TABLE forecasts ADD COLUMN IF NOT EXISTS rain_prob_1mm     DOUBLE PRECISION;
ALTER TABLE forecasts ADD COLUMN IF NOT EXISTS rain_prob_5mm     DOUBLE PRECISION;
ALTER TABLE forecasts ADD COLUMN IF NOT EXISTS rain_prob_15mm    DOUBLE PRECISION;
ALTER TABLE forecasts ADD COLUMN IF NOT EXISTS ensemble_size     INTEGER;
ALTER TABLE forecasts ADD COLUMN IF NOT EXISTS nwp_model_version VARCHAR;

CREATE TABLE IF NOT EXISTS forecast_ensembles (
    forecast_id VARCHAR NOT NULL REFERENCES forecasts(id) ON DELETE CASCADE,
    member_idx  INTEGER NOT NULL,
    rainfall    DOUBLE PRECISION,
    PRIMARY KEY (forecast_id, member_idx)
);
"""


_schema_initialized = False


def init_db(database_url: str = "") -> Any:
    """Initialize PostgreSQL database and return connection.

    DDL only runs once per process. Subsequent calls just return a connection.
    """
    global _schema_initialized
    from src.database._util import PgConnection, get_database_url
    if not database_url:
        database_url = get_database_url()
    conn = PgConnection(database_url)
    if not _schema_initialized:
        conn.execute(DDL)
        _schema_initialized = True
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
    insert_forecast_ensemble,
    update_forecast_downscaled,
    update_forecast_probabilistic,
)
from src.database.alerts import (  # noqa: E402, F401
    insert_alert,
    insert_personalized_advisory,
    get_personalized_advisories,
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
