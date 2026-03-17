# Weather AI 2 — Kerala & Tamil Nadu Farming Pipeline

## Project Vision
Self-healing, AI-powered weather forecasting for smallholder farmers in Kerala and Tamil Nadu. The pipeline ingests synthetic sensor data, heals anomalies, generates MOS-corrected forecasts, downscales to farmer GPS coordinates, produces bilingual (Tamil/Malayalam) agricultural advisories via RAG + Claude, and delivers via SMS.

---

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Add API keys
cp .env.example .env      # then fill in keys

# Run the full pipeline (all 20 stations)
python run_pipeline.py

# Launch the Streamlit dashboard
streamlit run streamlit_app/app.py

# NL agent CLI
python run_chat.py

# Station health monitor
python run_monitor.py
```

---

## Architecture

Each API has exactly ONE job — no source is shared between stages:

```
Synthetic Generator  → Step 1 Ingest
Tomorrow.io          → Step 2 Heal        (cross-validation reference)
Open-Meteo           → Step 3 Forecast    (GFS/ECMWF NWP baseline)
NASA POWER           → Step 4 Downscale   (0.5° spatial grid → farmer GPS)
Claude API           → Step 5 Translate   (RAG advisory + Tamil/Malayalam)
```

### Pipeline (6 steps, linear)

| Step | Output table | What it does |
|---|---|---|
| 1 Ingest | `raw_telemetry` | Synthetic ground-station readings with fault injection |
| 2 Heal | `clean_telemetry` | Tomorrow.io cross-validation, imputation, anomaly detection |
| 3 Forecast | `forecasts` | Open-Meteo NWP + XGBoost MOS correction (12-feature vector) |
| 4 Downscale | `forecasts` (updated) | NASA POWER IDW interpolation + lapse-rate elevation correction |
| 5 Translate | `agricultural_alerts` | Hybrid RAG (FAISS+BM25) + Claude advisory + translation |
| 6 Deliver | `delivery_log` | Console SMS (Twilio dry-run) |

### Degradation chain (independent, never cascades)
- NWP unavailable → persistence model (last obs + diurnal adjustment)
- XGBoost not trained → raw NWP passthrough
- Claude down → rule-based template advisories
- Tomorrow.io down → skip healing, pass raw through
- NASA POWER down (heal) → skip that record, never fabricate
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
├── requirements.txt
├── .env                       # API keys (never commit)
├── .streamlit/
│   ├── config.toml            # Theme + server config
│   └── secrets.toml           # API keys for Streamlit Cloud (never commit)
├── src/
│   ├── pipeline.py            # WeatherPipeline orchestrator
│   ├── database.py            # DuckDB lakehouse schema (6 tables)
│   ├── ingestion.py           # Synthetic sensor + fault injection
│   ├── agents.py              # Observability + self-healing agents
│   ├── weather_clients.py     # Tomorrow.io, Open-Meteo, NASA POWER clients
│   ├── forecasting.py         # HybridNWPModel: NWP + XGBoost MOS
│   ├── downscaling/           # IDW spatial interpolation + lapse-rate
│   ├── translation/           # RAG + Claude advisory provider
│   │   ├── __init__.py        # Provider factory + async dispatch
│   │   ├── rag_provider.py    # FAISS+BM25 hybrid search → Claude
│   │   ├── local_provider.py  # Rule-based fallback (no API)
│   │   └── rag_index_builder.py
│   ├── delivery/              # Console + Twilio SMS/WhatsApp
│   ├── nl_agent/              # NLAgent: Claude tool-use orchestration
│   ├── access/                # RBAC: 5 roles, 10 permissions
│   └── architecture.py        # Dynamic Mermaid diagram generator
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
└── models/                    # Trained XGBoost + FAISS index (auto-built)
```

---

## Stations (20 total)

**Kerala (10):** Thiruvananthapuram, Kollam, Kottayam, Alappuzha, Ernakulam, Thrissur, Palakkad, Kozhikode, Malappuram, Kannur
**Tamil Nadu (10):** Thanjavur, Madurai, Tiruchirappalli, Dindigul, Salem, Erode, Chennai, Tirunelveli, Coimbatore, Vellore

Languages: Malayalam (`ml`) for Kerala, Tamil (`ta`) for Tamil Nadu.

---

## Forecasting Model

**Architecture:** MOS (Model Output Statistics) — same approach used by national weather services.

