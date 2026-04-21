# GenCast 0.25° Integration Plan — Weather AI 2

Replacing GraphCast 0.25° deterministic with **GenCast 0.25° probabilistic** (50-member ensemble) on a 4× A100 HF Space. GraphCast stays as a fallback. Output gains quantile columns and `P(rain > threshold)` which propagate through the advisory classifier, RAG + Claude prompt, and frontend.

---

## 1. Why this path

- **Probabilistic rainfall is the win.** A farmer's question is "what's the chance of moderate rain tomorrow?", not "predict mm to 0.1 resolution." GenCast's ensemble spread answers that directly.
- **Single model, honest story.** "We run GenCast in production and evaluate with counterfactual decision regret" is a 2025-current narrative and fits LastMileBench directly.
- **Infrastructure fits.** 4× A100 at $10/hr on HF has enough host RAM (~568 GB, well past GenCast's 300 GB need) and single-GPU 80 GB VRAM (past the 60 GB need). No sharding, no external compute.
- **Cost is ~$22/month** for a weekly paused pipeline. Delta from today is ~$17/month.
- **GraphCast stays as real fallback** — if GenCast fails (GCS outage, OOM, timeout), the pipeline degrades to deterministic GraphCast rather than all the way to Open-Meteo.

## 2. What's explicitly out of scope

- XGBoost MOS (separately planned in `mos-retrain-plan.md`; may become unnecessary with probabilistic outputs).
- NeuralGCM or Open-Meteo — they stay in the degradation chain, no changes.
- Downscaling logic (IDW + lapse-rate at station grid is unchanged).
- Healing logic.
- Advisory translation language handling.

## 3. Licensing note (must land on a page)

GenCast weights are **CC BY-NC-SA 4.0** (non-commercial). The code is Apache 2.0, but the weights carry the restriction. For a portfolio demo and Gates Foundation (non-profit) use this is fine. Anything monetized — paid client work, commercial products — is not. The `/about` page or the Forecasts page footer on the frontend needs a one-line attribution: *"Forecasts powered by GenCast (Google DeepMind, CC BY-NC-SA 4.0, non-commercial research use)."*

---

## 4. Phase 0 — Load test (gates everything else)

**Goal:** confirm GenCast 0.25° actually runs on a 4× A100 HF Space, measure real inference time, watch peak memory.

**Harness** (~80 lines, `scripts/gencast_load_test.py`):
1. Install `graphcast` from the DeepMind GitHub archive.
2. Download the 0.25° operational checkpoint from `gs://dm_graphcast/gencast/`.
3. Fetch ERA5 initial conditions for a recent date from WeatherBench2 ARCO Zarr (same bucket GraphCast uses).
4. Run **one single-member** forecast, 7-day horizon.
5. Log peak host RSS + peak VRAM at each step to `/tmp/gencast_load.log`.
6. If single-member succeeds, run a **5-member ensemble** as a timing smoke test.
7. Exit cleanly, print summary.

**Procedure:**
1. Clone the existing Space, upgrade hardware to 4× A100 in Settings.
2. Push just this harness (not the full pipeline).
3. Wake Space, run `python scripts/gencast_load_test.py` via the existing trigger endpoint or a one-off script step.
4. Pause the Space, read the log.

**Decision gate:**
- **Pass:** Peak host RAM < 500 GB, single-member forecast < 5 min. Proceed to Phase 1.
- **Fail (OOM):** Path C' dies. Fall back to Path C (GraphCast + rainfall QM-MOS).
- **Pass but slow** (single-member > 10 min): 50-member ensemble would be too slow. Drop ensemble size to 20–30 and re-test. If still unworkable, consider 1.0° GenCast or Path C.

**Cost:** ~$10–20 depending on how long the test runs. Cheap gate.

---

## 5. Phase 1 — `gencast_client.py` (Week 1)

New file `src/gencast_client.py`, modeled on `src/graphcast_client.py`. Keep GraphCast alongside.

### Public interface

```python
class GenCastClient:
    def __init__(self, forecast_hours: int = 168, ensemble_size: int = 50): ...
    async def forecast(self, stations, target_date=None) -> tuple[list[dict], GenCastResult]: ...
```

Output shape per station: `{station_id, issued_at, ensemble: [mem0, mem1, ...], summary: {p10, p50, p90, prob_5mm, prob_15mm}}` at each 12-hour step.

### Key differences from GraphCast client

| | GraphCast | GenCast |
|---|---|---|
| Model weights path | `gs://dm_graphcast/params/...` | `gs://dm_graphcast/gencast/...` |
| Initial conditions | 2 timesteps, 6h apart | 2 timesteps, **12h apart** |
| Native time step | 6h | **12h** |
| Rollout | deterministic | diffusion sampler, N=50 members |
| Output variables | ~80 channels | ~80 channels (surface: `2t`, `10u`, `10v`, `msl`, **`tp12h`**) |
| VRAM | ~40 GB | ~60 GB |
| Host RAM | ~100 GB | ~300 GB |
| Attention mode (GPU) | default | `attention_type="triblockdiag_mha"`, `mask_type="full"` (GPU doesn't support splash attention) |

### Station extraction

Same bilinear interpolation as `_extract_station_forecasts` in `graphcast_client.py`, but applied per ensemble member → output shape `(ensemble=50, time=14, station=20, var=5)`.

### Fallback plumbing

`is_gencast_available()` helper (mirrors `is_graphcast_available()`) checks import + GPU. If unavailable, pipeline init picks GraphCast.

---

## 6. Phase 2 — Pipeline integration + schema (Week 2)

### 6a. Schema additions (all nullable, idempotent)

In `src/database/__init__.py` DDL:

```sql
ALTER TABLE forecasts ADD COLUMN IF NOT EXISTS temp_p10          DOUBLE PRECISION;
ALTER TABLE forecasts ADD COLUMN IF NOT EXISTS temp_p50          DOUBLE PRECISION;
ALTER TABLE forecasts ADD COLUMN IF NOT EXISTS temp_p90          DOUBLE PRECISION;
ALTER TABLE forecasts ADD COLUMN IF NOT EXISTS rain_p10          DOUBLE PRECISION;
ALTER TABLE forecasts ADD COLUMN IF NOT EXISTS rain_p50          DOUBLE PRECISION;
ALTER TABLE forecasts ADD COLUMN IF NOT EXISTS rain_p90          DOUBLE PRECISION;
ALTER TABLE forecasts ADD COLUMN IF NOT EXISTS rain_prob_1mm     DOUBLE PRECISION;
ALTER TABLE forecasts ADD COLUMN IF NOT EXISTS rain_prob_5mm     DOUBLE PRECISION;
ALTER TABLE forecasts ADD COLUMN IF NOT EXISTS rain_prob_15mm    DOUBLE PRECISION;
ALTER TABLE forecasts ADD COLUMN IF NOT EXISTS ensemble_size     INTEGER;
ALTER TABLE forecasts ADD COLUMN IF NOT EXISTS nwp_model_version VARCHAR;
```

- GraphCast fallback path populates: `ensemble_size=1`, `p10=p50=p90=point_value`, `rain_prob_*` = 1.0 if point > threshold else 0.0. Backwards-compatible.
- Keep existing `temperature`, `rainfall` columns populated with ensemble **mean** (not p50) — this matches what legacy consumers expect and preserves the Vercel frontend contract during rollout.

New optional table (for LMB and debug analysis, full ensemble retention):

```sql
CREATE TABLE IF NOT EXISTS forecast_ensembles (
    forecast_id VARCHAR NOT NULL REFERENCES forecasts(id) ON DELETE CASCADE,
    member_idx INTEGER NOT NULL,
    temperature DOUBLE PRECISION,
    rainfall DOUBLE PRECISION,
    humidity DOUBLE PRECISION,
    wind_speed DOUBLE PRECISION,
    PRIMARY KEY (forecast_id, member_idx)
);
CREATE INDEX IF NOT EXISTS idx_forecast_ensembles_id ON forecast_ensembles (forecast_id);
```

Size check: 50 members × 20 stations × 7 days × 4 vars × 16 bytes ≈ 450 KB/run. Annual at 52 weekly runs: ~23 MB. Trivial.

### 6b. Pipeline changes

`src/pipeline.py` `__init__`:

```python
if not config.neuralgcm.enabled:
    self.nwp_client = None
elif is_gencast_available() and config.gencast.enabled:
    self.nwp_client = GenCastClient(ensemble_size=config.gencast.ensemble_size)
    self.nwp_name = "GenCast 0.25°"
elif is_graphcast_available():
    self.nwp_client = GraphCastClient(...)
    self.nwp_name = "GraphCast 0.25°"
else:
    log.warning("Neither GenCast nor GraphCast available — Open-Meteo only")
```

`config.py` additions:

```python
@dataclass
class GenCastConfig:
    enabled: bool = True
    ensemble_size: int = 50
    probability_thresholds_mm: tuple[float, ...] = (1.0, 5.0, 15.0)
```

### 6c. `run_forecast_step` in `src/forecasting.py`

Currently consumes deterministic NWP forecasts and returns 7 daily forecast dicts. Upgrade:

1. Detect ensemble input (keyed by `ensemble_size > 1` in NWP metadata).
2. For each station-day, compute summary stats from the ensemble:
   - `temp_p10/p50/p90` from member quantiles
   - `rain_p10/p50/p90` same
   - `rain_prob_1mm/5mm/15mm` as fraction of members exceeding each threshold
   - `temperature` = ensemble mean (legacy compat)
   - `rainfall` = ensemble mean (legacy compat)
   - `confidence` = `1 - (temp_p90 - temp_p10) / 10` clamped to [0.3, 0.9]  — honest, ensemble-derived
3. Write parent row to `forecasts` and 50 child rows to `forecast_ensembles`.

Pseudo-code:

```python
def _summarize_ensemble(members: list[float]) -> dict:
    arr = np.asarray(members)
    return {
        "p10": float(np.quantile(arr, 0.10)),
        "p50": float(np.quantile(arr, 0.50)),
        "p90": float(np.quantile(arr, 0.90)),
        "mean": float(arr.mean()),
    }

def _rain_exceedance(members: list[float], thresholds: tuple[float, ...]) -> dict:
    arr = np.asarray(members)
    return {f"rain_prob_{int(t)}mm": float((arr > t).mean()) for t in thresholds}
```

### 6d. `classify_condition` upgrade

Current deterministic rules at `src/forecasting.py:22-43` become probability-aware:

```python
def classify_condition(forecast: Dict[str, Any]) -> str:
    # Prefer probabilistic inputs when available; fall back to point values.
    p15 = forecast.get("rain_prob_15mm")
    p5  = forecast.get("rain_prob_5mm")
    if p15 is not None and p15 > 0.5:
        return "heavy_rain"
    if p5 is not None and p5 > 0.5:
        return "moderate_rain"
    # Deterministic fallback path unchanged:
    rain = forecast.get("rainfall", 0.0) or 0.0
    if rain > 15.0: return "heavy_rain"
    if rain > 5.0:  return "moderate_rain"
    ...
```

Possible new conditions worth adding (advisory-visible):
- `uncertain_rain` when `rain_prob_5mm` is in `[0.3, 0.5]` — the "hedge" case that a farmer most wants to know about.
- `very_likely_dry` when `rain_prob_1mm < 0.1` — harder forecast than raw `rain < 1`.

These are additions to the condition taxonomy; they need to be added to `CONDITION_COLOR` / `CONDITION_EMOJI` in the dashboard CSS and the advisory matrix.

---

## 7. Phase 3 — Advisory + frontend (Week 3)

### 7a. Claude advisory prompt

`src/translation/rag_provider.py` constructs the advisory input from the forecast. Today it passes point values: `"28°C, 5mm rain tomorrow"`. Upgrade to:

```
Day 0 (2026-04-22): high 32°C, low 25°C, 70% chance of moderate rain (>5mm), 20% chance of heavy rain (>15mm).
Day 1 (2026-04-23): high 33°C, low 26°C, 30% chance of any rain, mostly dry.
```

This is not just cosmetic — Claude's advisory reasoning gets materially better when it can say "plan for rain tomorrow, not for the rest of the week" vs "it might rain."

Template helper in `src/translation/prompt_helpers.py`:

```python
def describe_probabilistic_day(f: dict) -> str:
    date = f["valid_for_ts"].split("T")[0]
    hi = f.get("temp_p90", f["temperature"])
    lo = f.get("temp_p10", f["temperature"])
    p5 = f.get("rain_prob_5mm")
    p15 = f.get("rain_prob_15mm")
    rain_clause = _rain_clause(p5, p15)
    return f"{date}: high {hi:.0f}°C, low {lo:.0f}°C, {rain_clause}."
```

### 7b. Frontend

`frontend/src/pages/Forecast.tsx`: add a `<ProbabilityChip>` component that renders `rain_prob_5mm` as a colored pill (green = dry, yellow = uncertain, blue = rain-likely). One chip per forecast day.

`frontend/api/forecasts.ts`: expose the new columns in the serverless response. Existing consumers keep the `temperature` / `rainfall` mean fields unchanged.

Optional (polish): temperature range bar (p10–p90) instead of a single number.

Legal/licensing line on `/about` or Forecasts footer: *"Forecasts powered by GenCast (Google DeepMind, CC BY-NC-SA 4.0, non-commercial research use)."*

---

## 8. Phase 4 — LastMileBench comparison (Week 4)

The portfolio headline.

### 8a. What it looks like

1. **Accumulate a week of paired output.** Run the pipeline once with GraphCast (as today) — we already have this data. Run again with GenCast as primary. Both live in `forecasts` with different `nwp_model_version`.
2. **Feed both through the `weather_advisory` benchmark.** The LMB adapter (`lastmile-bench/adapters/weather_advisory/adapter.py`) takes forecasts as inputs, generates advisories, and scores decision regret against observed rainfall per panel DP.
3. **Minor adapter upgrade:** teach the adapter to prefer probabilistic inputs when available. When `rain_prob_5mm` is present in the forecast row, use it directly in the decision function instead of thresholding `rain_p50`. Falls back to point values otherwise.
4. **Compare:** regret delta between the two runs. Writeup: N panels, mean regret for each, bootstrap CI, narrative on which panels moved most.

Expected outcome: GenCast beats GraphCast on rainfall-dominated panels (Kerala in monsoon). Temperature-dominated regret should be similar — honest null result, not a failure.

### 8b. Cost breakdown

The LMB weather_advisory v0_2 panel is **1,768 decision points** spanning roughly 3 months of weekly forecasts × 20 stations × 7 horizons. To benchmark GenCast against it, three costs:

| Cost | Amount | Notes |
|---|---|---|
| **Backfill: GenCast historical runs** | **~$75 one-time** | 1,768 DPs / (20 stations × 7 days) ≈ **12.6 forecast-issuance dates**. Each historical run on 4× A100 ≈ $5–10. Total: **$65–130**, call it $100 budget. Once backfilled, the data is permanent. |
| **Adapter upgrade (engineering)** | **~1–2 days** | Single function change in `adapters/weather_advisory/adapter.py`: teach `_advisory_decide_and_cost` to prefer `rain_prob_5mm` when present, fall back to point `rainfall` otherwise. ~50 lines. Plus tests. |
| **Benchmark execution** | **~$5–20 per run** | Anthropic API for advisory generation on 1,768 DPs. With prompt caching (LMB already uses it), first run hits ~$20, subsequent reruns ~$3–5. Wall clock: **~2–3 hours**. |
| **Ongoing (optional): continuous eval** | **~$5/week** | If you wire a mini-LMB run into the weekly GHA — score each week's forecasts against the prior week's observed — that's ~$5/wk extra Anthropic + compute. Turns LMB from "portfolio artifact" into a live quality dashboard. |

**Total one-time cost to get the GenCast-vs-GraphCast result on the table:**
- Backfill compute: ~$100
- Adapter engineering: 1–2 days
- First benchmark execution: ~$20
- **Cash total: ~$120. Time total: 1 week of engineering + 2–3 hours wait.**

That's cheap. Comparable to running the pipeline a few extra times for debugging.

### 8c. Difficulty — honest ranking

From easiest to hardest:

1. **Benchmark execution itself:** Easy. The LMB harness already works; this just means pointing it at a new `forecasts` slice and hitting "go."
2. **Adapter upgrade for probabilistic inputs:** Moderate. One function, but decision functions are correctness-critical — need good tests to make sure `rain_prob_5mm = 0.7` produces the same or better decision than the old `rain > 5mm` path when only the point forecast is available (back-compat).
3. **Backfilling GenCast forecasts on historical dates:** Moderate. Needs a `scripts/backfill_gencast_panel.py` that replays the pipeline's forecast step for specific dates, with ERA5 init from those dates (ERA5T lag means you'd forecast Feb 1 using T-5 ERA5 init from Jan 27). All the mechanics already exist in the GenCast client; this script just schedules N runs and writes to `forecasts` with a `nwp_model_version='gencast_v1_backfill'` tag so they don't collide with live runs.
4. **Statistical framing of the result:** Moderate-to-hard. LMB already produces point estimates of regret per DP. Turning that into a defensible "GenCast improves regret by X% ± Y%" requires bootstrap CI + an acknowledgment that adjacent DPs aren't independent (same weather system spans multiple stations). Standard climate-science caveats; not blocking but needs careful writeup.
5. **Negative-result handling:** Potentially hardest. If GenCast *doesn't* improve regret — or improves it only on a subset — you publish that honestly. LMB is built to surface exactly that kind of finding. The intellectual cost is accepting a null result as a valid portfolio artifact.

### 8d. Why this is strategically valuable

The ~$120 buys you a portfolio artifact that no one else has: a published decision-regret comparison of SOTA-deterministic vs SOTA-probabilistic weather models on a real farmer-decision benchmark. That's your thesis in one sentence, with numbers. Every other "we use GenCast" writeup on the internet is either a DeepMind blog post or a Kaggle CRPS number. A counterfactual-regret number on Indian station decisions is genuinely novel.

### 8e. Integration into the continuous pipeline (optional, week 5+)

Once the one-time comparison lands, a small follow-on: wire LMB `weather_advisory` scoring into the weekly GHA, scoring this week's delivered advisories against next week's observed rainfall. Produces an ongoing "regret-per-run" time series. Cost: ~$5/week extra. Dashboard surface: new card on the System tab. This is the ultimate "working-in-production LMB" demo.

---

## 9. File-level diff preview

### New files
- `scripts/gencast_load_test.py` — Phase 0 harness (~80 lines)
- `src/gencast_client.py` — Phase 1 client (~600 lines, modeled on `graphcast_client.py`)
- `src/translation/prompt_helpers.py` — advisory prompt templating for probabilistic inputs (~60 lines)
- `frontend/src/components/ProbabilityChip.tsx` — probability pill component (~40 lines)
- `docs/gencast-integration-plan.md` — this file
- `lastmile-bench/docs/gencast-vs-graphcast.md` — Phase 4 writeup

### Modified files
- `src/database/__init__.py` — add 11 `ALTER TABLE IF NOT EXISTS` + `CREATE TABLE IF NOT EXISTS forecast_ensembles`
- `src/database/forecasts.py` — `insert_forecast` writes new columns; new `insert_forecast_ensemble` for child rows
- `src/pipeline.py` — `__init__` selects GenCast / GraphCast / NeuralGCM / Open-Meteo in that order; `step_forecast` handles ensemble input
- `src/forecasting.py` — `classify_condition` probability-aware; `run_forecast_step` consumes ensemble
- `src/translation/rag_provider.py` — use `prompt_helpers.describe_probabilistic_day`
- `config.py` — add `GenCastConfig` dataclass, wire to `PipelineConfig`
- `frontend/src/pages/Forecast.tsx` — render `<ProbabilityChip>` per day
- `frontend/api/forecasts.ts` — return new columns
- `frontend/src/lib/api.ts` — extend `Forecast` type with optional `rain_prob_5mm` etc.
- `CLAUDE.md` — update Forecasting Model section, update degradation chain
- `requirements.txt` — no changes (same `graphcast` package covers GenCast)

### Deleted files
None. GraphCast stays as a fallback.

---

## 10. Rollout sequence

| Week | Milestone | Gate to next |
|---|---|---|
| 0 | Load test passes on 4× A100 Space | Peak RAM < 500 GB, single-member < 5 min |
| 1 | `gencast_client.py` produces an ensemble tensor for 20 stations, tested locally on CPU with 1.0° weights | 50-member ensemble for all 20 stations runs end-to-end; station extraction correct |
| 2 | Schema migration run on Neon (dev branch first); pipeline runs GenCast primary, GraphCast fallback; `forecasts` + `forecast_ensembles` populated | One weekly run completes with real 4× A100 cost; fallback path exercised by disabling GenCast flag |
| 3 | Claude advisories show probabilistic language; frontend chip shipped on staging Vercel | Advisory QA on 5 stations (human read-through) |
| 4 | LMB comparison runs; writeup published | Regret delta reported with CI |

## 11. Risks + open questions

- **Load test might reveal the 300 GB RAM estimate was wrong upward.** If real peak is >500 GB, 4× A100 is no longer enough. Mitigation: load test is the gate; if it fails we divert to Path C before writing any client code.
- **12h step changes aggregation.** The `aggregate_to_daily` function currently assumes 6h timesteps. Needs `tz_offset_h`-aware re-bucketing with 12h inputs. Small code change, big correctness risk if wrong. Dedicated test.
- **Claude might produce confusing probabilistic language.** "70% chance" is unfamiliar phrasing for a smallholder farmer. Probably translate to "likely" / "possible" / "unlikely" buckets before handing to Claude. A/B test the output quality.
- **LMB adapter upgrade scope creep.** Teaching the benchmark to consume probabilistic inputs is its own small project. Target: one function update (`_advisory_decide_and_cost` in `adapters/weather_advisory/adapter.py`), not a framework rewrite.
- **Weights license attribution is not a blocker but must be handled.** Add the attribution line on `/about` or the Forecasts page footer *before* going live. Adding it after the fact is embarrassing.
- **Do we keep the XGBoost MOS retrain plan alive?** Open. My leaning: no, archive `docs/mos-retrain-plan.md` with a "superseded by GenCast probabilistic outputs" header. GenCast's ensemble subsumes what rainfall MOS was trying to build.

## 12. Acceptance criteria (full integration)

Before calling Path C' done:

- [ ] Weekly GHA run on 4× A100 Space completes in < 60 minutes with GenCast as primary.
- [ ] `forecasts` table has non-null `rain_prob_5mm` for every row from a GenCast run, and exactly 50 children per row in `forecast_ensembles`.
- [ ] Pipeline falls back to GraphCast cleanly when GenCast is disabled via config; all 20 stations still get a forecast.
- [ ] Frontend renders probability chips on Forecasts page without breaking any existing view.
- [ ] Advisory QA on 5 stations confirms Claude produces sensible probabilistic language (no "70%" literal).
- [ ] LMB `weather_advisory` regret delta reported: GenCast vs GraphCast, with bootstrap CI and a one-paragraph narrative.
- [ ] Licensing attribution visible on the live site.
- [ ] CLAUDE.md updated to reflect GenCast primary.
