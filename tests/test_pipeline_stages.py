"""Unit tests for pipeline stage logic — ingestion, healing, forecasting, downscaling, advisory."""

import pytest
from config import FaultInjectionConfig, STATIONS


# ---------------------------------------------------------------------------
# Step 1: Ingestion
# ---------------------------------------------------------------------------

class TestIngestion:
    def test_generate_reading_has_required_fields(self, sample_station, fault_config_clean):
        from src.ingestion import generate_synthetic_reading
        reading = generate_synthetic_reading(sample_station, fault_config_clean)
        for field in ["id", "station_id", "ts", "temperature", "humidity",
                       "wind_speed", "pressure", "rainfall", "source"]:
            assert field in reading, f"Missing field: {field}"
        assert reading["station_id"] == "KL_TVM"
        assert reading["source"] == "synthetic"

    def test_clean_reading_has_no_fault(self, sample_station, fault_config_clean):
        from src.ingestion import generate_synthetic_reading
        reading = generate_synthetic_reading(sample_station, fault_config_clean)
        assert reading["fault_type"] is None

    def test_typo_fault_multiplies_temperature(self, sample_station):
        from src.ingestion import generate_synthetic_reading
        cfg = FaultInjectionConfig(typo_rate=1.0, offline_rate=0, drift_rate=0, missing_rate=0)
        reading = generate_synthetic_reading(sample_station, cfg)
        assert reading["fault_type"] == "typo"
        # Typo multiplies by 10 — baseline temps are ~18-32, so typo should be >100
        assert reading["temperature"] > 100

    def test_offline_fault_nulls_all_fields(self, sample_station):
        from src.ingestion import generate_synthetic_reading
        cfg = FaultInjectionConfig(typo_rate=0, offline_rate=1.0, drift_rate=0, missing_rate=0)
        reading = generate_synthetic_reading(sample_station, cfg)
        assert reading["fault_type"] == "offline"
        assert reading["temperature"] is None
        assert reading["humidity"] is None
        assert reading["wind_speed"] is None

    def test_drift_fault_adds_offset(self, sample_station):
        from src.ingestion import generate_synthetic_reading
        cfg = FaultInjectionConfig(typo_rate=0, offline_rate=0, drift_rate=1.0, missing_rate=0)
        reading = generate_synthetic_reading(sample_station, cfg)
        assert reading["fault_type"] == "drift"
        # Drift adds +5 to temp — KL_TVM coastal base is ~29-32, so drift should push it higher
        assert reading["temperature"] > 30

    def test_missing_field_fault(self, sample_station):
        from src.ingestion import generate_synthetic_reading
        cfg = FaultInjectionConfig(typo_rate=0, offline_rate=0, drift_rate=0, missing_rate=1.0)
        reading = generate_synthetic_reading(sample_station, cfg)
        assert reading["fault_type"] == "missing_field"
        # One of pressure, rainfall, or wind_dir should be None
        nullable = [reading.get("pressure"), reading.get("rainfall"), reading.get("wind_dir")]
        assert None in nullable


# ---------------------------------------------------------------------------
# Step 2: Healing (RuleBasedFallback)
# ---------------------------------------------------------------------------

class TestHealing:
    def test_typo_correction(self):
        from src.healing import RuleBasedFallback
        healer = RuleBasedFallback()
        reading = {"station_id": "KL_TVM", "temperature": 290.0, "humidity": 78.0}
        result = healer.heal(reading)
        assert result["temperature"] == 29.0
        assert result["heal_action"] == "typo_corrected"
        assert result["heal_source"] == "rule"

    def test_impute_from_reference(self):
        from src.healing import RuleBasedFallback
        healer = RuleBasedFallback()
        reading = {"station_id": "KL_TVM", "temperature": None, "humidity": None}
        reference = {"temperature": 28.0, "humidity": 80.0, "wind_speed": 7.0,
                     "pressure": 1010.0, "rainfall": 0.5, "source": "tomorrow_io"}
        result = healer.heal(reading, reference)
        assert result["temperature"] == 28.0
        assert result["heal_action"] == "imputed_from_reference"
        assert result["heal_source"] == "tomorrow_io"

    def test_no_reference_returns_none(self):
        from src.healing import RuleBasedFallback
        healer = RuleBasedFallback()
        reading = {"station_id": "KL_TVM", "temperature": None}
        result = healer.heal(reading, reference=None)
        assert result is None

    def test_clean_reading_passes_through(self):
        from src.healing import RuleBasedFallback
        healer = RuleBasedFallback()
        reading = {"station_id": "KL_TVM", "temperature": 29.5, "humidity": 78.0}
        result = healer.heal(reading)
        assert result["temperature"] == 29.5
        assert result["heal_action"] == "none"
        assert result["heal_source"] == "original"

    def test_detect_anomalies_finds_typo(self):
        from src.healing import RuleBasedFallback
        healer = RuleBasedFallback()
        readings = [{"station_id": "X", "id": "1", "temperature": 350.0, "humidity": 78.0}]
        anomalies = healer.detect_anomalies(readings)
        assert len(anomalies) == 1
        assert anomalies[0]["issues"][0]["type"] == "typo"