- **NWP baseline:** GFS/ECMWF via Open-Meteo (hourly, 7-day)
- **XGBoost correction:** trained on residual between NWP and observations
- **12-feature vector:** `nwp_temp`, `nwp_rainfall`, `humidity`, `wind_speed`, `pressure`, `station_altitude`, `soil_moisture`, `rolling_6h_error`, `recent_temp_trend`, `hour_sin`, `hour_cos`, `doy_sin`
- **Soil moisture proxy:** NASA POWER `PRECTOTCORR` (mm/day) ÷ 20, capped at 1.0
- **Rolling error tracking:** per-station 6h error window, updated after each prediction
- **Fallback:** persistence model (last obs + diurnal adjustment)
- **Formula:** `Final = NWP_Forecast + XGBoost_Correction(features)`

---

## Translation (RAG + Claude)

**Default provider:** RAG + Claude. **Fallback:** local rule-based (zero API cost).

**RAG flow:**
1. Build FAISS dense + BM25 sparse index from HuggingFace agricultural datasets
2. Hybrid retrieval (α=0.5 blend), score threshold=0.35, top-k=5
3. Generate English advisory via Claude (claude-sonnet-4-6)
4. Separate Claude call to translate to Tamil or Malayalam
5. Both `advisory_en` and `advisory_local` stored in `agricultural_alerts`

**Hover-to-translate:** Advisories page shows local language by default; hovering reveals English overlay (pure CSS, no JS).

---

## Downscaling

NASA POWER 5×5 grid (~0.5° radius around station) → IDW interpolation to farmer GPS coordinates → lapse-rate elevation correction (6.5°C per 1000m). Re-classifies weather condition at farmer scale.

---

## Database (DuckDB)

Six tables in `weather.duckdb`:
- `raw_telemetry` — synthetic sensor readings (with injected faults)
- `clean_telemetry` — healed readings with quality scores
- `forecasts` — MOS-corrected forecasts (station + farmer-level)
- `agricultural_alerts` — bilingual advisories (advisory_en + advisory_local)
- `delivery_log` — SMS delivery records
- `pipeline_runs` — run history with step-level status

---

## API Keys

| Key | Used for | Free tier |
|---|---|---|
| `ANTHROPIC_API_KEY` | Claude advisory generation + translation | Pay-per-use (~$0.12/run) |
| `TOMORROW_IO_API_KEY` | Anomaly healing cross-validation | 500 calls/day free |

NASA POWER and Open-Meteo are fully free, no key needed.

Set in `.env` for local development. On Streamlit Cloud, add to App Settings → Secrets.

---

## Hugging Face Spaces Deployment (recommended)

HF Spaces free tier gives **16 GB RAM** — enough for RAG (sentence-transformers + FAISS) to work fully.

1. Push to GitHub (`.gitignore` already excludes `.env` and `secrets.toml`)
2. Go to [huggingface.co/new-space](https://huggingface.co/new-space)
   - SDK: **Streamlit**
   - The `README.md` already contains the required YAML frontmatter
3. Add secrets in Space Settings → Variables and Secrets:
   - `ANTHROPIC_API_KEY`
   - `TOMORROW_IO_API_KEY`
4. Secrets are injected as plain **environment variables** — `config.py` already reads from `os.getenv()`, so no code changes needed.

**Notes:**
- `models/faiss_index/` (180 KB) is committed — RAG index is pre-built, no rebuild step needed.
- The BGE embedding model (`BAAI/bge-base-en-v1.5`, ~419 MB) downloads from HF Hub on first use and is cached for the container lifetime. On HF infrastructure this is fast (~30 sec vs ~5 min elsewhere).
- `weather.duckdb` is committed (9.6 MB) so the Space loads with pre-populated data — no pipeline run needed on first visit.
- `packages.txt` handles the `libgomp1` system dependency that `faiss-cpu` requires.

---

## Streamlit Cloud Deployment

1. Push to GitHub (`.gitignore` excludes `.env`, `secrets.toml`, `*.duckdb`)
2. Go to [share.streamlit.io](https://share.streamlit.io) → New app
   - Main file: `streamlit_app/app.py`
   - Python version: 3.11
3. Add secrets in App Settings → Secrets (contents of `.streamlit/secrets.toml`)

**Notes:**
- RAG advisory generation requires ~1.5 GB RAM (embedding model). Free tier (1 GB) falls back to rule-based advisories automatically.
- `weather.duckdb` is committed so the app loads with pre-populated data.
- Map uses CARTO Positron tiles (free, no Mapbox token needed).

---

## Tech Stack

- **Python 3.12+**, **DuckDB** (embedded lakehouse)
- **anthropic** (Claude API — advisory generation + translation)
- **xgboost** + **scikit-learn** (MOS correction model)
- **faiss-cpu** + **sentence-transformers** + **rank-bm25** (RAG retrieval)
- **langchain-huggingface** + **datasets** (index building)
- **httpx** (async HTTP for weather APIs)
- **streamlit** + **pydeck** (dashboard)
- **apscheduler** (scheduled pipeline runs)
- **rich** (terminal output)
