"""
Step 3: Forecasting — MOS (Model Output Statistics) using XGBoost on NWP residuals.
Formula: Final = NWP_Forecast + XGBoost_Correction(features)
Fallback: PersistenceModel (last observation + diurnal adjustment)
"""

from __future__ import annotations
import json
import logging
import os
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Condition classification
# ---------------------------------------------------------------------------

def classify_condition(forecast: Dict[str, Any]) -> str:
    """Map a forecast dict to a discrete condition code."""
    temp   = forecast.get("temperature", 25.0) or 25.0
    rh     = forecast.get("humidity", 60.0) or 60.0
    rain   = forecast.get("rainfall", 0.0) or 0.0
    wind   = forecast.get("wind_speed", 5.0) or 5.0

    if rain > 15.0:
        return "heavy_rain"
    if rain > 5.0:
        return "moderate_rain"
    if temp >= 40.0 and rh < 30.0:
        return "heat_stress"
    if temp <= 10.0:
        return "frost_risk"
    if temp >= 35.0 and rh < 40.0 and rain < 1.0:
        return "drought_risk"
    if wind > 60.0:
        return "high_wind"
    if rh > 90.0 and rain > 1.0:
        return "foggy"
    return "clear"


# ---------------------------------------------------------------------------
# Persistence model (fallback)
# ---------------------------------------------------------------------------

class PersistenceModel:
    """Last observation + diurnal temperature adjustment."""

    def predict(self, last_obs: Dict[str, Any]) -> Dict[str, Any]:
        hour = datetime.utcnow().hour
        # Simple diurnal: peak at 14h, trough at 04h
        diurnal_delta = 2.0 * (1.0 - abs(hour - 14) / 14.0)
        base_temp = (last_obs.get("temperature") or 25.0)
        forecast = {
            "temperature": base_temp + diurnal_delta,
            "humidity":    last_obs.get("humidity", 65.0),
            "wind_speed":  last_obs.get("wind_speed", 8.0),
            "wind_dir":    last_obs.get("wind_dir", 180.0),
            "pressure":    last_obs.get("pressure", 1013.0),
            "rainfall":    last_obs.get("rainfall", 0.0),
            "model_used":  "persistence",
            "nwp_temp":    None,
            "correction":  0.0,
            "confidence":  0.4,
        }
        forecast["condition"] = classify_condition(forecast)
        return forecast


# ---------------------------------------------------------------------------
# Hybrid NWP + XGBoost MOS model
# ---------------------------------------------------------------------------

