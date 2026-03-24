"""Shared fixtures for the weather pipeline test suite."""

import os
import sys
import pytest
import duckdb

# Ensure project root is on sys.path so imports like `from config import ...` work
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config import STATIONS, FaultInjectionConfig, PipelineConfig
from src.database import DDL


# ---------------------------------------------------------------------------
# Database fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db_conn():
    """Fresh in-memory DuckDB with all tables created."""
    conn = duckdb.connect(":memory:")
    conn.execute(DDL)
    yield conn
    conn.close()


# ---------------------------------------------------------------------------
# Config / station fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_station():
    """First station in the registry (KL_TVM — Thiruvananthapuram)."""
    return STATIONS[0]


@pytest.fixture
def fault_config_clean():
    """Fault config with all rates at zero — produces clean data."""
    return FaultInjectionConfig(typo_rate=0, offline_rate=0, drift_rate=0, missing_rate=0)


@pytest.fixture
def pipeline_config():
    """PipelineConfig with in-memory DB and empty API keys."""
    return PipelineConfig(db_path=":memory:", tomorrow_io_key="", anthropic_key="")


# ---------------------------------------------------------------------------
# Sample data fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_raw_reading():
    """A realistic raw_telemetry record (no faults)."""
    return {
        "id": "KL_TVM_20260323120000_abc123",
        "station_id": "KL_TVM",
        "ts": "2026-03-23T12:00:00",
        "temperature": 29.5,
        "humidity": 78.0,
        "wind_speed": 8.2,
        "wind_dir": 210.0,
        "pressure": 1005.6,
        "rainfall": 0.3,
        "fault_type": None,
        "source": "synthetic",
    }


@pytest.fixture
def sample_forecast():
    """A realistic forecasts record."""
    return {
        "id": "fc_KL_TVM_20260323_abc123",
        "station_id": "KL_TVM",
        "issued_at": "2026-03-23T12:00:00",
        "valid_for_ts": "2026-03-23T18:00:00",
        "temperature": 30.2,
        "humidity": 75.0,
        "wind_speed": 7.5,
        "rainfall": 1.2,
        "condition": "clear",
        "model_used": "hybrid_mos",
        "nwp_source": "open_meteo",
        "nwp_temp": 31.0,
        "correction": -0.8,
        "confidence": 0.82,
    }


# ---------------------------------------------------------------------------
# Mock API client fixtures
# ---------------------------------------------------------------------------

class MockWeatherClient:
    """Canned response client for any weather API."""

    def __init__(self, response):
        self._response = response

    async def get_current(self, lat, lon):
        return self._response

    async def get_forecast(self, lat, lon, hours=24):
        return [self._response] * min(hours, 3)


@pytest.fixture
def mock_tomorrow_io():
    """Returns canned Tomorrow.io-style response."""
    return MockWeatherClient({
        "temperature": 29.0,
        "humidity": 80.0,
        "wind_speed": 7.0,
        "wind_dir": 200.0,
        "pressure": 1010.0,
        "rainfall": 0.5,
        "source": "tomorrow_io",
    })


@pytest.fixture
def mock_open_meteo():
    """Returns canned Open-Meteo-style NWP forecast."""
    return MockWeatherClient({
        "ts": "2026-03-23T18:00:00",
        "temperature": 31.0,
        "humidity": 72.0,
        "wind_speed": 6.5,
        "wind_dir": 220.0,
        "pressure": 1008.0,
        "rainfall": 0.0,
    })


@pytest.fixture
def sample_healing_record():
    """A realistic healing_log record from the AI agent."""
    return {
        "id": "heal_KL_TVM_20260323_abc123",
        "pipeline_run_id": "run_001",
        "reading_id": "KL_TVM_20260323120000_abc123",
        "station_id": "KL_TVM",
        "assessment": "corrected",
        "reasoning": "Temperature 290°C is a decimal-place typo — corrected to 29.0°C. "
                     "Cross-validated against Tomorrow.io reference (29.3°C).",
        "corrections": '{"temperature": 29.0}',
        "quality_score": 0.85,
        "tools_used": "get_station_metadata,get_reference_comparison",
        "original_values": '{"temperature": 290.0}',
        "model": "claude-sonnet-4-6",
        "tokens_in": 3500,
        "tokens_out": 2000,
        "latency_s": 8.2,
        "fallback_used": False,
    }


@pytest.fixture
def sample_raw_reading_typo(sample_raw_reading):
    """A raw reading with a decimal-place typo (290 instead of 29)."""
    return {**sample_raw_reading, "temperature": 290.0, "fault_type": "typo",
            "id": "KL_TVM_20260323120000_typo"}


@pytest.fixture
def mock_nasa_power():
    """Returns canned NASA POWER-style response."""
    return MockWeatherClient({
        "lat": 8.52,
        "lon": 76.94,
        "temperature": 28.5,
        "humidity": 82.0,
        "wind_speed": 6.0,
        "pressure": 1012.0,
        "rainfall": 1.0,
    })