# ---------------------------------------------------------------------------
# Step 3: Forecasting
# ---------------------------------------------------------------------------

class TestForecasting:
    def test_classify_heavy_rain(self):
        from src.forecasting import classify_condition
        assert classify_condition({"rainfall": 20.0}) == "heavy_rain"

    def test_classify_moderate_rain(self):
        from src.forecasting import classify_condition
        assert classify_condition({"rainfall": 8.0}) == "moderate_rain"

    def test_classify_heat_stress(self):
        from src.forecasting import classify_condition
        assert classify_condition({"temperature": 42.0, "humidity": 25.0, "rainfall": 0.0}) == "heat_stress"

    def test_classify_drought_risk(self):
        from src.forecasting import classify_condition
        assert classify_condition({"temperature": 36.0, "humidity": 30.0, "rainfall": 0.0}) == "drought_risk"

    def test_classify_clear(self):
        from src.forecasting import classify_condition
        assert classify_condition({"temperature": 28.0, "humidity": 65.0, "rainfall": 0.5}) == "clear"

    def test_classify_frost_risk(self):
        from src.forecasting import classify_condition
        assert classify_condition({"temperature": 5.0}) == "frost_risk"

    def test_persistence_model_returns_valid_forecast(self):
        from src.forecasting import PersistenceModel
        model = PersistenceModel()
        obs = {"temperature": 29.0, "humidity": 75.0, "wind_speed": 8.0,
               "wind_dir": 200.0, "pressure": 1010.0, "rainfall": 0.5}
        forecast = model.predict(obs)
        assert "temperature" in forecast
        assert forecast["model_used"] == "persistence"
        assert forecast["confidence"] == 0.4
        assert forecast["condition"] in [
            "clear", "heavy_rain", "moderate_rain", "heat_stress",
            "drought_risk", "frost_risk", "high_wind", "foggy",
        ]

    def test_aggregate_to_daily_groups_by_day(self):
        from src.forecasting import aggregate_to_daily
        # 4 timesteps across 2 days
        hourly = [
            {"ts": "2026-03-24T00:00:00", "temperature": 28.0, "rainfall": 0.0, "humidity": 70.0, "wind_speed": 5.0, "pressure": 1010.0, "source": "open_meteo"},
            {"ts": "2026-03-24T06:00:00", "temperature": 32.0, "rainfall": 2.0, "humidity": 65.0, "wind_speed": 8.0, "pressure": 1012.0, "source": "open_meteo"},
            {"ts": "2026-03-24T12:00:00", "temperature": 34.0, "rainfall": 0.0, "humidity": 60.0, "wind_speed": 10.0, "pressure": 1011.0, "source": "open_meteo"},
            {"ts": "2026-03-25T00:00:00", "temperature": 27.0, "rainfall": 5.0, "humidity": 80.0, "wind_speed": 6.0, "pressure": 1009.0, "source": "open_meteo"},
        ]
        result = aggregate_to_daily(hourly, num_days=7)
        assert len(result) >= 1
        # Each daily should have condition classified
        for daily in result:
            assert "condition" in daily
            assert "temperature" in daily
            assert "rainfall" in daily

    def test_aggregate_to_daily_temp_is_max(self):
        from src.forecasting import aggregate_to_daily
        hourly = [
            {"ts": "2026-03-24T00:00:00", "temperature": 25.0, "rainfall": 0.0, "humidity": 70.0, "wind_speed": 5.0, "pressure": 1010.0, "source": "open_meteo"},
            {"ts": "2026-03-24T06:00:00", "temperature": 35.0, "rainfall": 0.0, "humidity": 60.0, "wind_speed": 8.0, "pressure": 1012.0, "source": "open_meteo"},
            {"ts": "2026-03-24T12:00:00", "temperature": 30.0, "rainfall": 0.0, "humidity": 65.0, "wind_speed": 6.0, "pressure": 1011.0, "source": "open_meteo"},
        ]
        result = aggregate_to_daily(hourly, num_days=7)
        assert result[0]["temperature"] == 35.0  # daily max

    @pytest.mark.asyncio
    async def test_run_forecast_step_returns_list(self):
        from src.forecasting import run_forecast_step, HybridNWPModel, PersistenceModel

        class FakeOpenMeteo:
            async def get_forecast(self, lat, lon, hours=168):
                # Return 7 days of hourly data (simplified to 4 per day)
                results = []
                for d in range(7):
                    for h in [0, 6, 12, 18]:
                        results.append({
                            "ts": f"2026-03-{24+d:02d}T{h:02d}:00:00",
                            "temperature": 28.0 + d,
                            "humidity": 70.0,
                            "wind_speed": 5.0,
                            "pressure": 1010.0,
                            "rainfall": 1.0 if d == 3 else 0.0,
                            "source": "open_meteo",
                        })
                return results

        from config import STATIONS
        station = STATIONS[0]
        obs = {"temperature": 29.0, "humidity": 75.0}
        model = HybridNWPModel()
        persistence = PersistenceModel()

        result = await run_forecast_step(
            station, obs, FakeOpenMeteo(), model, persistence,
        )
        assert isinstance(result, list)
        assert len(result) == 7
        for fc in result:
            assert "forecast_day" in fc
            assert fc["forecast_day"] in range(7)
            assert "valid_for_ts" in fc

    @pytest.mark.asyncio
    async def test_run_forecast_step_persistence_returns_day0_only(self):
        from src.forecasting import run_forecast_step, HybridNWPModel, PersistenceModel

        class EmptyOpenMeteo:
            async def get_forecast(self, lat, lon, hours=168):
                return []

        from config import STATIONS
        station = STATIONS[0]
        obs = {"temperature": 29.0, "humidity": 75.0}
        model = HybridNWPModel()
        persistence = PersistenceModel()

        result = await run_forecast_step(
            station, obs, EmptyOpenMeteo(), model, persistence,
        )
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["forecast_day"] == 0


