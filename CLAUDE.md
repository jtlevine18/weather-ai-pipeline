# Weather AI 2 — Kerala & Tamil Nadu Farming Pipeline

## Project Vision
Self-healing, AI-powered weather forecasting for smallholder farmers in Kerala and Tamil Nadu. The pipeline ingests real station data from IMD (India Meteorological Department) with imdlib gridded backup, heals anomalies, generates MOS-corrected forecasts, downscales to farmer GPS coordinates, produces bilingual (Tamil/Malayalam) agricultural advisories via RAG + Claude, and delivers via SMS.

---

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Add API keys + database URL
cp .env.example .env      # then fill in keys + DATABASE_URL

# Run the full pipeline with real IMD data (all configured stations)
python run_pipeline.py

# Run with NeuralGCM forecasting (requires GPU + neuralgcm package)
python run_pipeline.py --neuralgcm

# Run with synthetic data (old behavior)
python run_pipeline.py --source synthetic

# Launch the Streamlit dashboard
streamlit run streamlit_app/app.py

# NL agent CLI
python run_chat.py

# Station health monitor
python run_monitor.py

# Unified FastAPI (health, auth, pipeline tracker, webhook) — local dev only
python run_api.py                # FastAPI on port 8000

# Dagster orchestration UI
dagster dev -m dagster_pipeline
```

---

## Architecture

Each API has exactly ONE job — no source is shared between stages:

```
IMD Scraper + imdlib → Step 1 Ingest     (real station obs, fallback: synthetic)
Tomorrow.io          → Step 2 Heal        (cross-validation reference)
GraphCast / NeuralGCM / Open-Meteo → Step 3 Forecast (GraphCast 0.25° on A100, fallback: NeuralGCM 2.8° or Open-Meteo API)
NASA POWER           → Step 4 Downscale   (0.5° spatial grid → farmer GPS)
Claude API           → Step 5 Translate   (RAG advisory + Tamil/Malayalam)
```

### Pipeline (6 steps, linear)

| Step | Output table | What it does |
|---|---|---|
| 1 Ingest | `raw_telemetry` | Real IMD station data (scraper → imdlib → synthetic fallback) |
| 2 Heal | `clean_telemetry` + `healing_log` | Claude Sonnet agentic healer (5 tools: station metadata, historical normals, Tomorrow.io reference, neighboring stations, seasonal context) with rule-based fallback |
| 3 Forecast | `forecasts` | GraphCast 0.25° on A100 (ERA5 init, single batch for all stations) → XGBoost MOS correction; fallback: NeuralGCM 2.8° or Open-Meteo API |
| 4 Downscale | `forecasts` (updated) | NASA POWER IDW interpolation + lapse-rate elevation correction |
| 5 Translate | `agricultural_alerts` | Hybrid RAG (FAISS+BM25) + Claude advisory + translation |
| 6 Deliver | `delivery_log` | Console SMS (Twilio dry-run) |

### Parallelization
- Step 2 Heal: Tomorrow.io fetched in batches of 10 with 0.2s sleep
- Step 3 Forecast: GraphCast (or NeuralGCM fallback) runs once globally (all configured stations from one inference); Open-Meteo fallback fetched in a single batch
- Step 4 Downscale: all configured stations downscaled in parallel via `asyncio.gather()`
- Step 5 Translate: all advisories generated in parallel via `asyncio.gather()`

### Quality score design
Quality score measures **accuracy of compared fields only** (how well IMD temp/rainfall match Tomorrow.io reference). NULL-filling from Tomorrow.io is expected enrichment (IMD never provides wind/pressure/humidity) and does NOT penalize quality. `cross_validated` and `null_filled` coexist as independent heal actions. `fields_filled` count tracked per reading.

### Degradation chain (independent, never cascades)
- Claude healing agent unavailable → rule-based fallback (identical output, no reasoning logged)
- IMD scraper down → imdlib gridded (T-1 day) → synthetic fallback
- GraphCast unavailable (no A100/package) → NeuralGCM 2.8° fallback (fits L4 48GB)
- NeuralGCM also unavailable → Open-Meteo API fallback
- NWP unavailable (all three) → persistence model (last obs + diurnal adjustment)
- XGBoost not trained → raw NWP passthrough
- Claude down → rule-based template advisories
- Tomorrow.io down → cross-validate against NASA POWER; if both down, assign quality by data completeness
- NASA POWER down (heal) → quality score reflects missing cross-validation
- NASA POWER down (downscale) → use station-level forecast
- Translation fails → return English advisory

---

## Project Structure

```
weather AI 2/
├── CLAUDE.md                  # This file
├── config.py                  # All station configs + pipeline dataclasses (database_url, DPIConfig)
├── run_pipeline.py            # Main entry point
├── run_api.py                 # FastAPI server entry point (uvicorn on port 8000)
├── run_chat.py                # NL agent CLI
├── run_monitor.py             # Station health monitor
├── trace_pipeline.py          # Step-by-step pipeline demo
├── docker-compose.yml         # Single app service
├── requirements.txt
├── pyproject.toml
├── dvc.yaml                   # DVC pipeline: export_training_data → train_mos
├── .env                       # API keys (never commit)
├── .streamlit/
│   ├── config.toml            # Theme + server config
│   └── secrets.toml           # API keys for Streamlit Cloud (never commit)
├── src/
│   ├── pipeline.py            # WeatherPipeline orchestrator (6-step, parallelized async)
│   ├── database/              # PostgreSQL (Neon) — 17 tables, PgConnection wrapper
│   │   ├── __init__.py        # DDL (17 tables), init_db(), re-exports all public names
│   │   ├── telemetry.py       # raw/clean telemetry CRUD + paired join
│   │   ├── forecasts.py       # forecast CRUD + actuals join
│   │   ├── alerts.py          # agricultural_alerts CRUD
│   │   ├── delivery.py        # delivery_log + delivery_metrics CRUD
│   │   ├── pipeline_runs.py   # start/finish pipeline run
│   │   ├── conversation.py    # conversation_log CRUD
│   │   ├── health.py          # station health aggregation query
│   │   └── healing.py         # healing_log CRUD (AI agent assessment persistence)
│   ├── models.py              # Pydantic v2 data contracts (stage boundary validation)
│   ├── healing.py             # HealingAgent (Claude Sonnet tool-use agentic healer, 5 tools, 24-entry seasonal context) + RuleBasedFallback (quality score = accuracy of compared fields only, no fill penalty)
│   ├── ingestion.py           # IMD scraper + imdlib gridded + synthetic fallback
│   ├── weather_clients.py     # Tomorrow.io, Open-Meteo, NASA POWER, IMD JSON API + imdlib clients
│   ├── graphcast_client.py    # GraphCast 0.25° forecaster (JAX/A100, ERA5 init, station extraction)
│   ├── neuralgcm_client.py   # NeuralGCM 2.8° forecaster (JAX/GPU, ERA5 init, fallback)
│   ├── forecasting.py         # HybridNWPModel: NWP + XGBoost MOS + persistence fallback
│   ├── downscaling/           # IDW spatial interpolation + lapse-rate
│   │   ├── __init__.py        # IDWDownscaler
│   │   ├── interpolation.py   # haversine, IDW, lapse-rate math
│   │   └── grid_fetcher.py    # NASA POWER grid retrieval
│   ├── translation/           # RAG + Claude advisory provider
│   │   ├── __init__.py        # Provider factory + async dispatch
│   │   ├── rag_provider.py    # FAISS+BM25 hybrid search → Claude
│   │   ├── local_provider.py  # Rule-based fallback (no API)
│   │   ├── claude_provider.py # Claude-only provider
│   │   ├── curated_advisories.py  # Crop-specific advisory templates
│   │   ├── rag_index_builder.py   # Build FAISS + BM25 index
│   │   └── farmer_template.py # Per-farmer advisory template expansion from DPI profiles
│   ├── delivery/              # Console + Twilio SMS/WhatsApp
│   │   ├── __init__.py        # MultiChannelDelivery
│   │   ├── console_provider.py
│   │   ├── twilio_provider.py
│   │   └── whatsapp_provider.py
│   ├── nl_agent/              # NLAgent: Claude tool-use orchestration (5 tools)
│   │   └── __init__.py
│   ├── conversation/          # ConversationalAgent: farmer-aware, stateful chat
│   │   ├── __init__.py        # ConversationalAgent class
│   │   ├── state_machine.py   # Conversation state transitions
│   │   ├── language.py        # Language detection
│   │   ├── prompts.py         # System prompt builder
│   │   ├── tools.py           # 6 conversation tools (profile, soil, insurance, etc.)
│   │   ├── memory.py          # Per-farmer memory extraction + retrieval
│   │   └── followup.py        # Proactive follow-up scheduling
│   ├── dpi/                   # Digital Public Infrastructure agent
│   │   ├── __init__.py        # DPIAgent: profile assembly from 6 services
│   │   ├── models.py          # Dataclasses: AadhaarProfile, LandRecord, SoilHealthCard, etc.
│   │   ├── simulator.py       # SimulatedDPIRegistry: 40+ farmers across all configured stations
│   │   └── services.py        # DPIService protocol + SimulatedDPIService + factory
│   ├── daily_scheduler.py     # Singleton daily scheduler (APScheduler, toggle via System tab, auto-resumes)
│   ├── event_bus.py           # File-based pub/sub event bus
│   ├── quality_checks.py      # Post-pipeline data quality checks (row count, nulls, ranges, freshness)
│   ├── api.py                 # Unified FastAPI REST API (GET /health, POST /auth/*, GET /api/stations, GET /api/forecasts, GET /api/alerts, GET /api/station/{id}/latest, GET /api/pipeline/runs, POST /webhook, GET /webhook/history)
│   ├── auth.py                # JWT auth with operator/viewer roles, passlib bcrypt
│   ├── scheduler.py           # APScheduler-based pipeline scheduling
│   ├── monitor.py             # Station health monitor
│   └── architecture.py        # Dynamic Mermaid diagram + get_pipeline_stages() (3 stages: Data/Forecasts/Advisories)
├── dagster_pipeline/          # Dagster orchestration (alternative to run_pipeline.py)
│   ├── __init__.py            # Dagster definitions
│   ├── resources.py           # Dagster resources (API clients, PostgresResource)
│   ├── io_manager.py          # PostgreSQL I/O manager
│   ├── schedules.py           # Dagster schedules
│   ├── sensors.py             # Dagster sensors
│   ├── hooks.py               # Dagster hooks
│   ├── checks.py              # Dagster asset checks
│   └── assets/                # One asset per pipeline step
│       ├── __init__.py
│       ├── ingest.py
│       ├── heal.py
│       ├── forecast.py
│       ├── downscale.py
│       ├── deliver.py
│       └── translate.py
├── scripts/
│   ├── batch_pipeline.py      # Multi-run batch execution
│   ├── export_training_data.py # DVC stage: DuckDB → Parquet
│   └── train_mos.py           # DVC stage: Parquet → XGBoost model + metrics
├── streamlit_app/
│   ├── app.py                 # Homepage: 3 clickable stage cards, intro text, how-it-works, run history
│   ├── data_helpers.py        # Shared DB queries (@st.cache_data) + Streamlit secrets injection
│   ├── style.py               # Shared CSS (Source Serif 4 + DM Sans, cream/gold theme, STATUS_COLOR)
│   ├── chat_widget.py         # Floating chat toggle (sidebar panel on every page, farmer ID, agent dispatch)
│   └── pages/
│       ├── 1_Data.py          # Ingest+Heal: station map, data sources, healing before/after, station health
│       ├── 2_Forecasts.py     # Forecast+Downscale: station forecasts, model perf, downscaling demo
│       ├── 3_Advisories.py    # Translate+Deliver: advisory feed, lineage, farmers/DPI profiles, delivery log
│       └── _System.py         # System (hidden from sidebar): architecture, scheduler, runs, delivery, cost, evals
├── tests/
│   ├── conftest.py            # Shared fixtures (sample_station, fault_config, etc.)
│   ├── test_pipeline_stages.py  # Unit tests: ingestion, healing, forecasting, downscaling, advisory
│   ├── test_database.py       # Database CRUD tests
│   ├── test_dpi.py            # DPI agent + services tests
│   ├── test_conversation.py   # Conversation agent tests
│   ├── test_models.py         # Pydantic model validation tests
│   ├── eval_healing.py        # Level 1A: detection precision/recall, imputation accuracy
│   ├── eval_forecast.py       # Level 1B: MOS correction accuracy
│   ├── eval_advisory.py       # Level 2: advisory quality scoring
│   ├── eval_translation.py    # Level 3: translation quality
│   ├── eval_rag.py            # RAG retrieval quality
│   ├── eval_dpi.py            # DPI agent integration eval
│   └── eval_conversation.py   # Conversation agent integration eval
└── models/                    # Trained XGBoost + FAISS index (auto-built)
```

---

## Stations (20 total — all with verified IMD SYNOP station IDs)

**Kerala (10):** Thiruvananthapuram (43371), Kochi (43353), Alappuzha (43352), Kannur (43315), Kozhikode (43314), Thrissur (43357), Kottayam (43355), Palakkad (43335), Punalur (43354), Nilambur (43316)
**Tamil Nadu (10):** Thanjavur (43330), Madurai (43360), Tiruchirappalli (43344), Salem (43325), Erode (43338), Chennai (43279), Tirunelveli (43376), Coimbatore (43321), Vellore (43303), Nagappattinam (43347)

Languages: Malayalam (`ml`) for Kerala, Tamil (`ta`) for Tamil Nadu.
Crop contexts: verified per-district from state agriculture department data.

---

## Database (PostgreSQL / Neon — 17 tables)

| Table | Domain | Purpose |
|---|---|---|
| `raw_telemetry` | telemetry | Real IMD station readings (or synthetic with injected faults) |
| `clean_telemetry` | telemetry | AI-healed or rule-based cross-validated readings with quality scores |
| `healing_log` | telemetry | Per-reading AI agent assessments: reasoning, corrections, tools used, tokens, latency |
| `forecasts` | forecasts | MOS-corrected forecasts (station + farmer-level) |
| `agricultural_alerts` | alerts | Bilingual advisories (advisory_en + advisory_local) |
| `delivery_log` | delivery | SMS delivery records |
| `delivery_metrics` | delivery | Per-station delivery aggregates per run |
| `pipeline_runs` | pipeline | Run history with step-level status |
| `conversation_log` | conversation | NL agent + conversation agent chat logs |
| `conversation_sessions` | conversation | Stateful session tracking |
| `conversation_memory` | conversation | Per-farmer extracted memories |
| `scheduled_followups` | conversation | Proactive follow-up messages |
| `feedback_responses` | delivery | Farmer feedback on advisories |
| `farmer_profiles` | DPI | Cached composite farmer profiles |
| `farmer_land_records` | DPI | Land records from DPI |
| `farmer_soil_health` | DPI | Soil Health Card data |
| `users` | auth | User accounts for JWT auth (operator/viewer roles) |

---

## Forecasting Model

**Architecture:** MOS (Model Output Statistics) — same approach used by national weather services.

- **NWP primary: GraphCast 0.25°** (Google DeepMind's graph neural network, Science 2023)
  - 0.25° resolution (~28km) — resolves Kerala precipitation (NeuralGCM at 2.8° could not)
  - Initial conditions: ERA5 reanalysis from ARCO Zarr (free, ~5-day lag via ERA5T)
  - Single inference pass produces global forecast → extract all configured stations
  - Requires A100 80GB GPU on HF Spaces
- **NWP fallback 1: NeuralGCM 2.8°** (Google DeepMind's neural GCM, fits L4 48GB)
- **NWP fallback 2: Open-Meteo** (GFS/ECMWF via free API, no GPU needed)
- **XGBoost MOS correction:** trained on residual between NWP and observations
- **12-feature vector:** `nwp_temp`, `nwp_rainfall`, `humidity`, `wind_speed`, `pressure`, `station_altitude`, `soil_moisture`, `rolling_6h_error`, `recent_temp_trend`, `hour_sin`, `hour_cos`, `doy_sin`
- **Soil moisture proxy:** NASA POWER `PRECTOTCORR` (mm/day) / 20, capped at 1.0
- **Rolling error tracking:** per-station 6h error window, updated after each prediction
- **Fallback:** persistence model (last obs + diurnal adjustment)
- **Formula:** `Final = NWP_Forecast + XGBoost_Correction(features)`
- **model_used values:** `graphcast_mos`, `graphcast_only`, `neuralgcm_mos`, `neuralgcm_only`, `hybrid_mos`, `nwp_only`, `persistence`
- **DVC pipeline:** `scripts/export_training_data.py` → `scripts/train_mos.py` → `models/hybrid_mos.json`

---

## Translation (RAG + Claude)

**Default provider:** RAG + Claude. **Fallback:** local rule-based (zero API cost).

**RAG flow:**
1. Build FAISS dense + BM25 sparse index from HuggingFace agricultural datasets
2. Hybrid retrieval (alpha=0.5 blend), score threshold=0.35, top-k=5
3. Generate English advisory via Claude (claude-sonnet-4-6)
4. Separate Claude call to translate to Tamil or Malayalam
5. Both `advisory_en` and `advisory_local` stored in `agricultural_alerts`

**Hover-to-translate:** Advisories page shows local language by default; hovering reveals English overlay (pure CSS, no JS).

---

## DPI (Digital Public Infrastructure) Subsystem

**6 simulated services** (single generic class in `src/dpi/services.py`):
Aadhaar eKYC, Land Records, Soil Health Card, PM-KISAN, PMFBY crop insurance, Kisan Credit Card.

**DPIAgent** (`src/dpi/__init__.py`): phone → identify → parallel fetch all 6 services → composite FarmerProfile → cache to DB.

**40+ simulated farmers** across all configured stations with realistic Kerala/Tamil Nadu data (district-specific crops, soil types, irrigation, names in Malayalam/Tamil).

---

## Conversation Engine

**ConversationalAgent** (`src/conversation/`): wraps NLAgent with:
- State machine: onboarding → active → follow-up
- Farmer identification via DPI (phone → profile)
- Persistent per-farmer memory extraction
- Proactive follow-up scheduling
- Language detection + native language responses
- 11 total tools (5 NLAgent + 6 conversation-specific)

---

## Daily Scheduler

`src/daily_scheduler.py` — singleton APScheduler background thread that runs the full pipeline once daily at 06:00 IST (00:30 UTC).

- Toggle on/off from **System → Scheduler** tab in the dashboard
- State persists in `scheduler_state.json` — auto-resumes after HF Spaces restarts
- Auto-imported by `app.py` on startup (`import src.daily_scheduler`)
- Manual controls in System tab: Run Full Pipeline, Ingest+Heal, Forecast→Deliver, Retrain MOS

---

## Dagster Orchestration

Alternative to `run_pipeline.py` — same 6 steps as Dagster assets with:
- Resources for API clients (Tomorrow.io, NASA POWER, Open-Meteo), PostgresResource
- PostgreSQL I/O manager
- Schedules, sensors, hooks
- Asset checks (data quality validation)
- Launch via `dagster dev -m dagster_pipeline`

---

## Portfolio UI (React + Vercel)

The portfolio-facing dashboard is a React 18 + TypeScript + Vite SPA in `frontend/` served from Vercel. Serverless functions in `frontend/api/*.ts` read from Neon directly so the UI works even when the pipeline Space is asleep.

**Design language:**
- Typography: Source Serif 4 (headings, `.page-title` 28px) + Space Grotesk (body)
- Palette: cream `#fcfaf7`, ink `#1b1e2d`, slate `#606373`, hairline `#e8e5e1`
- Accent: steel blue `#2d5b7d`
- Sidebar brand: **Weather AI**
- No eyebrow labels above `<h1>` page titles; all pages use the shared `.page-title` class
- Output cards have `max-height: 240px` + `overflow: hidden` so live data can't push past page height
- Grid columns use `minmax(0, Nfr)` for truncation

**How It Works page** (`frontend/src/pages/Pipeline.tsx`): h1 only (no caption), 4-category stack (Data / Models / Delivery / Infrastructure), then 3 tabs — **Run history**, **Cost & scale**, **Build your own**.

The `streamlit_app/` section below describes the legacy local-only dev dashboard and is not the portfolio UI.

---

## Dashboard (Streamlit)

Pages map to pipeline stages. Chat is a floating sidebar toggle, System is hidden from the sidebar nav.

| Page | Pipeline Steps | Tabs |
|------|---------------|------|
| **Home** (`app.py`) | Overview | Descriptive title, "What is this?" explainer, 3 clickable stage cards (Data/Forecasts/Advisories), key metrics, run history |
| **Data** (`1_Data.py`) | Ingest + Heal | Map, Sources (IMD/imdlib/synthetic distribution), Healing (before/after + quality), Station Health |
| **Forecasts** (`2_Forecasts.py`) | Forecast + Downscale | Station Forecasts, Model Performance, Downscaling (IDW + lapse-rate demo) |
| **Advisories** (`3_Advisories.py`) | Translate + Deliver | Advisory Feed (hover-to-English), Lineage (forecast→advisory), Farmers & DPI (6 services), Delivery log |
| **System** (`_System.py`) | Operations | Architecture, Scheduler, Pipeline Runs, Delivery Log, Cost, Evals, Agent Log, Delivery Funnel |
| **Chat** (`chat_widget.py`) | All pages | Sidebar toggle → farmer lookup → NLAgent or ConversationalAgent |

Style: Source Serif 4 (headings) + DM Sans (body), cream background (`#faf8f5`), gold accents (`#d4a019`), subtle warm gradient background. CSS in `style.py`, shared constants: `STATUS_COLOR`, `CONDITION_COLOR`, `CONDITION_EMOJI`. Home page cards are `<a>` elements with color-coded top borders (green/blue/gold) linking to `/Data`, `/Forecasts`, `/Advisories`.

---

## Pydantic Data Contracts

`src/models.py` — validates data at stage boundaries:
- `RawReading` (stage 1 output)
- `CleanReading` (stage 2 output)
- `Forecast` / `DownscaledForecast` (stage 3-4 output)
- `Advisory` (stage 5 output)
- `DeliveryLog` (stage 6 output)

---

## Downscaling

NASA POWER 5x5 grid (~0.5 deg radius around station) → IDW interpolation to farmer GPS coordinates → lapse-rate elevation correction (6.5 deg C per 1000m). Re-classifies weather condition at farmer scale.

---

## API Keys

| Key | Used for | Free tier |
|---|---|---|
| `ANTHROPIC_API_KEY` | Claude healing agent + advisory generation + translation | Pay-per-use (~$0.27/run: ~$0.15 healing + ~$0.12 advisory) |
| `TOMORROW_IO_API_KEY` | Anomaly healing cross-validation | 500 calls/day free |

NASA POWER, Open-Meteo, GraphCast/NeuralGCM (model checkpoints on GCS), ERA5 ARCO Zarr, IMD city weather (scraping), and imdlib are fully free, no key needed.

| `DATABASE_URL` | PostgreSQL (Neon) connection | Required (no default) |

Set in `.env` for local development. On Streamlit Cloud, add to App Settings → Secrets.

---

## Deployment (2 services + Neon)

Weather 2 now follows the same pattern as Market Intelligence and Climate Risk Engine: **one HF Space for the pipeline runner, Vercel for the frontend + serverless API functions that read Neon directly.** There is no separate always-on API Space anymore.

### 1. Vercel — React frontend + serverless API (always on)
- **Source:** `frontend/` directory
- **Live URL:** `https://weather-forecast.jeff-levine.com`
- **Git remote:** `github` → `https://github.com/jtlevine18/weather-ai-pipeline.git`
- **Push command:** `git push github main`
- Static React SPA from `frontend/dist/` + 11 Vercel serverless functions in `frontend/api/*.ts` (alerts, conversation, delivery, farmers, forecasts, healing, metrics, pipeline, sources, stations, telemetry)
- Serverless functions read from Neon via `@neondatabase/serverless`. No dependency on any HF Space being awake.
- Auto-deploys on every push to `github main`
- **Env vars (Vercel production):** `DATABASE_URL` (Neon connection string)

### 2. HF Spaces — Pipeline runner (sleeps, wakes weekly)
- **Space:** `jtlevine/ai-weather-pipeline-runner`
- **URL:** `https://jtlevine-ai-weather-pipeline-runner.hf.space`
- **Git remote:** `hf-runner` → `https://huggingface.co/spaces/jtlevine/ai-weather-pipeline-runner` (configured as a second remote on the main repo — the Space's history is unified with `github main`, so pushes go to both from the same working tree).
- **Push command:** `git push hf-runner main` (add `&& git push github main` if both remotes need updating; see the push checklist below).
- The Space's `Dockerfile` runs `uvicorn src.api:app` on port 7860. It serves a pipeline tracker page at `/` with a manual **Run Pipeline** button, a `/health` endpoint, and `/api/pipeline/trigger` + `/api/pipeline/status` that the weekly GitHub Action polls. The pipeline does NOT auto-run on Space wake-up — it's triggered explicitly.
- The Space includes the full main-repo tree (`COPY . .` in the Dockerfile). `frontend/`, `tests/`, `streamlit_app/`, etc. are copied in but unused at runtime — only `src/`, `config.py`, `stations.json`, and `requirements.txt` are read by `src.api:app`. Total tracked size is ~2 MB, so image bloat is negligible.
- Scheduled weekly via GitHub Action; sleeps between runs to save compute
- A100 80GB GPU for GraphCast (falls back to NeuralGCM on L4, then Open-Meteo without GPU)
- **Env vars (Space secrets — set these before pushing):** `DATABASE_URL`, `ANTHROPIC_API_KEY`, `TOMORROW_IO_API_KEY`, `JWT_SECRET_KEY` (required if `ENV=production`), `WEBHOOK_SECRET` (only if webhook receiver is wired in), optional `ALLOWED_ORIGINS`
- **Hardware:** set explicitly in *Settings → Variables and secrets → Hardware* — it does not persist across Space rebuilds automatically
- **Retired:** `jtlevine/ai-weather-pipeline` (without `-runner`) was the original pipeline-runner Space and has been deleted. Do not reference it in code, docs, or git remotes. The stale `origin` and `hf-api` remotes that used to point at retired Spaces have been removed.

### Data flow
```
Pipeline Space (weekly)  → writes to → Neon PostgreSQL
Vercel (always on)       → serverless API reads from → Neon → serves frontend
```

### Push checklist
The main repo now has two remotes: `github` (Vercel source of truth) and `hf-runner` (HF Space). Push destinations by file type:

| What changed | Push to |
|---|---|
| Frontend React code (`frontend/src/`) | `git push github main` |
| Vercel serverless API (`frontend/api/*.ts`) | `git push github main` |
| Pipeline code (`src/pipeline.py`, `src/ingestion.py`, `src/healing.py`, etc.) | `git push github main && git push hf-runner main` |
| `src/api.py` changes (runs on the Space as the status/health page) | `git push github main && git push hf-runner main` |
| `config.py`, `requirements.txt`, `stations.json`, `Dockerfile` | `git push github main && git push hf-runner main` |
| Database schema (`src/database/`) | `git push github main && git push hf-runner main` |
| Docs only (`README.md`, `CLAUDE.md`) | `git push github main` |

### Legacy
- `streamlit_app/` still exists in the repo as a local-only dashboard for dev work. It is **not** deployed to any Space and does not serve the portfolio UI — Vercel + serverless functions do.

---

## Tech Stack

- **Python 3.11+**, **PostgreSQL** (Neon hosted) + **psycopg2-binary**
- **dm-graphcast** + **dm-haiku** (Google DeepMind GraphCast 0.25° on A100)
- **neuralgcm** (Google DeepMind NeuralGCM 2.8° fallback on L4)
- **jax[cuda12]** (GPU backend for both weather models)
- **anthropic** (Claude API — advisory generation + translation)
- **xgboost** + **scikit-learn** (MOS correction model)
- **faiss-cpu** + **sentence-transformers** + **rank-bm25** (RAG retrieval)
- **langchain-huggingface** + **datasets** (index building)
- **pydantic** v2 (data contracts at stage boundaries)
- **httpx** (async HTTP for weather APIs)
- **gcsfs** + **xarray** + **zarr** (ERA5 data access for GraphCast/NeuralGCM)
- **google-cloud-storage** (GraphCast checkpoint + normalization stats download)
- **beautifulsoup4** + **imdlib** (IMD data scraping + gridded backup)
- **streamlit** + **pydeck** (dashboard)
- **dagster** (orchestration — alternative to linear pipeline)
- **fastapi** + **uvicorn** (unified REST API: health, auth, stations, forecasts, alerts, webhook)
- **python-jose** + **passlib** (JWT auth + bcrypt password hashing)
- **apscheduler** (scheduled pipeline runs)
- **rich** (terminal output)
- **DVC** (ML model versioning pipeline)

---

## Adapting for a New Region

This pipeline is designed to be forked and adapted. See [REBUILD.md](REBUILD.md) for the full guide and Claude Code prompt.

### Geography-coupled files (must change for a new region)

| File | What's region-specific |
|------|----------------------|
| `stations.json` | Station definitions (lat/lon/altitude/crops/language) |
| `config.py` | `_HARDCODED_STATIONS` fallback list, `region_name`, `timezone` defaults |
| `src/ingestion.py` | `_baseline()` uses Kerala/TN altitude thresholds (synthetic only); `ingest_real_stations()` uses IMD |
| `src/healing.py` | `SEASONAL_CONTEXT` dict (24 entries: Kerala × 12 months + Tamil Nadu × 12 months) |
| `src/translation/curated_advisories.py` | Advisory matrix for 17 Kerala/TN crops × 9 weather conditions |
| `src/dpi/simulator.py` | Farmer templates for 20 India stations (loads from `farmers.json` if present) |
| `src/dpi/models.py` | India-specific service names (AadhaarProfile, PMKISANRecord, etc.) for universal concepts |
| `farmers.json` | Demo farmer profiles per station (optional, auto-generated from templates) |
| `frontend/src/regionConfig.ts` | All dashboard geography strings: region name, states, languages, locale, currency, data source label, farmer service names |
| `.env` | `REGION_NAME`, `TIMEZONE` |

### Globally portable files (no changes needed)

- `src/pipeline.py` — Generic orchestrator
- `src/forecasting.py` — GraphCast/NeuralGCM + XGBoost MOS (timezone now configurable)
- `src/weather_clients.py` — OpenMeteo (global), NASA POWER (global), Tomorrow.io (global)
- `src/downscaling/` — IDW + lapse-rate math (universal)
- `src/translation/rag_provider.py` — FAISS+BM25 hybrid RAG (language-agnostic)
- `src/delivery/` — Console/Twilio/WhatsApp (global)
- `src/database/` — All 17 tables are geography-neutral
- `src/models.py` — Pydantic contracts (geography-neutral)
- `src/auth.py`, `src/api.py` — JWT auth, FastAPI endpoints
- `dagster_pipeline/` — Dagster orchestration
- `tests/` — Test fixtures reference India stations (expected for reference impl)

### Recommended workflow

1. Fork the repo
2. Create `stations.json` with your stations
3. Create `farmers.json` with demo profiles for your region (optional)
4. Set `REGION_NAME` and `TIMEZONE` in `.env`
5. Run the REBUILD.md Claude Code prompt to adapt remaining files
6. Test: `python run_pipeline.py && pytest tests/`

### Custom data ingestion

Set `config.weather.ingestion_source = "custom"` and provide an async function via `config.weather.custom_ingest_fn` that accepts a `StationConfig` and returns a dict with keys: `temperature`, `humidity`, `wind_speed`, `pressure`, `rainfall`. See `src/ingestion.py` module docstring for the full interface.
