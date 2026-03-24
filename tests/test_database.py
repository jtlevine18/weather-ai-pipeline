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
    insert_healing_log,
    get_healing_log,
    get_healing_log_for_reading,
    get_healing_stats,
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
            "healing_log",
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

    def test_nwp_source_persisted(self, db_conn, sample_forecast):
        insert_forecast(db_conn, sample_forecast)
        forecasts = get_recent_forecasts(db_conn, limit=10)
        assert forecasts[0]["nwp_source"] == "open_meteo"

    def test_neuralgcm_nwp_source(self, db_conn, sample_forecast):
        fc = {**sample_forecast, "id": "fc_ngcm_001",
              "nwp_source": "neuralgcm", "model_used": "neuralgcm_mos"}
        insert_forecast(db_conn, fc)
        forecasts = get_recent_forecasts(db_conn, limit=10)
        ngcm = [f for f in forecasts if f["nwp_source"] == "neuralgcm"]
        assert len(ngcm) == 1
        assert ngcm[0]["model_used"] == "neuralgcm_mos"


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


class TestHealingLog:
    def test_insert_and_query(self, db_conn, sample_healing_record):
        insert_healing_log(db_conn, [sample_healing_record])
        logs = get_healing_log(db_conn, limit=10)
        assert len(logs) == 1
        assert logs[0]["station_id"] == "KL_TVM"
        assert logs[0]["assessment"] == "corrected"
        assert logs[0]["model"] == "claude-sonnet-4-6"

    def test_query_by_reading(self, db_conn, sample_healing_record):
        insert_healing_log(db_conn, [sample_healing_record])
        logs = get_healing_log_for_reading(db_conn, sample_healing_record["reading_id"])
        assert len(logs) == 1
        assert logs[0]["reasoning"].startswith("Temperature 290")

    def test_stats_aggregation(self, db_conn, sample_healing_record):
        # Insert two records with different assessments
        rec2 = {**sample_healing_record, "id": "heal_002", "reading_id": "r_002",
                "station_id": "TN_CHN", "assessment": "good", "quality_score": 0.95}
        insert_healing_log(db_conn, [sample_healing_record, rec2])
        stats = get_healing_stats(db_conn)
        assert stats["total_assessments"] == 2
        assert "corrected" in stats["assessment_distribution"]
        assert "good" in stats["assessment_distribution"]
        assert stats["latest_run"] is not None
        assert stats["latest_run"]["model"] == "claude-sonnet-4-6"

    def test_tool_usage_tracking(self, db_conn, sample_healing_record):
        insert_healing_log(db_conn, [sample_healing_record])
        stats = get_healing_stats(db_conn)
        assert "get_station_metadata" in stats["tool_usage"]
        assert "get_reference_comparison" in stats["tool_usage"]

    def test_fallback_flag(self, db_conn, sample_healing_record):
        rec = {**sample_healing_record, "id": "heal_fb", "fallback_used": True,
               "model": None, "tokens_in": None, "tokens_out": None}
        insert_healing_log(db_conn, [rec])
        logs = get_healing_log(db_conn, limit=10)
        assert logs[0]["fallback_used"] is True


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
