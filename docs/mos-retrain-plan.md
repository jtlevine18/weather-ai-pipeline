# MOS Retrain Plan — Weather AI 2

Replacing the broken per-run XGBoost MOS with a proper accumulate-and-retrain pattern modelled on Market Intelligence's `scripts/retrain_mos.py`.

---

## 1. Current state

- **Bug A (per-run retrain):** `src/forecasting.py:472-477` (`run_forecast_step`) calls `model.train(training_obs, nwp_forecasts[:1], ...)` every pipeline run, per station. That throws away any previously trained model (XGBoost is re-instantiated in `HybridNWPModel.train` at `src/forecasting.py:212-222`) and trains a fresh tree on 5-10 observations for just that one station.
- **Bug B (degenerate features):** `src/forecasting.py:186` hard-codes `nwp = nwp_data[0]` inside the training loop, so every training row uses the *same* NWP forecast. All rows share identical `nwp_temp`, `nwp_rainfall`, `humidity`, `wind_speed`, `pressure`, `station_altitude`, `soil_moisture`, `hour_sin/cos`, `doy_sin`. The only features that vary within a station's training batch are `rolling_6h_error` and `recent_temp_trend`, and both are near-zero for small histories. XGBoost has no signal and collapses to the mean residual — a station-level bias offset.
- **Bug C (no eval gate):** `train()` saves whatever it fits with no held-out test, no minimum-sample check beyond `len(X) < 3`, and silently clamps inference to ±8 °C (`src/forecasting.py:289`). There is no promotion gate, so a bad retrain overwrites `models/hybrid_mos.json` unconditionally.
- **Bug D (model clobbering across stations):** The pipeline iterates stations; each one retrains on its own 5-10 obs and saves to the same `models/hybrid_mos.json` path. The final file reflects only the *last* station processed.

**Data already in Neon we can use as training pairs:**
- `forecasts` table (`src/database/__init__.py:66-83`): has `station_id`, `valid_for_ts`, `forecast_day`, `nwp_temp`, `temperature` (corrected), `correction`, `model_used`, `nwp_source`, `issued_at`, `humidity`, `wind_speed`, `rainfall`, `confidence`.
- `clean_telemetry` (`src/database/__init__.py:31-45`): has `station_id`, `ts`, `temperature`, `humidity`, `wind_speed`, `pressure`, `rainfall`, `quality_score`.
- **Pair construction already exists:** `scripts/export_training_data.py:21-46` joins `clean_telemetry.ts ≈ forecasts.valid_for_ts` via `date_trunc('hour', ...)` filtered to `forecast_day = 0`. This is the right join — hourly bucket match, day-0 only. A ±6h tolerance is unnecessary because `valid_for_ts` is written by us and can be snapped to the hour of the clean reading.

---

## 2. MI reference pattern (`market-intelligence/scripts/retrain_mos.py`)

- **Pull training pairs (lines 40-76):** one SQL query joins `price_forecasts` (predicted) with `market_prices` (actual) on `(mandi_id, commodity_id)`. Returns a DataFrame of `(predicted, actual, horizon_days, forecast_date)`. Guards with `min_rows=50` (demoted to 20 in `main()`); exits 0 if under threshold.
- **Feature engineering (lines 91-175):** reuses the same 8 features the live `XGBoostPriceModel` uses (`current_reconciled_price`, `price_trend_7d`, `price_volatility_30d`, `seasonal_index`, `days_since_harvest`, `days_until_next_harvest`, `month_sin`, `month_cos`). Derives trend/volatility from the `market_prices` history pulled separately. The label is **the residual** `actual - predicted`.
- **Train/eval split (lines 194-234):** filters to rows matching each horizon (7/14/30d). If `< 20` rows for a horizon, skips. Temporal 80/20 split. Reports RMSE before vs after MOS per horizon and logs an "improvement_pct".
- **Model save/load:** writes `models/mos_{horizon}d.json` per horizon. Live pipeline loads via `ChronosXGBoostForecaster.load()` in `src/forecasting/price_model.py:900-949` — it reads the joblib blob, sets `_mos_trained=True`, and falls back to `XGBoost standalone` if load fails.
- **Trigger:** monthly GitHub Action on the 4th Monday (`.github/workflows/weekly-pipeline.yml` in MI) or manual `POST /api/pipeline/retrain-mos`.