# ---------------------------------------------------------------------------
# Step 4: Downscaling
# ---------------------------------------------------------------------------

class TestDownscaling:
    def test_idw_interpolate_basic(self):
        from src.downscaling.interpolation import idw_interpolate
        # 4-point grid around target
        grid = [
            {"lat": 9.0, "lon": 77.0, "temperature": 30.0},
            {"lat": 9.0, "lon": 78.0, "temperature": 32.0},
            {"lat": 10.0, "lon": 77.0, "temperature": 28.0},
            {"lat": 10.0, "lon": 78.0, "temperature": 26.0},
        ]
        result = idw_interpolate(grid, 9.5, 77.5, "temperature")
        assert result is not None
        # IDW result should be between min and max grid values
        assert 26.0 <= result <= 32.0

    def test_idw_interpolate_empty_grid(self):
        from src.downscaling.interpolation import idw_interpolate
        assert idw_interpolate([], 9.5, 77.5) is None

    def test_idw_interpolate_all_none(self):
        from src.downscaling.interpolation import idw_interpolate
        grid = [{"lat": 9.0, "lon": 77.0, "temperature": None}]
        assert idw_interpolate(grid, 9.5, 77.5) is None

    def test_idw_closer_point_has_more_weight(self):
        from src.downscaling.interpolation import idw_interpolate
        grid = [
            {"lat": 9.5, "lon": 77.5, "temperature": 30.0},  # very close to target
            {"lat": 11.0, "lon": 79.0, "temperature": 20.0},  # far away
        ]
        result = idw_interpolate(grid, 9.5, 77.5)
        # Should be much closer to 30 than 20 since first point is nearly coincident
        assert result > 28.0

    def test_lapse_rate_higher_altitude_is_cooler(self):
        from src.downscaling.interpolation import apply_lapse_rate
        # Going from 100m to 1100m (1000m higher) should cool by ~6.5°C
        result = apply_lapse_rate(30.0, source_alt_m=100, target_alt_m=1100)
        assert abs(result - 23.5) < 0.01

    def test_lapse_rate_lower_altitude_is_warmer(self):
        from src.downscaling.interpolation import apply_lapse_rate
        # Going from 1000m down to 0m should warm by ~6.5°C
        result = apply_lapse_rate(20.0, source_alt_m=1000, target_alt_m=0)
        assert abs(result - 26.5) < 0.01

    def test_haversine_zero_distance(self):
        from src.downscaling.interpolation import haversine_km
        assert haversine_km(9.0, 77.0, 9.0, 77.0) == 0.0


# ---------------------------------------------------------------------------
# Step 5: Translation (local fallback)
# ---------------------------------------------------------------------------

class TestLocalAdvisory:
    def test_local_provider_returns_required_keys(self, sample_station):
        from src.translation.local_provider import LocalProvider
        provider = LocalProvider()
        forecast = {"condition": "heavy_rain", "temperature": 29.0, "rainfall": 20.0}
        result = provider.generate_advisory(forecast, sample_station)
        assert "advisory_en" in result
        assert "advisory_local" in result
        assert result["provider"] == "rule_based"
        assert result["retrieval_docs"] == 0
        assert result["language"] == "ml"  # KL_TVM is Kerala → Malayalam

    def test_local_provider_clear_condition(self, sample_station):
        from src.translation.local_provider import LocalProvider
        provider = LocalProvider()
        forecast = {"condition": "clear", "temperature": 29.0, "rainfall": 0.0}
        result = provider.generate_advisory(forecast, sample_station)
        assert len(result["advisory_en"]) > 10

    def test_curated_advisory_lookup(self):
        from src.translation.curated_advisories import get_advisory
        # Rice + heavy rain should return a specific advisory
        advisory = get_advisory("heavy_rain", "rice (paddy), coconut")
        assert "drainage" in advisory.lower() or "waterlogging" in advisory.lower()

    def test_curated_advisory_default_fallback(self):
        from src.translation.curated_advisories import get_advisory
        advisory = get_advisory("heavy_rain", "unknown_crop_xyz")
        assert len(advisory) > 20  # should return default advisory
