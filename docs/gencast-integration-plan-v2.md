# GenCast Integration Plan v2 — Hybrid GraphCast + GenCast 1.0°

*Supersedes `docs/gencast-integration-plan.md` (v1). v1 assumed pure 0.25° GenCast was reachable; Phase 0 empirical testing proved it does not fit on A100 80GB. This v2 adopts the hybrid HRES+ENS pattern that operational weather centers use.*

## 1. Architecture

```
      ┌─────────────────────────┐       ┌──────────────────────┐
ERA5 ─┤ GraphCast 0.25° (det.)  ├──┬──→ │  forecasts table     │
      │  Temp, wind, humidity,  │  │    │  (scalar columns)    │
      │  deterministic rainfall │  │    └──────────────────────┘
      └─────────────────────────┘  │
                                   │    ┌──────────────────────┐
      ┌─────────────────────────┐  ├──→ │ rain_p10/50/90       │
ERA5 ─┤ GenCast 1.0° (prob.)    ├──┘    │ rain_prob_5mm/15mm   │
 @1.0°│  20-member ensemble     │       │ forecast_ensembles   │
      └─────────────────────────┘       └──────────────────────┘
```

- **GraphCast 0.25°** — deterministic point forecast for temperature, wind, humidity, and a baseline rainfall estimate
- **GenCast 1.0°** — 20-member ensemble for rainfall probability at each 12h step
- Both run in the **same weekly pipeline**, on the **same Space** (4× A100 Large, $10/hr), sequentially

## 2. Scientific justification (the preprint pitch)

> Following operational practice at ECMWF (HRES + ENS), NOAA (GFS + GEFS), Met Office (UKV + MOGREPS), and DWD, we deploy a hybrid deterministic + probabilistic architecture. GraphCast 0.25° provides point forecasts optimized for RMSE; GenCast 1.0° provides an ensemble optimized for CRPS. This decoupling reflects divergent objective functions — point accuracy vs. ensemble calibration — and matches how real operational centers actually deploy AI-NWP.
>
> For farmer-decision rainfall thresholds — P(rain > 5mm) at 24–48h horizons — ensemble calibration dominates marginal spatial resolution (cf. Leutbecher 2019 on member-count requirements for tail probabilities). We evaluate this trade-off empirically on LastMileBench's `weather_advisory` panel.

Key references for the preprint:
- Bauer, Thorpe & Brunet 2015 *Nature* — "The quiet revolution of numerical weather prediction" (canonical HRES/ENS history)
- Leutbecher 2019 — "Ensemble size: How suitable is it for NWP forecasts?" (member-count requirements for tail probabilities)
- Palmer 2019 — "Stochastic weather and climate models" (probabilistic modeling at coarser resolutions)

## 3. Phase 0 findings (completed 2026-04-21)

Results empirically confirm the hybrid path:

| Config | Tier | Result |
|---|---|---|
| 0.25° Operational, `mask_type=full` | 4× A100 | OOM at 41 GB mesh2grid buffer |
| 0.25° Operational, `mask_type=lazy` | 4× A100 | OOM (lazy saved <1 GB) |
| **1.0° Mini (coarsened ERA5)** | **4× A100** | **✅ 70s rollout, gate PASS** |
| **1.0° Full (coarsened ERA5)** | **4× A100** | **✅ 149s rollout, gate PASS** |
| 1.0° on 1× A100 Large | 1× A100 Large | Container OOM-killed during JIT compile (host RAM < 568 GB) |

**Architectural lessons worth capturing:**