class HybridNWPModel:
    """
    MOS model: trains XGBoost on residuals between NWP and observations.
    At inference: final = nwp_forecast + xgboost_correction(features)

    Feature vector (11 features):
      nwp_temp, nwp_rainfall, humidity, wind_speed, pressure,
      station_altitude, soil_moisture,
      rolling_6h_error, recent_temp_trend,
      hour_sin, hour_cos, doy_sin
    """

    FEATURE_NAMES = [
        "nwp_temp", "nwp_rainfall", "humidity", "wind_speed", "pressure",
        "station_altitude", "soil_moisture",
        "rolling_6h_error", "recent_temp_trend",
        "hour_sin", "hour_cos", "doy_sin",
    ]

    def __init__(self, models_dir: str = "models"):
        self.models_dir  = models_dir
        self._model      = None
        self._trained    = False
        self._model_path = os.path.join(models_dir, "hybrid_mos.json")
        # Per-station rolling error history: {station_id: [(datetime, error), ...]}
        self._rolling_errors: Dict[str, List[Tuple[datetime, float]]] = {}

    # ------------------------------------------------------------------
    # Rolling error tracking
    # ------------------------------------------------------------------

    def record_error(self, station_id: str, error: float) -> None:
        """Record a prediction error for rolling-error feature computation."""
        if station_id not in self._rolling_errors:
            self._rolling_errors[station_id] = []
        self._rolling_errors[station_id].append((datetime.utcnow(), error))
        # Prune entries older than 48h
        cutoff = datetime.utcnow() - timedelta(hours=48)
        self._rolling_errors[station_id] = [
            (ts, e) for ts, e in self._rolling_errors[station_id] if ts >= cutoff
        ]

    def _get_rolling_error(self, station_id: str) -> float:
        """Mean absolute error over the last 6 hours for this station."""
        history = self._rolling_errors.get(station_id, [])
        if not history:
            return 0.0
        cutoff = datetime.utcnow() - timedelta(hours=6)
        recent = [abs(e) for ts, e in history if ts >= cutoff]
        return float(sum(recent) / len(recent)) if recent else 0.0

    # ------------------------------------------------------------------
    # Feature engineering
    # ------------------------------------------------------------------

    def _build_features(self, nwp: Dict[str, Any],
                         station_altitude: float = 0.0,
                         soil_moisture: float = 0.0,
                         station_id: str = "",
                         recent_temp_trend: float = 0.0) -> List[float]:
        """Build the 12-element feature vector."""
        ts = nwp.get("ts", "")
        try:
            dt   = datetime.fromisoformat(ts.replace("Z", ""))
            hour = dt.hour
            doy  = dt.timetuple().tm_yday
        except Exception:
            hour, doy = datetime.utcnow().hour, 180

        import math
        return [
            nwp.get("temperature", 25.0) or 25.0,   # nwp_temp
            nwp.get("rainfall",     0.0) or 0.0,     # nwp_rainfall
            nwp.get("humidity",    60.0) or 60.0,    # humidity
            nwp.get("wind_speed",   8.0) or 8.0,     # wind_speed
            nwp.get("pressure",  1013.0) or 1013.0,  # pressure
            station_altitude,                          # station_altitude (m)
            soil_moisture,                             # soil_moisture (0-1 or mm)
            self._get_rolling_error(station_id),       # rolling_6h_error (°C MAE)
            recent_temp_trend,                         # recent_temp_trend (°C/h)
            math.sin(2 * math.pi * hour / 24),        # hour_sin
            math.cos(2 * math.pi * hour / 24),        # hour_cos
            math.sin(2 * math.pi * doy / 365),        # doy_sin
        ]

    # ------------------------------------------------------------------
    # Training
    # ------------------------------------------------------------------

    def train(self, observations: List[Dict[str, Any]],
               nwp_data: List[Dict[str, Any]],
               station_altitude: float = 0.0,
               soil_moisture: float = 0.0) -> None:
        """Train XGBoost on (obs - NWP) residuals."""
        try:
            import xgboost as xgb
            import numpy as np

            if len(observations) < 5 or not nwp_data:
                log.info("Insufficient data for MOS training, will use persistence")
                return

            X, y = [], []
            temps = [o.get("temperature") for o in observations
                     if o.get("temperature") is not None]

            for i, obs in enumerate(observations):
                if obs.get("temperature") is None:
                    continue
                nwp      = nwp_data[0]
                nwp_temp = nwp.get("temperature", obs["temperature"])
                residual = obs["temperature"] - nwp_temp

                # Temperature trend: slope over available history window
                if i >= 3:
                    window = [observations[j].get("temperature") or obs["temperature"]
                              for j in range(max(0, i - 6), i + 1)]
                    trend = (window[-1] - window[0]) / max(1, len(window) - 1)
                else:
                    trend = 0.0

                sid = obs.get("station_id", "")
                feats = self._build_features(
                    nwp,
                    station_altitude=station_altitude,
                    soil_moisture=soil_moisture,
                    station_id=sid,
                    recent_temp_trend=trend,
                )
                X.append(feats)
                y.append(residual)

            if len(X) < 3:
                return

            self._model = xgb.XGBRegressor(
                n_estimators=100,
                max_depth=5,
                learning_rate=0.1,
                subsample=0.8,
                colsample_bytree=0.8,
                min_child_weight=3,
                random_state=42,
                verbosity=0,
            )
            self._model.fit(np.array(X), np.array(y))
            self._trained = True

            os.makedirs(self.models_dir, exist_ok=True)
            self._model.save_model(self._model_path)
            log.info("MOS model trained on %d samples (alt=%.0fm, sm=%.2f)",
                     len(X), station_altitude, soil_moisture)
        except Exception as exc:
            log.warning("MOS training failed: %s", exc)

    # ------------------------------------------------------------------
    # Load / save
    # ------------------------------------------------------------------

    def load_if_exists(self) -> bool:
        if not os.path.exists(self._model_path):
            return False
        try:
            import xgboost as xgb
            self._model = xgb.XGBRegressor()
            self._model.load_model(self._model_path)
            self._trained = True
            return True
        except Exception as exc:
            log.warning("Failed to load MOS model: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Prediction
    # ------------------------------------------------------------------

    def predict(self, nwp_forecast: Dict[str, Any],
                 station_altitude: float = 0.0,
                 soil_moisture: float = 0.0,
                 station_id: str = "",
                 recent_temp_trend: float = 0.0) -> Dict[str, Any]:
        """Produce corrected forecast. Records error for rolling tracker."""
        nwp_temp   = nwp_forecast.get("temperature", 25.0) or 25.0
        correction = 0.0
        model_used = "nwp_only"

        if self._trained and self._model is not None:
            try:
                import numpy as np
                feat_vec = self._build_features(
                    nwp_forecast,
                    station_altitude=station_altitude,
                    soil_moisture=soil_moisture,
                    station_id=station_id,
                    recent_temp_trend=recent_temp_trend,
                )
                correction = float(self._model.predict(np.array([feat_vec]))[0])
                correction = max(-8.0, min(8.0, correction))  # sanity clamp
                model_used = "hybrid_mos"
            except Exception as exc:
                log.warning("MOS inference failed: %s", exc, exc_info=True)

        final_temp = nwp_temp + correction

        # Wider confidence interval when correction is large
        base_uncertainty = 1.5
        confidence = max(0.5, 0.85 - abs(correction) * 0.05)

        result = dict(nwp_forecast)
        result["temperature"] = final_temp
        result["nwp_temp"]    = nwp_temp
        result["correction"]  = correction
        result["model_used"]  = model_used
        result["confidence"]  = confidence
        result["condition"]   = classify_condition(result)
        return result


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def create_forecast_model(models_dir: str = "models") -> HybridNWPModel:
    model = HybridNWPModel(models_dir=models_dir)
    model.load_if_exists()
    return model


# ---------------------------------------------------------------------------
# Forecasting step runner
# ---------------------------------------------------------------------------

async def run_forecast_step(
    station,
    clean_reading: Optional[Dict[str, Any]],
    open_meteo_client,
    model: HybridNWPModel,
    persistence_model: PersistenceModel,
    nasa_client=None,
    station_history: Optional[List[Dict[str, Any]]] = None,
) -> Optional[Dict[str, Any]]:
    """Run complete forecast for one station. Returns forecast record."""

    nwp_forecasts = await open_meteo_client.get_forecast(station.lat, station.lon, hours=24)

    if not clean_reading and not nwp_forecasts:
        return None

    # Fetch soil moisture from NASA POWER (reuse existing client, non-blocking)
    soil_moisture = 0.0
    if nasa_client is not None:
        try:
            nasa = await nasa_client.get_current(station.lat, station.lon)
            if nasa and nasa.get("rainfall") is not None:
                # PRECTOTCORR (mm/day) as a proxy for antecedent soil moisture
                soil_moisture = min(1.0, (nasa["rainfall"] or 0.0) / 20.0)
        except Exception:
            pass

    # Temperature trend from history (°C/h)
    recent_temp_trend = 0.0
    if station_history and len(station_history) >= 3:
        recent_temps = [h.get("temperature") for h in station_history[-5:]
                        if h.get("temperature") is not None]
        if len(recent_temps) >= 2:
            recent_temp_trend = (recent_temps[-1] - recent_temps[0]) / max(1, len(recent_temps) - 1)
    elif clean_reading and clean_reading.get("temperature") is not None:
        recent_temp_trend = 0.0

    # Use full station history for training when available
    training_obs = None
    if station_history and len(station_history) >= 5:
        training_obs = station_history
    elif clean_reading:
        training_obs = [clean_reading]

    if nwp_forecasts:
        if training_obs:
            model.train(
                training_obs, nwp_forecasts[:1],
                station_altitude=station.altitude_m,
                soil_moisture=soil_moisture,
            )
        forecast = model.predict(
            nwp_forecasts[0],
            station_altitude=station.altitude_m,
            soil_moisture=soil_moisture,
            station_id=station.station_id,
            recent_temp_trend=recent_temp_trend,
        )
        # Record error for rolling tracker (observed - predicted, if obs available)
        if clean_reading and clean_reading.get("temperature") is not None:
            error = clean_reading["temperature"] - forecast["temperature"]
            model.record_error(station.station_id, error)
    elif clean_reading:
        forecast = persistence_model.predict(clean_reading)
    else:
        return None

    now = datetime.utcnow()
    return {
        "id":           f"{station.station_id}_{now.strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:4]}",
        "station_id":   station.station_id,
        "issued_at":    now.isoformat(),
        "valid_for_ts": (now + timedelta(hours=6)).isoformat(),
        **{k: v for k, v in forecast.items()
           if k in ("temperature","humidity","wind_speed","rainfall",
                    "condition","model_used","nwp_temp","correction","confidence")},
    }
