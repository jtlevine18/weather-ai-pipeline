"""Unit tests for DuckDB schema and CRUD helpers."""

import pytest
from src.database import (
    DDL,
    insert_raw_telemetry,
    insert_clean_telemetry,
    insert_forecast,
    insert_alert,
    insert_delivery_log,
    start_pipeline_run,
    finish_pipeline_run,
    get_latest_clean_for_station,
    get_recent_forecasts,
    get_recent_alerts,
    get_station_health,
)


class TestSchemaCreation:
    def test_all_core_tables_exist(self, db_conn):
        tables = db_conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema='main'"
        ).fetchall()
        table_names = {t[0] for t in tables}
        expected = {
            "raw_telemetry", "clean_telemetry", "forecasts",
            "agricultural_alerts", "delivery_log", "pipeline_runs",
        }
        assert expected.issubset(table_names), f"Missing: {expected - table_names}"

    def test_all_metadata_tables_exist(self, db_conn):
        tables = db_conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema='main'"
        ).fetchall()
        table_names = {t[0] for t in tables}
        expected = {
            "conversation_log", "delivery_metrics", "farmer_profiles",
            "farmer_land_records", "farmer_soil_health",
            "conversation_sessions", "conversation_memory", "scheduled_followups",
        }
        assert expected.issubset(table_names), f"Missing: {expected - table_names}"


class TestRawTelemetry:
    def test_insert_and_query(self, db_conn, sample_raw_reading):
        insert_raw_telemetry(db_conn, [sample_raw_reading])
        rows = db_conn.execute("SELECT * FROM raw_telemetry").fetchall()
        assert len(rows) == 1

    def test_insert_replaces_duplicate(self, db_conn, sample_raw_reading):
        insert_raw_telemetry(db_conn, [sample_raw_reading])
        # Insert again with same ID — should replace, not duplicate
        sample_raw_reading["temperature"] = 99.0
        insert_raw_telemetry(db_conn, [sample_raw_reading])
        rows = db_conn.execute("SELECT * FROM raw_telemetry").fetchall()
        assert len(rows) == 1


class TestCleanTelemetry:
    def test_insert_and_query(self, db_conn, sample_raw_reading):
        clean = {**sample_raw_reading, "heal_action": "none",
                 "heal_source": "original", "quality_score": 1.0}
        insert_clean_telemetry(db_conn, [clean])
        result = get_latest_clean_for_station(db_conn, "KL_TVM")
        assert result is not None
        assert result["station_id"] == "KL_TVM"
        assert result["quality_score"] == 1.0

    def test_station_health(self, db_conn, sample_raw_reading):
        clean = {**sample_raw_reading, "heal_action": "none",
                 "heal_source": "original", "quality_score": 0.9}
        insert_clean_telemetry(db_conn, [clean])
        health = get_station_health(db_conn)
        assert len(health) == 1
        assert health[0]["station_id"] == "KL_TVM"
        assert health[0]["avg_quality"] == 0.9


class TestForecasts:
    def test_insert_and_query(self, db_conn, sample_forecast):
        insert_forecast(db_conn, sample_forecast)
        forecasts = get_recent_forecasts(db_conn, limit=10)
        assert len(forecasts) == 1
        assert forecasts[0]["station_id"] == "KL_TVM"
        assert forecasts[0]["confidence"] == 0.82


class TestAlerts:
    def test_insert_and_query(self, db_conn):
        alert = {
            "id": "alert_001",
            "station_id": "KL_TVM",
            "issued_at": "2026-03-23T12:00:00",
            "condition": "heavy_rain",
            "advisory_en": "Clear drainage channels",
            "advisory_local": "ഡ്രെയിനേജ് ചാനലുകൾ വൃത്തിയാക്കുക",
            "language": "ml",
            "provider": "rule_based",
            "retrieval_docs": 0,
        }
        insert_alert(db_conn, alert)
        alerts = get_recent_alerts(db_conn, limit=10)
        assert len(alerts) == 1
        assert alerts[0]["provider"] == "rule_based"


class TestDeliveryLog:
    def test_insert(self, db_conn):
        log_entry = {
            "id": "del_001",
            "alert_id": "alert_001",
            "station_id": "KL_TVM",
            "channel": "console",
            "recipient": "stdout",
            "status": "sent",
            "message": "Test delivery",
        }
        insert_delivery_log(db_conn, log_entry)
        rows = db_conn.execute("SELECT * FROM delivery_log").fetchall()
        assert len(rows) == 1


class TestPipelineRuns:
    def test_lifecycle(self, db_conn):
        run_id = "run_test_001"
        start_pipeline_run(db_conn, run_id)
        rows = db_conn.execute(
            "SELECT * FROM pipeline_runs WHERE id=?", [run_id]
        ).fetchall()
        assert len(rows) == 1
        assert rows[0][3] == "running"  # status column

        finish_pipeline_run(db_conn, run_id, "ok", 6, 0, "All steps passed")
        row = db_conn.execute(
            "SELECT status, steps_ok, steps_fail FROM pipeline_runs WHERE id=?",
            [run_id],
        ).fetchone()
        assert row[0] == "ok"
        assert row[1] == 6
        assert row[2] == 0