1. **mesh2grid decoder buffer scales with grid size, not mesh size.** Feeding 0.25°-resolution ERA5 (721×1440) into a 1.0° model reproduces the 17.8 GB OOM buffer identically. Always coarsen ERA5 to the model's native resolution before inference.
2. **DeepMind's multi-GPU pattern is ensemble-parallel pmap** via `xarray_jax.pmap(fn, dim="sample")`, **not** tensor-parallel pjit sharding. Each GPU holds a full model copy and runs one ensemble member.
3. **JAX 0.4.27 + xarray ≥2024.10 need compat shims** for graphcast's pinned API usage: `jax.P`, `jax.NamedSharding` aliases, and `xarray.Dataset.__init__` monkey-patch to handle `Dataset(dataset)` idiom.
4. **`NaNCleaner` expects `fill_value` as a dict**, not scalar: `{"sea_surface_temperature": 0.0}`.
5. **Latitude must be sorted monotonic ascending** before passing to the sampler; ERA5 stores descending.
6. **target_lead_times must be the full slice**, not single step — the rollout generator (`chunked_prediction_generator_multiple_runs`) slices one step at a time internally via `num_steps_per_chunk=1`.
7. **JIT compile needs ~568 GB host RAM** → requires the 4× A100 tier, not single A100 Large (which has ~142 GB host RAM and oom-kills the container during compile).

Detailed traces and Phase 0 debug history preserved in git at commits `85413a4` → `5bae612` of `scripts/gencast_load_test.py` on `hf-gencast-test`.

## 4. Phase roadmap

### Phase 1 — `src/gencast_client.py` (1 week)

Port the Phase 0 load-test pattern into a reusable client.

**Public API:**
```python
class GenCastClient:
    def __init__(self, ensemble_size: int = 20): ...
    async def forecast(self, stations, target_date=None) -> tuple[dict, GenCastResult]:
        """Returns {station_id: {rain_p10, rain_p50, rain_p90, rain_prob_5mm, rain_prob_15mm}}
        plus metadata. Internally runs 5 pmap batches of 4 members each on 4× A100."""
```

**Key logic** (~400 lines, modeled on `graphcast_client.py`):
- ERA5 fetch + coarsen to 1.0° (port from load test)
- Ensemble loop: `jax.random.split(key, 20)` → 5 batches of 4 via `rollout.chunked_prediction_generator_multiple_runs`
- Aggregate per-station: ensemble → quantiles (p10/p50/p90) + threshold exceedance probabilities (P(rain>1mm), P(rain>5mm), P(rain>15mm))
- Bilinear downscale 1.0° rainfall probability to each IMD station lat/lon
- Checkpoint selection: default `1p0deg <2019` (Full), fallback `1p0deg Mini`
- `is_gencast_available()` helper (mirrors `is_graphcast_available()`)

**Compat shims** (inline in client, lifted from Phase 0):
- `jax.P`, `jax.NamedSharding` aliases for JAX 0.4.27
- `xarray.Dataset.__init__` monkey-patch for graphcast/rollout.py

### Phase 2 — Pipeline integration + schema (1 week)

**Schema** (Neon, all nullable, idempotent):
```sql
ALTER TABLE forecasts ADD COLUMN IF NOT EXISTS rain_p10          DOUBLE PRECISION;
ALTER TABLE forecasts ADD COLUMN IF NOT EXISTS rain_p50          DOUBLE PRECISION;
ALTER TABLE forecasts ADD COLUMN IF NOT EXISTS rain_p90          DOUBLE PRECISION;
ALTER TABLE forecasts ADD COLUMN IF NOT EXISTS rain_prob_1mm     DOUBLE PRECISION;
ALTER TABLE forecasts ADD COLUMN IF NOT EXISTS rain_prob_5mm     DOUBLE PRECISION;
ALTER TABLE forecasts ADD COLUMN IF NOT EXISTS rain_prob_15mm    DOUBLE PRECISION;
ALTER TABLE forecasts ADD COLUMN IF NOT EXISTS ensemble_size     INTEGER;
ALTER TABLE forecasts ADD COLUMN IF NOT EXISTS nwp_model_version VARCHAR;

CREATE TABLE IF NOT EXISTS forecast_ensembles (
    forecast_id VARCHAR NOT NULL REFERENCES forecasts(id) ON DELETE CASCADE,
    member_idx INTEGER NOT NULL,
    rainfall DOUBLE PRECISION,
    PRIMARY KEY (forecast_id, member_idx)
);
```

