#!/usr/bin/env python3
"""DVC stage: train XGBoost MOS model on exported Parquet data, emit metrics."""

from __future__ import annotations

import json
import math
import os
import sys
from collections import defaultdict
from datetime import datetime

# Allow imports from project root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split

from src.forecasting import HybridNWPModel

PARQUET_PATH = "data/training_export.parquet"
MODEL_PATH = "models/hybrid_mos.json"
METRICS_PATH = "metrics/mos_metrics.json"

FEATURE_NAMES = HybridNWPModel.FEATURE_NAMES


def load_and_engineer(df: pd.DataFrame) -> tuple:
    """Compute engineered features from exported Parquet, return X and y arrays."""
    df = df.dropna(subset=["actual_temp", "nwp_temp"])

    if df.empty:
        print("ERROR: No valid rows in training export.")
        sys.exit(1)

    X_list = []
    y_list = []

    for station_id, group in df.groupby("station_id"):
        srows = group.sort_values("obs_ts").to_dict("records")

        for i, row in enumerate(srows):
            actual_temp = row["actual_temp"]
            nwp_temp = row["nwp_temp"]
            residual = actual_temp - nwp_temp

            humidity = row.get("humidity") or 60.0
            wind_speed = row.get("wind_speed") or 8.0
            pressure = row.get("pressure") or 1013.0
            nwp_rainfall = row.get("nwp_rainfall") or 0.0
            actual_rainfall = row.get("actual_rainfall") or 0.0
            prior_correction = row.get("prior_correction")

            station_altitude = 0.0
            soil_moisture = min(1.0, actual_rainfall / 20.0)

            # Rolling 6h error: mean absolute prior_correction over last 6 rows
            window_start = max(0, i - 6)
            corrections = [
                abs(srows[j]["prior_correction"])
                for j in range(window_start, i)
                if srows[j].get("prior_correction") is not None
            ]
            rolling_6h_error = (
                sum(corrections) / len(corrections) if corrections else 0.0
            )

            # Recent temp trend: slope over last 6 rows
            if i >= 3:
                temps_window = [
                    srows[j]["actual_temp"]
                    for j in range(max(0, i - 6), i + 1)
                    if srows[j].get("actual_temp") is not None
                ]
                if len(temps_window) >= 2:
                    recent_temp_trend = (
                        (temps_window[-1] - temps_window[0])
                        / max(1, len(temps_window) - 1)
                    )
                else:
                    recent_temp_trend = 0.0
            else:
                recent_temp_trend = 0.0

            try:
                obs_ts = row["obs_ts"]
                if isinstance(obs_ts, str):
                    dt = datetime.fromisoformat(obs_ts.replace("Z", ""))
                else:
                    dt = obs_ts
                hour = dt.hour
                doy = dt.timetuple().tm_yday
            except Exception:
                hour, doy = 12, 180

            hour_sin = math.sin(2 * math.pi * hour / 24)
            hour_cos = math.cos(2 * math.pi * hour / 24)
            doy_sin = math.sin(2 * math.pi * doy / 365)

            feature_vec = [
                nwp_temp,
                nwp_rainfall,
                humidity,
                wind_speed,
                pressure,
                station_altitude,
                soil_moisture,
                rolling_6h_error,
                recent_temp_trend,
                hour_sin,
                hour_cos,
                doy_sin,
            ]

            X_list.append(feature_vec)
            y_list.append(residual)

    return np.array(X_list), np.array(y_list)


def main() -> None:
    if not os.path.exists(PARQUET_PATH):
        print(f"ERROR: Training data not found at {PARQUET_PATH}")
        print("Run  python scripts/export_training_data.py  first.")
        sys.exit(1)

    os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
    os.makedirs(os.path.dirname(METRICS_PATH), exist_ok=True)

    df = pd.read_parquet(PARQUET_PATH)
    X, y = load_and_engineer(df)

    print(f"Training samples: {len(X)}")
    print(f"Features: {len(FEATURE_NAMES)}")
    print(f"Residual stats — mean: {y.mean():.3f}, std: {y.std():.3f}")

    if len(X) < 10:
        print("WARNING: Very few training samples, model may not generalize.")

    # Train/test split (80/20)
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42
    )

    model = xgb.XGBRegressor(
        n_estimators=100,
        max_depth=5,
        learning_rate=0.1,
        subsample=0.8,
        colsample_bytree=0.8,
        min_child_weight=3,
        random_state=42,
        verbosity=0,
    )
    model.fit(X_train, y_train)

    # Evaluate on test set
    y_pred = model.predict(X_test)
    rmse = float(np.sqrt(mean_squared_error(y_test, y_pred)))
    mae = float(mean_absolute_error(y_test, y_pred))
    r2 = float(r2_score(y_test, y_pred))

    # Feature importances
    importances = model.feature_importances_
    feature_importance = {
        name: round(float(imp), 4)
        for name, imp in zip(FEATURE_NAMES, importances)
    }

    # Save model
    model.save_model(MODEL_PATH)
    print(f"Model saved to {MODEL_PATH}")

    # Save metrics
    metrics = {
        "rmse": round(rmse, 4),
        "mae": round(mae, 4),
        "r2": round(r2, 4),
        "n_train": len(X_train),
        "n_test": len(X_test),
        "residual_mean": round(float(y.mean()), 4),
        "residual_std": round(float(y.std()), 4),
        "feature_importances": feature_importance,
    }
    with open(METRICS_PATH, "w") as f:
        json.dump(metrics, f, indent=2)
    print(f"Metrics saved to {METRICS_PATH}")

    # Print summary
    print("\n--- Training Results ---")
    print(f"  RMSE:  {rmse:.4f} C")
    print(f"  MAE:   {mae:.4f} C")
    print(f"  R2:    {r2:.4f}")
    print(f"  Train: {len(X_train)} samples, Test: {len(X_test)} samples")
    print("\n  Feature importances (top 5):")
    sorted_imp = sorted(feature_importance.items(), key=lambda x: x[1], reverse=True)
    for name, imp in sorted_imp[:5]:
        print(f"    {name:>22s}: {imp:.4f}")


if __name__ == "__main__":
    main()