---

## 3. Proposed Weather AI 2 design

### Schema changes
**None required.** `forecasts` already has `nwp_temp` (raw NWP) and `temperature` (corrected), and `clean_telemetry` has `temperature`. The existing `export_training_data.py` JOIN at `src/database/...` (well, `scripts/`) already produces the training set. Recommended small additions for observability, not correctness:
- Add `mos_model_version VARCHAR` to `forecasts` (nullable) — lets us attribute each forecast row to a specific retrain. Idempotent `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` in the DDL.
- Add a new `mos_model_runs` table: `(id, trained_at, n_train, n_test, rmse_before, rmse_after, mae, r2, model_path, promoted boolean)`. Gives us a durable audit trail of every retrain attempt (including rejects).

### Feature vector
**Keep the existing 12 features, but compute them correctly from the joined table.** The current `scripts/train_mos.py:31-121` is almost right — it already derives rolling-6h-error from `prior_correction`, trend from actual temps, and time-of-day/year encodings per row. Two fixes:
1. Line 57: `station_altitude = 0.0` is hard-coded. Look up `altitude_m` from `config.py` via `station_id`.
2. Lines 65-69: rolling error uses `abs(prior_correction)`, but `correction` is the MOS output, not the NWP error. Swap to `abs(actual_temp - nwp_temp)` computed from the previous row's residual. (That's the genuine leading signal.)

We should **not** simplify the feature set before having real data on which features matter. Post-train feature importances will drive pruning in a later pass.

### Training cadence and trigger
**Weekly, chained to the existing pipeline GitHub Action.** Mirror the MI cadence but tighter because Weather AI 2 runs weekly, not daily. The `.github/workflows/weekly-pipeline.yml` already wakes the Space, triggers, and pauses. Append a conditional "retrain MOS" step that runs on the 4th week of each month (or every run, with the eval gate preventing promotion when data is insufficient). Two triggers:
1. **Primary: GitHub Action step** — after pipeline completes, call `POST /api/pipeline/retrain-mos` on the runner Space.
2. **Manual: endpoint on `src/api.py`** — same URL, for ad-hoc retraining during debugging.

### Bootstrap problem
First N runs have no paired data in Neon. Fallback chain:
1. Ship the repo with a **seed model** at `models/hybrid_mos.json` trained offline on synthetic residuals (or a no-op zero-correction model). Commit to git so every clone has it.
2. If pairs `< MIN_PAIRS` (suggest 200 across all stations, or 10/station avg), retrain exits early and the seed stays in place.
3. If the seed fails to load at runtime, fall through to `nwp_only` — exactly the current "we're dropping MOS entirely" behavior. This is the safest degradation; we'd rather serve raw GraphCast than a bad correction.

### Per-station vs single global model
**One global model with `station_id` as a learned feature.** Reasoning:
- 20 stations × ~30 weekly forecasts × ~52 weeks = ~31k rows per year total. Per-station that's 1.5k — enough for XGBoost, but fragmented training is fragile.
- Pooling lets the model learn cross-station patterns (coastal Kerala vs inland Tamil Nadu regimes) and regularizes small stations.
- Station identity can enter two ways: (a) keep `station_altitude` as the only continuous station feature for now; (b) add a learned `station_enc` integer column (one-hot not needed — XGBoost handles integer categories natively with `enable_categorical=True`).
- MI gets away with one-model-per-horizon because horizons are fundamentally different time scales. Weather AI 2's analog would be one-model-per-`forecast_day`, but day-0 dominates training data and later days degrade smoothly. Skip that for v1; revisit once we have >5k pairs.

### Live pipeline model loading
**Reuse `load_if_exists` as-is.** `HybridNWPModel.load_if_exists` (`src/forecasting.py:245-262`) already tries `models/hybrid_mos.json` and `/tmp/models/hybrid_mos.json`. The retrain script writes to the same path. The **critical deletion**: remove the `model.train(...)` call at `src/forecasting.py:472-477` entirely. Forecast step should be inference-only. Training is strictly the retrain job's job.