**Pipeline changes** (`src/pipeline.py`):
1. `step_forecast` runs GraphCast first (existing, unchanged) → writes all scalar columns
2. `step_forecast` then runs GenCast 1.0° → updates `rain_p*`, `rain_prob_*`, `ensemble_size`, writes ensemble children
3. `classify_condition` in `src/forecasting.py` upgraded to prefer `rain_prob_5mm > 0.5` over deterministic threshold on point `rainfall`

**Config** (`config.py`):
```python
@dataclass
class GenCastConfig:
    enabled: bool = True
    ensemble_size: int = 20
    checkpoint_match: str = "1p0deg <2019"  # Full; fallback "1p0deg Mini"
    probability_thresholds_mm: tuple = (1.0, 5.0, 15.0)
```

### Phase 3 — Advisory + frontend (1 week)

**Claude prompt upgrade** (`src/translation/rag_provider.py`):
- New helper `describe_probabilistic_day(forecast)` turns `rain_prob_5mm=0.7` into natural language: "likely moderate rain tomorrow" / "possible rain Thursday" / "mostly dry Friday"
- Translate to three probability buckets: `>0.6 = likely`, `0.3–0.6 = possible`, `<0.3 = unlikely`
- Never surface literal "70%" to farmers

**Frontend** (`frontend/src/pages/Forecast.tsx`):
- New `<ProbabilityChip>` component: colored pill per forecast day (green = dry, yellow = uncertain, blue = rain-likely)
- `frontend/api/forecasts.ts` exposes new columns in the serverless response (existing consumers keep the scalar `rainfall` field unchanged)
- `frontend/src/lib/api.ts` extends `Forecast` type with optional `rain_prob_5mm`, etc.
- `/about` page adds attribution: *"Powered by GraphCast + GenCast (Google DeepMind, CC BY-NC-SA 4.0, non-commercial research use)"*

### Phase 4 — LMB benchmark (1 week — portfolio headline)

**Sub-panel pre-registration** (before any scoring — methodological requirement):
- Commit `lastmile-bench/panels/weather_advisory/v0_2_sampled_subpanel.json`
- Stratified 5-date sub-panel (1 per season) on 20 stations × 7 horizons = ~700 DPs
- Hash-pinned

**Adapter upgrade** (`lastmile-bench/adapters/weather_advisory/adapter.py`):
- `_advisory_decide_and_cost` prefers `rain_prob_5mm` when present; falls back to point `rainfall > 5`
- Unit tests for back-compat (both inputs produce equivalent decisions when probability is 0.0 or 1.0)

**Backfill** (~$10, 3 hours):
- Run GenCast 1.0° on the 5 pre-registered dates, tag `nwp_model_version='gencast_1p0_v1'`
- GraphCast side already backfilled from production history

**Benchmark run** (~$0 — LMB scoring is rule-based, no Anthropic cost):
- Score both GraphCast-only and GraphCast+GenCast on the sub-panel
- Regret delta + bootstrap CI + narrative

**Preprint artifact:** `lastmile-bench/docs/hybrid-vs-deterministic.md` — one-page writeup with numbers, not a thesis chapter.

### Phase 5 — Production rollout (1 week)

1. **Hardware upgrade**: production Space `jtlevine/ai-weather-pipeline-runner` from A100 Large (1×, $4/hr) → **4× A100 Large** ($10/hr). Settings → Hardware → confirm.
2. Merge Phases 1–3 from the gencast-test Space into main repo, push to `hf-runner` + `github`.
3. Schema migration on Neon (idempotent `ALTER TABLE IF NOT EXISTS` — safe to run).
4. First weekly run on production Space. Monitor.
5. If >3 consecutive weekly runs succeed with valid rain probabilities → mark Phase 0 complete, update `CLAUDE.md` degradation chain.

## 5. Cost + time totals

| Item | Cost |
|---|---|
| Phase 1-3 engineering | 3 weeks, $0 compute (dev is local + paused Space) |
| Phase 4 backfill + benchmark | ~$10 one-time |
| Phase 5 production rollout | ~$3 for first weekly run |
| **One-time total** | **~$15 + 5 weeks engineering** |
| Monthly ongoing production | **~$14** (4× A100 weekly × ~20 min) |
| Delta vs. current ($4/mo GraphCast-only) | **+$10/mo** |

