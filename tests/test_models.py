"""Tests for Pydantic data contract models."""

import pytest
from pydantic import ValidationError

from src.models import (
    RawReading, CleanReading, Forecast, DownscaledForecast,
    Advisory, DeliveryLog,
)


class TestRawReading:
    def test_valid_reading(self, sample_raw_reading):
        model = RawReading(**sample_raw_reading)
        assert model.station_id == "KL_TVM"
        assert model.temperature == 29.5

    def test_offline_reading_allows_nulls(self):
        reading = RawReading(
            id="test_001", station_id="KL_TVM", ts="2026-03-23T12:00:00",
            temperature=None, humidity=None, fault_type="offline",
        )
        assert reading.temperature is None

    def test_roundtrip_dict(self, sample_raw_reading):
        model = RawReading(**sample_raw_reading)
        d = model.model_dump()
        model2 = RawReading(**d)
        assert model == model2


class TestCleanReading:
    def test_valid_clean_reading(self):
        reading = CleanReading(
            id="test_001", station_id="KL_TVM", ts="2026-03-23T12:00:00",
            temperature=29.5, humidity=78.0, quality_score=0.8,
            heal_action="typo_corrected", heal_source="rule",
        )
        assert reading.quality_score == 0.8

    def test_rejects_quality_score_above_1(self):
        with pytest.raises(ValidationError):
            CleanReading(
                id="test_001", station_id="KL_TVM", ts="2026-03-23T12:00:00",
                quality_score=1.5,
            )

    def test_rejects_quality_score_below_0(self):
        with pytest.raises(ValidationError):
            CleanReading(
                id="test_001", station_id="KL_TVM", ts="2026-03-23T12:00:00",
                quality_score=-0.1,
            )


class TestForecast:
    def test_valid_forecast(self, sample_forecast):
        model = Forecast(**sample_forecast)
        assert model.confidence == 0.82
        assert model.model_used == "hybrid_mos"

    def test_rejects_confidence_above_1(self):
        with pytest.raises(ValidationError):
            Forecast(
                id="fc_001", station_id="KL_TVM",
                issued_at="2026-03-23T12:00:00",
                valid_for_ts="2026-03-23T18:00:00",
                confidence=1.5,
            )

    def test_rejects_confidence_below_0(self):
        with pytest.raises(ValidationError):
            Forecast(
                id="fc_001", station_id="KL_TVM",
                issued_at="2026-03-23T12:00:00",
                valid_for_ts="2026-03-23T18:00:00",
                confidence=-0.2,
            )

    def test_defaults(self):
        model = Forecast(
            id="fc_001", station_id="KL_TVM",
            issued_at="2026-03-23T12:00:00",
            valid_for_ts="2026-03-23T18:00:00",
        )
        assert model.condition == "clear"
        assert model.model_used == "persistence"
        assert model.nwp_source == "open_meteo"
        assert model.confidence == 0.7
        assert model.correction == 0.0

    def test_neuralgcm_nwp_source(self):
        model = Forecast(
            id="fc_001", station_id="KL_TVM",
            issued_at="2026-03-23T12:00:00",
            valid_for_ts="2026-03-23T18:00:00",
            nwp_source="neuralgcm",
            model_used="neuralgcm_mos",
        )
        assert model.nwp_source == "neuralgcm"
        assert model.model_used == "neuralgcm_mos"


class TestDownscaledForecast:
    def test_extends_forecast(self):
        model = DownscaledForecast(
            id="fc_001", station_id="KL_TVM",
            issued_at="2026-03-23T12:00:00",
            valid_for_ts="2026-03-23T18:00:00",
            farmer_lat=8.53, farmer_lon=76.94,
            downscaled=True, lapse_delta=-1.2,
        )
        assert model.downscaled is True
        assert model.lapse_delta == -1.2
        # Inherits Forecast fields
        assert model.confidence == 0.7


class TestAdvisory:
    def test_valid_advisory(self):
        model = Advisory(
            id="adv_001", station_id="KL_TVM",
            issued_at="2026-03-23T12:00:00",
            advisory_en="Clear drainage",
            advisory_local="ഡ്രെയിനേജ്",
            language="ml", provider="rag_claude",
            retrieval_docs=3,
        )
        assert model.provider == "rag_claude"
        assert model.retrieval_docs == 3

    def test_defaults(self):
        model = Advisory(
            id="adv_001", station_id="KL_TVM",
            issued_at="2026-03-23T12:00:00",
        )
        assert model.language == "en"
        assert model.provider == "unknown"
        assert model.retrieval_docs == 0


class TestDeliveryLog:
    def test_valid_log(self):
        model = DeliveryLog(
            id="del_001", alert_id="adv_001", station_id="KL_TVM",
            channel="console", recipient="stdout", status="sent",
        )
        assert model.channel == "console"

    def test_missing_required_field(self):
        with pytest.raises(ValidationError):
            DeliveryLog(id="del_001")  # missing channel and recipient


class TestQualityChecks:
    def test_row_count_pass(self, db_conn, sample_raw_reading):
        from src.database import insert_raw_telemetry
        from src.quality_checks import check_row_count
        insert_raw_telemetry(db_conn, [sample_raw_reading])
        passed, msg = check_row_count(db_conn, "raw_telemetry", 1)
        assert passed

    def test_row_count_fail(self, db_conn):
        from src.quality_checks import check_row_count
        passed, msg = check_row_count(db_conn, "raw_telemetry", 10)
        assert not passed

    def test_null_rate(self, db_conn, sample_raw_reading):
        from src.database import insert_raw_telemetry
        from src.quality_checks import check_null_rate
        insert_raw_telemetry(db_conn, [sample_raw_reading])
        passed, msg = check_null_rate(db_conn, "raw_telemetry", "temperature", 5.0)
        assert passed  # 0% null

    def test_value_range_pass(self, db_conn, sample_raw_reading):
        from src.database import insert_raw_telemetry
        from src.quality_checks import check_value_range
        insert_raw_telemetry(db_conn, [sample_raw_reading])
        passed, msg = check_value_range(db_conn, "raw_telemetry", "temperature", -10.0, 55.0)
        assert passed

    def test_value_range_fail(self, db_conn):
        from src.database import insert_raw_telemetry
        from src.quality_checks import check_value_range
        # Insert a reading with temp=290 (typo fault)
        insert_raw_telemetry(db_conn, [{
            "id": "test_typo", "station_id": "KL_TVM", "ts": "2026-03-23T12:00:00",
            "temperature": 290.0, "source": "synthetic",
        }])
        passed, msg = check_value_range(db_conn, "raw_telemetry", "temperature", -10.0, 55.0)
        assert not passed
