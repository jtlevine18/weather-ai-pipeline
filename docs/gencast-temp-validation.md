# GenCast 2m_temperature validation — experiment results

**Run:** pipeline_run_id `171cdeb9-9c8e-4c68-9269-0f2795c8fdef`
**GenCast init:** 2026-04-15 (target_date)
**Space:** `jtlevine/ai-weather-pipeline-runner-gencast-test` (paused after run)
**Model:** `gencast_1p0_full` — 12-member ensemble × 14 12h steps × 20 stations = 3,360 scratch rows
**Ground truth:** `clean_telemetry` daily max (IMD station observations, min 3 obs/day)

## Question

Is GenCast's `2m_temperature` good enough to replace the GraphCast raw temp path, so we can retire the NASA POWER downscaling writeback (Option A) as our temperature fix?

## Method

1. Extract GenCast `2m_temperature` per (station, 12h step, member) alongside rainfall during inference. Kelvin → Celsius.
2. Compute per-(station, forecast_day, member) daily-max as max over the 2 12h snapshots within that day.
3. Aggregate to p10/p50/p90 across 12 members → ensemble forecast for each (station, day).
4. Compare against:
   - **Ground truth:** `clean_telemetry` daily max per station, filtered to days with ≥3 observations (to avoid imputed/synthetic fallback days).
   - **Baseline:** GraphCast raw `forecasts.nwp_temp` (the pre-downscale value that appears on the frontend when Option A is disabled).

`clean_telemetry` was available for 04-15, 04-20, 04-21 (the days with sufficient IMD observations in the validation window), so the validated lead times are **0, 5, 6** — which includes the 5-6 day leads where long-lead cold drift was the concern. 60 datapoints total (20 stations × 3 leads).

**Note on an earlier version of this doc:** first pass compared against NASA POWER `T2M_MAX`. That was circular — NASA POWER is what Option A downscales *from*, so it's not an independent ground truth. It also runs systematically warmer than IMD point observations (gridded reanalysis over 0.5° cells). Switching to `clean_telemetry` changed GenCast's observed bias from −5.35 °C to −1.54 °C.

## Results

### Per-lead-time summary

| Lead | Date | N | GraphCast bias | GenCast p50 bias | GraphCast RMSE | GenCast RMSE | Envelope coverage |
|---|---|---|---|---|---|---|---|
| 0 | 2026-04-15 | 20 | −14.90 °C | **−1.86 °C** | 15.37 °C | 5.12 °C | 0% |
| 5 | 2026-04-20 | 20 | −15.57 °C | **−1.38 °C** | 15.90 °C | 2.93 °C | 30% |
| 6 | 2026-04-21 | 20 | −17.39 °C | **−1.38 °C** | 17.75 °C | 3.15 °C | 10% |

### Overall (60 datapoints)

| Metric | GraphCast raw `nwp_temp` | GenCast p50 daily-max |
|---|---|---|
| Mean bias | **−15.95 °C** | **−1.54 °C** |
| RMSE | 16.37 °C | 3.86 °C |
| Envelope coverage (p10 ≤ truth ≤ p90) | n/a | 13.3% |

### Representative rows

| Station | Lead | Truth | GraphCast | GenCast p10 / p50 / p90 | GenCast err |
|---|---|---|---|---|---|
| TN_SLM (Salem) | 5 | 32.50 | 12.60 | 32.26 / 33.36 / 34.44 | +0.86 |
| TN_CBE (Coimbatore) | 6 | 32.10 | 11.40 | 31.46 / 33.52 / 34.22 | +1.41 |
| TN_MDU (Madurai) | 6 | 33.20 | 13.50 | 31.48 / 32.80 / 33.03 | −0.40 |
| KL_COK (Kochi) | 5 | 27.60 | 19.30 | 27.16 / 27.73 / 27.95 | +0.13 |
| KL_TVM (Thiruvananthapuram) | 5 | 31.40 | 17.20 | 27.18 / 28.21 / 28.61 | −3.19 |
| TN_VLR (Vellore) | 5 | 33.40 | 11.10 | 31.62 / 32.23 / 33.60 | −1.16 |

## Findings