### Safety net
Four gates, all in the retrain script:
1. **Minimum samples:** hard-fail if `< 200` total pairs or `< 10` pairs for any station we'd serve from the model. Log count per station.
2. **Temporal train/test split:** 80/20 by `obs_ts`, not random. Random split leaks future into past for a time-series.
3. **Promotion gate:** `rmse_after < rmse_before * 0.95` (at least 5% improvement on held-out test) AND `rmse_after < 3.0 °C` absolute. Otherwise: log to `mos_model_runs` with `promoted=false`, do **not** overwrite `models/hybrid_mos.json`.
4. **Inference clipping:** keep the `max(-8, min(8, correction))` clamp at `src/forecasting.py:289`. Belt and suspenders for any future bad retrain that slips past the gate.

---

## 4. Implementation order

**Week 1 — Clean up and baseline**
- Remove the broken `model.train(...)` call from `run_forecast_step` (line 472-477). Keep `load_if_exists` → predict path. Verify pipeline serves `graphcast_only` correctly across all stations.
- Commit a seed `models/hybrid_mos.json` trained on the current DVC export (run `export_training_data.py` + `train_mos.py` against Neon as it stands — even with limited pairs, it's better than nothing and exercises the full path).
- Add the observability bits: `mos_model_version` column (nullable) and the `mos_model_runs` table.

**Week 2 — Retrain script (port from MI)**
- Create `scripts/retrain_mos.py` modeled on MI's version. Internally, it should mostly be thin wrappers over the existing `export_training_data.py` (pull pairs) + `train_mos.py` (fit) logic, plus the four safety gates and a write to `mos_model_runs`.
- Fix the two feature bugs in `train_mos.py` (altitude lookup, rolling error source).
- Add eval logging: per-station RMSE before/after, feature importances, n_samples.

**Week 3 — Wire the retrain endpoint**
- Add `POST /api/pipeline/retrain-mos` to `src/api.py` — invokes `scripts/retrain_mos.py` in a background task, returns run_id. Mirrors MI's endpoint.
- Extend `.github/workflows/weekly-pipeline.yml` with a conditional retrain step (runs after pipeline completes; guarded by `if: github.event.schedule && date +%U % 4 == 0` or simpler: every run, relying on the promotion gate).

**Week 4 — Enable MOS in live pipeline**
- In `HybridNWPModel.load_if_exists`, log the loaded `mos_model_version` and surface it into forecast rows via the new column.
- Flip `model_used` in the inference path to `graphcast_mos` when a promoted model is loaded. This is already wired in `run_forecast_step:495-500`; it just needs a trained model to light up.
- Dashboard tab (System → Model Performance) reads `mos_model_runs` to plot RMSE-over-time. Small scope — just a table + a sparkline.

---

## 5. Open questions

- **How often do we have matched pairs in practice?** Pipeline runs weekly. A forecast issued Monday has `forecast_day=0` for Monday. `clean_telemetry` for Monday exists after the same run. So every run produces ~20 day-0 pairs (one per station). That's ~1000 pairs/year, which is fine for a single global model but marginal for per-station. Confirms the "one global model" choice.
- **Does `valid_for_ts` actually land on the same hour as `clean_telemetry.ts`?** The aggregation in `aggregate_to_daily` emits `ts = local_noon_utc` (line 361-365 in `src/forecasting.py`), not the hour of the observation. `clean_telemetry` is hourly. The existing JOIN in `export_training_data.py` uses `date_trunc('hour', ...)` — this will only match if obs happens to be at local noon UTC, which is rare. **This is a likely bug in the existing exporter and needs a tolerance-based join (`ABS(EXTRACT(EPOCH FROM c.ts - f.valid_for_ts)) < 3*3600`) or a change to what we store in `valid_for_ts`.** Flagging for Jeff's review.
- **Should `forecasts.nwp_temp` be the raw NWP, or is it already the corrected forecast?** Code at `src/forecasting.py:300-301` sets both `nwp_temp = nwp_forecast.get("temperature")` (raw) and `temperature = final_temp` (corrected). Looks clean, but worth spot-checking a few recent rows.
- **Rainfall residuals:** MOS currently only corrects temperature. Should the retrain also learn a rainfall correction? NWP rainfall bias is typically larger than temperature bias. Out of scope for v1 but worth scoping for v2.
- **Per-station RMSE variance:** we'll know after the first real retrain whether a global model is enough or if coastal/inland split into two models would help. Don't pre-optimize.