Load test on Phase 0 empirically measured:
- GenCast 1.0° Mini: 70s per 4-member × 14-step rollout → **~6 min** for 20-member ensemble
- GenCast 1.0° Full: 149s per 4-member × 14-step rollout → **~12 min** for 20-member ensemble

## 6. Risks + mitigations

| Risk | Mitigation |
|---|---|
| 4× A100 tier gets deprecated or priced out | Fallback: single A100 Large runs GraphCast-only (existing path stays functional); GenCast columns stay NULL |
| 1.0° rain misses Kerala orographic events | GraphCast 0.25° deterministic `rainfall` provides *intensity* signal; GenCast 1.0° provides *probability* signal. Adapter blends both. |
| Claude advisory language sounds stilted with probability buckets | QA on 5 stations before production; A/B the bucket thresholds |
| GenCast fails mid-run (GCS outage, JAX issue) | Pipeline degrades to GraphCast-only; `rain_prob_*` stays NULL; advisory falls back to deterministic |
| License attribution missed | Attribution line blocks the `/about` PR merge — make it a checklist item |
| JAX / graphcast version drift breaks compat shims | Pin `jax==0.4.27`, `xarray>=2024.10,<2025`, `graphcast` at current commit; update shims if versions change |

## 7. Decision gates

- **After Phase 2**: First live weekly run with both models. If GenCast times out (>20 min) → drop ensemble to 10 members.
- **After Phase 4**: If hybrid regret delta vs GraphCast-only is <2% on sub-panel → publish honest null result, keep hybrid in production for the probability chip (UX value independent of regret).
- **After Phase 5**: 3 consecutive successful production runs = gate closed.

## 8. Artifacts produced

**New files:**
- `src/gencast_client.py` — main GenCast client (~400 lines)
- `src/translation/prompt_helpers.py` — probabilistic language helper (~60 lines)
- `frontend/src/components/ProbabilityChip.tsx` — probability pill component (~40 lines)
- `lastmile-bench/panels/weather_advisory/v0_2_sampled_subpanel.json` — pre-registered sub-panel
- `lastmile-bench/docs/hybrid-vs-deterministic.md` — preprint artifact
- `docs/phase0-findings.md` — archive of Phase 0 debug history

**Modified files:**
- `src/database/__init__.py` — schema additions
- `src/database/forecasts.py` — `insert_forecast` writes new columns; new `insert_forecast_ensemble`
- `src/pipeline.py` — `step_forecast` runs GraphCast + GenCast
- `src/forecasting.py` — `classify_condition` probability-aware
- `src/translation/rag_provider.py` — uses `describe_probabilistic_day`
- `config.py` — adds `GenCastConfig`
- `frontend/src/pages/Forecast.tsx`, `frontend/api/forecasts.ts`, `frontend/src/lib/api.ts`
- `CLAUDE.md` — forecasting section reflects hybrid
- `requirements.txt` — unchanged (same `graphcast` package covers GenCast)

**Deleted files:** none. GraphCast stays in the pipeline.

**Deprecated files:**
- `docs/gencast-integration-plan.md` — keep as historical, this doc supersedes
- `scripts/gencast_load_test.py` + `scripts/gencast_load_batch.py` — keep as Phase 0 archive; not called by production
- `src/api.py` `/api/gencast/*` test endpoints — remove from production `src/api.py` before merging to main Space (test-Space only)

## 9. Rollout sequence

| Week | Milestone | Gate to next |
|---|---|---|
| 1 | `gencast_client.py` produces a 20-member rainfall ensemble for 20 stations on the test Space | CPU smoke test OK; 20-station output shape correct |
| 2 | Schema migration on Neon dev branch; pipeline runs GraphCast + GenCast; both populated in `forecasts` and `forecast_ensembles` | One weekly run completes in <20 min on 4× A100 |
| 3 | Claude advisories show probabilistic language; frontend chip shipped on staging Vercel | Advisory QA on 5 stations |
| 4 | LMB comparison published | Regret delta with CI |
| 5 | Production Space hardware upgraded; weekly GHA run succeeds | 3 consecutive green weekly runs |
