# Weather AI 2 — Kerala & Tamil Nadu Farming Pipeline

## Project Vision
Self-healing, AI-powered weather forecasting for smallholder farmers in Kerala and Tamil Nadu. The pipeline ingests real station data from IMD (India Meteorological Department) with imdlib gridded backup, heals anomalies, generates MOS-corrected forecasts, downscales to farmer GPS coordinates, produces bilingual (Tamil/Malayalam) agricultural advisories via RAG + Claude, and delivers via SMS.

---

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Add API keys
cp .env.example .env      # then fill in keys

# Run the full pipeline with real IMD data (all 20 stations)
python run_pipeline.py

# Run with synthetic data (old behavior)
python run_pipeline.py --source synthetic

# Launch the Streamlit dashboard
streamlit run streamlit_app/app.py

# NL agent CLI
python run_chat.py

# Station health monitor
python run_monitor.py

# Health check endpoint
uvicorn src.health:app --port 8000

# Webhook receiver
uvicorn src.webhook_receiver:app --port 8001

# Dagster orchestration UI
dagster dev -m dagster_pipeline
```

---

## Architecture

Each API has exactly ONE job — no source is shared between stages:

```
IMD Scraper + imdlib → Step 1 Ingest     (real station obs, fallback: synthetic)
Tomorrow.io          → Step 2 Heal        (cross-validation reference)
Open-Meteo           → Step 3 Forecast    (GFS/ECMWF NWP baseline)
NASA POWER           → Step 4 Downscale   (0.5° spatial grid → farmer GPS)
Claude API           → Step 5 Translate   (RAG advisory + Tamil/Malayalam)
```

### Pipeline (6 steps, linear)

| Step | Output table | What it does |
|---|---|---|
| 1 Ingest | `raw_telemetry` | Real IMD station data (scraper → imdlib → synthetic fallback) |
| 2 Heal | `clean_telemetry` | Tomorrow.io cross-validation, NULL-fill (wind/pressure), anomaly flagging, quality scoring |
| 3 Forecast | `forecasts` | Open-Meteo NWP + XGBoost MOS correction (12-feature vector) |
| 4 Downscale | `forecasts` (updated) | NASA POWER IDW interpolation + lapse-rate elevation correction |
| 5 Translate | `agricultural_alerts` | Hybrid RAG (FAISS+BM25) + Claude advisory + translation |
| 6 Deliver | `delivery_log` | Console SMS (Twilio dry-run) |

### Degradation chain (independent, never cascades)
- IMD scraper down → imdlib gridded (T-1 day) → synthetic fallback
- NWP unavailable → persistence model (last obs + diurnal adjustment)
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
├── config.py                  # All station configs + pipeline dataclasses
├── run_pipeline.py            # Main entry point
├── run_chat.py                # NL agent CLI
├── run_monitor.py             # Station health monitor
├── trace_pipeline.py          # Step-by-step pipeline demo
├── requirements.txt
├── pyproject.toml
├── dvc.yaml                   # DVC pipeline: export_training_data → train_mos
├── .env                       # API keys (never commit)
├── .streamlit/
│   ├── config.toml            # Theme + server config
│   └── secrets.toml           # API keys for Streamlit Cloud (never commit)
├── src/
│   ├── pipeline.py            # WeatherPipeline orchestrator (6-step linear)
│   ├── database/              # DuckDB lakehouse (15 tables)
│   │   ├── __init__.py        # DDL, init_db(), re-exports all public names
│   │   ├── telemetry.py       # raw/clean telemetry CRUD + paired join
│   │   ├── forecasts.py       # forecast CRUD + actuals join
│   │   ├── alerts.py          # agricultural_alerts CRUD
│   │   ├── delivery.py        # delivery_log + delivery_metrics CRUD
│   │   ├── pipeline_runs.py   # start/finish pipeline run
│   │   ├── conversation.py    # conversation_log CRUD
│   │   └── health.py          # station health aggregation query
│   ├── models.py              # Pydantic v2 data contracts (stage boundary validation)
│   ├── healing.py             # RuleBasedFallback (cross-validation + NULL-fill + anomaly flagging) + Claude agents
│   ├── ingestion.py           # IMD scraper + imdlib gridded + synthetic fallback
│   ├── weather_clients.py     # Tomorrow.io, Open-Meteo, NASA POWER, IMD JSON API + imdlib clients
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
│   │   └── rag_index_builder.py   # Build FAISS + BM25 index
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
│   │   ├── simulator.py       # SimulatedDPIRegistry: 40+ farmers across 20 stations
│   │   └── services.py        # DPIService protocol + SimulatedDPIService + factory
│   ├── event_bus.py           # File-based pub/sub event bus
│   ├── quality_checks.py      # Post-pipeline data quality checks (row count, nulls, ranges, freshness)
│   ├── health.py              # FastAPI /health endpoint (DuckDB connectivity, pipeline freshness)
│   ├── webhook_receiver.py    # FastAPI webhook receiver (POST /webhook, GET /webhook/history)
│   ├── scheduler.py           # APScheduler-based pipeline scheduling
│   ├── monitor.py             # Station health monitor
│   └── architecture.py        # Dynamic Mermaid diagram generator
├── dagster_pipeline/          # Dagster orchestration (alternative to run_pipeline.py)
│   ├── __init__.py            # Dagster definitions
│   ├── resources.py           # Dagster resources (API clients)
│   ├── io_manager.py          # DuckDB I/O manager
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
│   ├── app.py                 # Homepage: forecast table + advisory feed
│   ├── data_helpers.py        # Shared DB queries + Streamlit secrets injection
│   ├── style.py               # Shared CSS (Inter font, cream/gold theme)
│   └── pages/
│       ├── 1_Network.py       # Station map (pydeck/CARTO), health, data quality
│       ├── 2_Forecasts.py     # Station forecasts + model performance tabs
│       ├── 3_Advisories.py    # Advisory feed with hover-to-English, SMS preview
│       ├── 4_Chat.py          # NL agent chat interface
│       └── 5_System.py        # Mermaid architecture, pipeline runs, cost
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

## Database (DuckDB — 15 tables)

| Table | Domain | Purpose |
|---|---|---|
| `raw_telemetry` | telemetry | Real IMD station readings (or synthetic with injected faults) |
| `clean_telemetry` | telemetry | Cross-validated readings with quality scores, NULL fields filled from Tomorrow.io |
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

---

## Forecasting Model

**Architecture:** MOS (Model Output Statistics) — same approach used by national weather services.

- **NWP baseline:** GFS/ECMWF via Open-Meteo (hourly, 7-day)
- **XGBoost correction:** trained on residual between NWP and observations
- **12-feature vector:** `nwp_temp`, `nwp_rainfall`, `humidity`, `wind_speed`, `pressure`, `station_altitude`, `soil_moisture`, `rolling_6h_error`, `recent_temp_trend`, `hour_sin`, `hour_cos`, `doy_sin`
- **Soil moisture proxy:** NASA POWER `PRECTOTCORR` (mm/day) / 20, capped at 1.0
- **Rolling error tracking:** per-station 6h error window, updated after each prediction
- **Fallback:** persistence model (last obs + diurnal adjustment)
- **Formula:** `Final = NWP_Forecast + XGBoost_Correction(features)`
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

**40+ simulated farmers** across 20 stations with realistic Kerala/Tamil Nadu data (district-specific crops, soil types, irrigation, names in Malayalam/Tamil).

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

## Dagster Orchestration

Alternative to `run_pipeline.py` — same 6 steps as Dagster assets with:
- Resources for API clients (Tomorrow.io, NASA POWER, Open-Meteo)
- DuckDB I/O manager
- Schedules, sensors, hooks
- Asset checks (data quality validation)
- Launch via `dagster dev -m dagster_pipeline`

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
| `ANTHROPIC_API_KEY` | Claude advisory generation + translation | Pay-per-use (~$0.12/run) |
| `TOMORROW_IO_API_KEY` | Anomaly healing cross-validation | 500 calls/day free |

NASA POWER, Open-Meteo, IMD city weather (scraping), and imdlib are fully free, no key needed.

Set in `.env` for local development. On Streamlit Cloud, add to App Settings → Secrets.

---

## Deployment

### Hugging Face Spaces (recommended)
HF Spaces free tier gives **16 GB RAM** — enough for RAG (sentence-transformers + FAISS).
- `models/faiss_index/` (180 KB) is committed — RAG index is pre-built
- BGE embedding model downloads from HF Hub on first use (~30 sec on HF infra)
- `weather.duckdb` is committed (pre-populated data)

### Streamlit Cloud
- Main file: `streamlit_app/app.py`, Python 3.11
- RAG needs ~1.5 GB RAM; free tier (1 GB) auto-falls back to rule-based advisories
- Map uses CARTO Positron tiles (free, no Mapbox token)

---

## Tech Stack

- **Python 3.12+**, **DuckDB** (embedded lakehouse)
- **anthropic** (Claude API — advisory generation + translation)
- **xgboost** + **scikit-learn** (MOS correction model)
- **faiss-cpu** + **sentence-transformers** + **rank-bm25** (RAG retrieval)
- **langchain-huggingface** + **datasets** (index building)
- **pydantic** v2 (data contracts at stage boundaries)
- **httpx** (async HTTP for weather APIs)
- **beautifulsoup4** + **imdlib** (IMD data scraping + gridded backup)
- **streamlit** + **pydeck** (dashboard)
- **dagster** (orchestration — alternative to linear pipeline)
- **fastapi** + **uvicorn** (health endpoint + webhook receiver)
- **apscheduler** (scheduled pipeline runs)
- **rich** (terminal output)
- **DVC** (ML model versioning pipeline)