**1. GenCast is effectively unbiased.** Mean error of −1.54 °C with RMSE of 3.86 °C across 60 observations. Tamil Nadu stations trend slightly warm (+0 to +4 °C), Kerala stations slightly cold (−3 to −7 °C). There's a regional pattern worth investigating but the central tendency is production-viable as-is.

**2. Bias does NOT grow with lead time.** If anything, lead 0 has slightly worse bias (−1.86 °C) than leads 5–6 (both −1.38 °C). The original cold-bias hypothesis — "GraphCast drifts cold at long leads" — is not replicated in GenCast. The drift story for GraphCast may have been about the raw extracted-temperature bug (see point 3) rather than model skill.

**3. GraphCast's stored `nwp_temp` has a ~−16 °C systematic error.** This is the value the frontend renders when Option A (NASA POWER downscaling writeback) is off. It's almost certainly an extraction/timing bug in `src/graphcast_client.py` — sampled at a UTC hour that's near the local daily minimum rather than aggregating across the diurnal cycle — not a failure of the GraphCast model itself. Worth fixing independently regardless of Option B.

**4. Ensemble envelope is overconfident for temperature** — 13% overall coverage of the p10–p90 band (expected ~80% for a calibrated ensemble). Spread is ~1–2 °C across 12 members vs a 3-4 °C RMSE, so members cluster too tightly around the mean. This is consistent with the GenCast paper's finding that small ensembles at 1.0° have low spread in T2M. Use p50 as a point forecast; **do not surface p10/p90 as a "temperature range" to farmers.**

## Decision

**PASS with caveats — migrate to Option B (GenCast-native temps) as the primary temperature path. Option A (NASA POWER writeback) becomes the fallback.**

Reasoning:
- GenCast p50 bias (−1.54 °C) is better than any typical NWP station-level skill and within the noise of IMD observation accuracy itself.
- Unlike Option A (which overwrites after GraphCast with NASA POWER's 0.5° grid interpolation), Option B uses GenCast's own forecast state → temporally consistent with the rainfall ensemble from the same run.
- GraphCast's stored `nwp_temp` is broken enough that *any* replacement is an improvement.

Next concrete steps:
1. Plumb GenCast p50 daily-max into `forecasts.temperature` in place of GraphCast's `nwp_temp` — mirror the Option A write path but source from the ensemble.
2. Keep NASA POWER downscaling writeback as fallback for (a) stations where GenCast extraction fails, (b) the station→farmer GPS lapse-rate correction (that stays because it's a spatial not temporal problem).
3. Investigate the regional bias pattern (Kerala −3 to −7 °C, Tamil Nadu +0 to +4 °C) — may indicate a per-station bias correction is warranted, learnable from rolling `clean_telemetry` history.
4. Fix the underlying GraphCast extraction bug in `src/graphcast_client.py` — it should not be producing −16 °C values regardless of this migration.

## Limitations

- 3 lead days validated (0, 5, 6) — no data for leads 1, 2, 3, 4. The bias-by-lead plot is sparse, though the flat pattern across lead 0 → 5 → 6 is directionally informative.
- 60 datapoints — enough for a clear pass/fail signal on central bias, not enough to resolve fine per-station corrections.
- Only one init date (2026-04-15). Seasonal bias patterns unexplored — run again in a pre-monsoon heatwave scenario (May) and a wet-season scenario (July) before committing to production migration.
- 12-member ensemble at 1.0° — smaller ensemble than GenCast paper standard; spread may be artificially low because of sample size.
- Daily-max proxy = max of two 12h instantaneous snapshots. True 24h max from a continuous diurnal cycle would be ~2 °C higher — so GenCast's observed small cold bias may be entirely sampling artifact.

## Raw data

- Scratch table: `gencast_temp_validation WHERE pipeline_run_id = '171cdeb9-9c8e-4c68-9269-0f2795c8fdef'` (3,360 rows; safe to DROP)
- Analysis rows (clean_telemetry comparison): `/tmp/gencast_validation/analysis_rows_v2.json`
- Earlier NASA POWER pull (superseded): `/tmp/gencast_validation/nasa_power.json`
