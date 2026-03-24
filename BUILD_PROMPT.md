# One-Shot Build Prompt: Weather AI 2 — Kerala & Tamil Nadu Farming Pipeline

Build a complete, production-grade AI-powered weather forecasting pipeline for smallholder farmers in Kerala and Tamil Nadu (India). The system ingests real station data from IMD (India Meteorological Department), cross-validates and heals it against Tomorrow.io, generates MOS-corrected forecasts, downscales to farmer GPS coordinates, produces bilingual (Tamil/Malayalam) agricultural advisories via RAG + Claude, and delivers via SMS. Deployed on HuggingFace Spaces via Docker with a Streamlit dashboard.

---

## Stack & Dependencies

- **Python 3.11**, **DuckDB** (embedded lakehouse — single file `weather.duckdb`, 16 tables)
- **neuralgcm** + **jax[cuda12]** — Google DeepMind neural weather model (GPU, L4/T4)
- **gcsfs** + **xarray** + **zarr** — ERA5 reanalysis data access for NeuralGCM initial conditions
- **anthropic** (Claude claude-sonnet-4-6) — advisory generation + translation + NL chat tool-use
- **faiss-cpu** + **sentence-transformers** (BAAI/bge-base-en-v1.5) + **rank-bm25** — hybrid RAG retrieval
- **xgboost** + **scikit-learn** — MOS forecast correction model
- **httpx** — async HTTP for all weather APIs (IMD, Tomorrow.io, Open-Meteo, NASA POWER)
- **imdlib** — IMD gridded rainfall/temperature data (0.25°–0.5° resolution, T-1 day lag)
- **pydantic** v2 — data contracts at every stage boundary
- **streamlit** + **pydeck** — dashboard with CARTO Positron tiles (free, no Mapbox)
- **apscheduler** — daily scheduled pipeline runs (background thread)
- **dagster** — alternative orchestration (same 6 steps as Dagster assets)
- **fastapi** + **uvicorn** — health endpoint + webhook receiver
- **langchain-huggingface** — embedding wrapper for index building
- **rich** — terminal output formatting
- **DVC** — ML model versioning (`export_training_data.py` → `train_mos.py`)

API keys needed: `ANTHROPIC_API_KEY`, `TOMORROW_IO_API_KEY`. NASA POWER, Open-Meteo, IMD city weather API, and imdlib are fully free, no key needed.

---

## The 6-Step Pipeline

Each step fails independently — never cascades. Every step has a fallback. The pipeline is orchestrated by `WeatherPipeline` in `src/pipeline.py` — one `async run()` method calls `step_ingest()` → `step_heal()` → `step_forecast()` → `step_downscale()` → `step_translate()` → `step_deliver()`.

Each API has exactly ONE job — no source is shared between stages:

```
IMD JSON API + imdlib → Step 1 Ingest     (real station observations, fallback: synthetic)
Tomorrow.io           → Step 2 Heal        (cross-validation reference source)
NeuralGCM / Open-Meteo → Step 3 Forecast  (NeuralGCM 1.4° on GPU, fallback: Open-Meteo GFS/ECMWF)
NASA POWER            → Step 4 Downscale   (0.5° spatial grid → farmer GPS)
Claude API            → Step 5 Translate   (RAG advisory generation + Tamil/Malayalam translation)
```

### Step 1: Ingest (`raw_telemetry`)

**Primary source:** IMD JSON API at `https://city.imd.gov.in/citywx/responsive/api/fetchCity_static.php`. POST with `data={"ID": imd_id}` where `imd_id` is the WMO SYNOP station ID (e.g., "43371" for Thiruvananthapuram). Returns JSON list with one dict containing `max`, `min` (temperature), `rh` (relative humidity), `rain_24` (rainfall mm). **Sentinel value 999 means missing data** — filter with `_safe_float()` that returns None for values ≥ 999. Use `verify=False` for HTTPS (IMD's cert chain is incomplete). Cache results with TTL.

**Backup source:** `imdlib` gridded data — 0.25°–0.5° resolution, T-1 day lag, temperature + rainfall only (no humidity/wind/pressure). Used when IMD API returns no data for a station (e.g., Thanjavur 43330 returns `{"status": 404}`).

**Synthetic fallback:** Generated readings with configurable fault injection (~5% rate: `typo`, `drift`, `offline`, `missing`). Only used when both real sources fail, or explicitly with `--source synthetic`.

Store all readings in `raw_telemetry` DuckDB table with `source` column ("imd", "imdlib", or "synthetic").

### Step 2: Heal (`clean_telemetry` + `healing_log`)

**Primary: Claude-powered AI Healing Agent** (`HealingAgent` in `src/healing.py`)

Single-batch, multi-tool agentic loop using Claude Sonnet (`claude-sonnet-4-6`). All 20 readings sent in one API call. The agent uses 5 investigation tools to assess each reading:

1. `get_station_metadata` — station name, lat/lon, altitude, state, crop context, WMO SYNOP ID
2. `get_historical_normals` — min/mean/max per field from past clean_telemetry for that station + calendar month
3. `get_reference_comparison` — Tomorrow.io (or NASA POWER fallback) cross-validation reference for station coordinates
4. `check_neighboring_stations` — current readings from other IMD stations within radius (uses `haversine_km()`)
5. `get_seasonal_context` — 24-entry lookup (12 months × 2 states) with season name, typical weather patterns, agricultural context

All tools execute locally (zero API calls during the agentic loop). The agent calls whichever tools it needs, then returns a JSON assessment for every reading: `assessment` (good/corrected/filled/flagged/dropped), `reasoning` (1-2 sentences shown on dashboard), `corrections` ({field: new_value}), `quality_score` (0.0-1.0), `tools_used`.

System prompt grounds Claude in: IMD station network context, Tomorrow.io cross-validation thresholds, Indian tropical weather norms (monsoon seasons, 40-45°C summer Tamil Nadu is normal), spatial consistency checks, and the no-fabrication rule.

Assessments stored in `healing_log` table (reasoning, corrections, tools_used, tokens, latency per reading).

**Fallback: Rule-based** (`RuleBasedFallback` in `src/healing.py`)

Three-phase deterministic healing when Anthropic API is unavailable:

**Phase 1 — Fault-based healing** (synthetic mode only): detect and correct injected faults (typo correction for decimal-place errors like 320°C → 32.0°C, drift imputation, offline filling).

**Phase 2 — NULL field filling**: For each reading, fetch reference from Tomorrow.io (batches of 2, 2-second sleep between batches — rate limit: free tier). Fill NULL fields (wind_speed, pressure, wind_dir) from the reference. Fall back to NASA POWER if Tomorrow.io fails.

**Phase 3 — Cross-validation**: Compare each reading's fields against the Tomorrow.io reference. Thresholds: temperature 8°C, humidity 25%, wind_speed 15 km/h, pressure 15 hPa, rainfall 20mm. Fields within threshold = agreement. Quality score = weighted agreement (temperature gets 2x weight) minus penalties (-0.05 per remaining NULL), floor at 0.3.

**Heal actions (AI):** `ai_validated`, `ai_corrected`, `ai_filled`, `ai_flagged` (with reasoning in healing_log).
**Heal actions (rule-based):** `cross_validated`, `null_filled`, `anomaly_flagged`, `typo_corrected`, `imputed_from_reference`.

Store healed readings in `clean_telemetry` with `quality_score` (0.0–1.0) and `heal_action` columns. Cost: ~$0.15/run with Sonnet.

### Step 3: Forecast (`forecasts`)

**NWP primary: NeuralGCM 1.4°** (Google DeepMind's neural GCM, `src/neuralgcm_client.py`):
- Runs on GPU (JAX) via HF Spaces L4 tier. Single inference pass produces global forecast → extracts all 20 station forecasts via nearest-gridpoint interpolation.
- Initial conditions: ERA5 reanalysis from ARCO Zarr on Google Cloud Storage (free, no auth, ~5-day lag via ERA5T). Fetches pressure-level vars (u, v, T, Z, q, cloud) + surface forcings (SST, sea ice).
- Post-processing: temperature K→°C at station-appropriate pressure level (accounting for altitude), specific humidity→RH, u/v→wind speed/direction, surface pressure from barometric formula.
- Matches ECMWF-HRES accuracy for 1-5 day forecasts. Enabled via `--neuralgcm` flag or `config.neuralgcm.enabled = True`.

**NWP fallback: Open-Meteo** (GFS/ECMWF via free API, no GPU needed). Per-station HTTP calls, same as before.

**MOS correction:** XGBoost trained on residual between NWP and observations. 12-feature vector: `nwp_temp`, `nwp_rainfall`, `humidity`, `wind_speed`, `pressure`, `station_altitude`, `soil_moisture`, `rolling_6h_error`, `recent_temp_trend`, `hour_sin`, `hour_cos`, `doy_sin`. Soil moisture proxy: NASA POWER `PRECTOTCORR` (mm/day) / 20, capped at 1.0. Rolling error: per-station 6h window, updated after each prediction. MOS correction applies identically regardless of NWP source.

**Formula:** `Final = NWP_Forecast + XGBoost_Correction(features)`

**Fallback:** Persistence model (last observation + diurnal adjustment) when NWP unavailable.

**DVC pipeline:** `scripts/export_training_data.py` → Parquet → `scripts/train_mos.py` → `models/hybrid_mos.json`

Store in `forecasts` table with `model_used` ("neuralgcm_mos", "neuralgcm_only", "hybrid_mos", "nwp_only", or "persistence"), `nwp_source` ("neuralgcm" or "open_meteo"), `confidence`, `condition`.

### Step 4: Downscale (`forecasts` updated)

Query NASA POWER for a 5×5 grid (~0.5° radius) around each station. Use IDW (Inverse Distance Weighting) interpolation to each farmer's GPS coordinates (from DPI registry). Apply lapse-rate elevation correction: `Final = IDW_Temp - (0.0065 × altitude_delta_m)`. Re-classify weather condition at farmer scale. Update `forecasts` table with `farmer_lat`, `farmer_lon`, `downscaled=True`.

### Step 5: Translate (`agricultural_alerts`)

Three-level fallback chain: **RAGProvider → ClaudeProvider → LocalProvider**

**RAGProvider** (primary):
1. Query reformulation: convert forecast dict to NL search query
2. Hybrid retrieval: FAISS dense (BGE embeddings) + BM25 sparse, α=0.5 blend, threshold=0.35, top-k=5
3. Claude call #1 (claude-sonnet-4-6): English advisory grounded in retrieved docs
4. Claude call #2: translate to Tamil (`ta`) or Malayalam (`ml`)

**ClaudeProvider** (fallback if RAG index fails):
- Direct Claude call with forecast context, no FAISS needed
- Parse `ENGLISH: [...]` and `TAMIL:/MALAYALAM: [...]` format

**LocalProvider** (final fallback — zero API cost):
- Rule-based lookup in `curated_advisories.py` matrix (condition × crop → advisory)
- Covers 17 Kerala/TN crops × 10 weather conditions

Store both `advisory_en` and `advisory_local` in `agricultural_alerts`.

### Step 6: Deliver (`delivery_log`)

Console SMS output (Twilio dry-run). Log each delivery to `delivery_log`. Aggregate metrics to `delivery_metrics`. Track full run in `pipeline_runs` with per-step status.

---

## Degradation Chain (independent — never cascades)

- Claude healing agent unavailable → rule-based fallback (same output, no reasoning logged)
- IMD API down → imdlib gridded (T-1 day) → synthetic fallback
- Tomorrow.io down → cross-validate against NASA POWER; if both down → quality by data completeness
- NASA POWER down (heal) → quality score reflects missing cross-validation
- NeuralGCM unavailable (no GPU / package not installed / ERA5 fetch fails) → Open-Meteo API fallback
- NWP unavailable (both NeuralGCM + Open-Meteo fail) → persistence model (last obs + diurnal adjustment)
- XGBoost not trained → raw NWP passthrough
- Claude down → rule-based template advisories
- NASA POWER down (downscale) → use station-level forecast
- Translation fails → return English advisory
- Twilio fails → console delivery only

---

## 20 Stations

All stations have verified WMO SYNOP station IDs that map to IMD's city weather JSON API.

**Kerala (10, language=`ml`):**

| ID | Name | SYNOP | Alt(m) | Crops |
|---|---|---|---|---|
| KL_TVM | Thiruvananthapuram | 43371 | 60 | coconut, rubber, banana, tapioca, pepper |
| KL_COK | Kochi | 43353 | 1 | coconut, rubber, pineapple, nutmeg, banana |
| KL_ALP | Alappuzha | 43352 | 2 | rice (paddy), coconut, banana, tapioca |
| KL_KNR | Kannur | 43315 | 11 | coconut, cashew, pepper, rubber, arecanut |
| KL_KZD | Kozhikode | 43314 | 4 | coconut, pepper, arecanut, rubber, banana |
| KL_TCR | Thrissur | 43357 | 40 | rice (paddy), coconut, arecanut |
| KL_KTM | Kottayam | 43355 | 39 | rubber, coconut, pepper, banana, cardamom |
| KL_PKD | Palakkad | 43335 | 95 | rice (paddy), coconut, groundnut, arecanut, banana |
| KL_PNL | Punalur | 43354 | 33 | rubber, coconut, cashew, pepper, tapioca |
| KL_NLB | Nilambur | 43316 | 30 | coconut, rubber, arecanut, pepper, paddy |

**Tamil Nadu (10, language=`ta`):**

| ID | Name | SYNOP | Alt(m) | Crops |
|---|---|---|---|---|
| TN_TNJ | Thanjavur | 43330 | 0 | rice (paddy), pulses, sugarcane, banana, coconut |
| TN_MDU | Madurai | 43360 | 139 | paddy, cotton, groundnut, millets, banana |
| TN_TRZ | Tiruchirappalli | 43344 | 85 | paddy, banana, sugarcane, groundnut, maize |
| TN_SLM | Salem | 43325 | 279 | paddy, tapioca, groundnut, turmeric, mango |
| TN_ERD | Erode | 43338 | 183 | turmeric, sugarcane, coconut, banana, cotton |
| TN_CHN | Chennai | 43279 | 10 | rice (paddy), groundnut, sugarcane, vegetables |
| TN_TNV | Tirunelveli | 43376 | 45 | paddy, banana, cotton, millets, coconut |
| TN_CBE | Coimbatore | 43321 | 396 | cotton, coconut, groundnut, vegetables, millets |
| TN_VLR | Vellore | 43303 | 215 | paddy, groundnut, sugarcane, mango, vegetables |
| TN_NGP | Nagappattinam | 43347 | 2 | rice (paddy), banana, coconut, cashew, pulses |

Each station has: `station_id`, `name`, `lat`, `lon`, `altitude_m`, `state`, `crop_context`, `language`, `imd_id` (WMO SYNOP).

---

## Config (`config.py`)

All API keys read from `os.getenv()` with `.strip()` — **critical**: HF Spaces secret UI appends `\n` to pasted values; `.strip()` prevents `Illegal header value` errors in httpx.

```python
@dataclass
class PipelineConfig:
    anthropic_key: str = field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", "").strip())
    tomorrow_io_key: str = field(default_factory=lambda: os.getenv("TOMORROW_IO_API_KEY", "").strip())
```

`STATIONS` list of 20 `StationConfig` dataclasses defined at module level. `get_config()` factory function.

---

## Database (DuckDB — 15 tables)

| Table | Domain | Purpose |
|---|---|---|
| `raw_telemetry` | telemetry | Real IMD station readings with `source` column (imd/imdlib/synthetic) |
| `clean_telemetry` | telemetry | AI-healed or rule-based cross-validated readings with `quality_score`, `heal_action` |
| `healing_log` | telemetry | Per-reading AI agent assessments: `reasoning`, `corrections` (JSON), `tools_used`, `quality_score`, `model`, `tokens_in/out`, `latency_s` |
| `forecasts` | forecasts | MOS-corrected forecasts with `model_used`, `confidence`, optional downscaled fields |
| `agricultural_alerts` | alerts | Bilingual advisories (`advisory_en` + `advisory_local`), `provider`, `condition` |
| `delivery_log` | delivery | SMS delivery records per farmer |
| `delivery_metrics` | delivery | Per-station delivery aggregates per run |
| `pipeline_runs` | pipeline | Run history with `started_at`, `status` (ok/partial/failed), `summary`, `steps_ok` |
| `conversation_log` | conversation | NL agent + conversation agent chat logs |
| `conversation_sessions` | conversation | Stateful session tracking |
| `conversation_memory` | conversation | Per-farmer extracted memories |
| `scheduled_followups` | conversation | Proactive follow-up messages |
| `feedback_responses` | delivery | Farmer feedback on advisories |
| `farmer_profiles` | DPI | Cached composite farmer profiles |
| `farmer_land_records` | DPI | Land records from DPI |
| `farmer_soil_health` | DPI | Soil Health Card data |

Database module structure: `src/database/__init__.py` (DDL + init_db()), `telemetry.py`, `forecasts.py`, `alerts.py`, `delivery.py`, `pipeline_runs.py`, `conversation.py`, `health.py`, `healing.py`.

---

## RAG Corpus

The FAISS index is built from two sources:
1. **`src/translation/ag_corpus.json`** — ~6,000 texts extracted from HF datasets (committed as plain JSON — do NOT use the `datasets` package at runtime). Original datasets: `KisanVaani/agriculture-qa-english-only`, `Mahesh2841/agriculture`, `YuvrajSingh9886/agriculture-soil-qa-pairs-dataset`.
2. **`src/translation/curated_advisories.py`** — hand-crafted matrix covering 17 Kerala/TN crops × 10 weather conditions. Each entry 3-4 sentences with specific chemical names, application rates, and timing.

The FAISS index is built at first pipeline run and cached to `models/faiss_index/`. The index rebuilds from `ag_corpus.json` in ~3 minutes on first run, then loads from cache. The `.faiss` file can be committed (180 KB) for instant startup.

---

## Pydantic Data Contracts (`src/models.py`)

Validates data at every stage boundary:
- `RawReading` (stage 1 output)
- `CleanReading` (stage 2 output — includes `quality_score`, `heal_action`)
- `Forecast` / `DownscaledForecast` (stage 3-4 output)
- `Advisory` (stage 5 output)
- `DeliveryLog` (stage 6 output)

---

## DPI (Digital Public Infrastructure) Subsystem

**6 simulated government services** (single generic class in `src/dpi/services.py`):
1. **Aadhaar eKYC** — identity (name, name_local, district, state, language)
2. **Land Records** — survey number, area, GPS coordinates, soil type, irrigation type
3. **Soil Health Card** — pH, organic carbon, NPK levels, recommendations
4. **PM-KISAN** — direct benefit transfer status, payment history
5. **PMFBY crop insurance** — policy details, sum insured, premium, claim history
6. **Kisan Credit Card (KCC)** — credit limit, outstanding, interest rate

**DPIAgent** (`src/dpi/__init__.py`): phone → identify → parallel fetch all 6 services → composite `FarmerProfile` → cache to DB.

**SimulatedDPIRegistry** (`src/dpi/simulator.py`): 40+ simulated farmers across 20 stations with realistic Kerala/Tamil Nadu data (district-specific crops, soil types, irrigation methods, names in Malayalam/Tamil script). `get_registry()` → singleton. `list_farmers()` returns summary list. `lookup_by_phone(phone)` returns full `FarmerProfile`.

---

## NL Agent & Conversation Engine

### NLAgent (`src/nl_agent/__init__.py`)
Claude tool-use orchestration with 5 tools: check station health, get forecast, get advisory, run pipeline, explain architecture. Generic mode — no farmer identity.

### ConversationalAgent (`src/conversation/`)
Wraps NLAgent with farmer-aware, stateful capabilities:
- **State machine** (`state_machine.py`): onboarding → active → follow-up
- **Farmer identification** via DPI: phone → profile lookup → personalized context
- **Persistent per-farmer memory** (`memory.py`): extracts key facts from conversations
- **Proactive follow-up scheduling** (`followup.py`)
- **Language detection** (`language.py`): auto-detects Tamil/Malayalam/English
- **System prompt builder** (`prompts.py`): farmer profile + crop context + weather data
- **11 total tools** (5 NLAgent + 6 conversation-specific: profile, soil, insurance, land, credit, weather)

---

## Streamlit Dashboard

Pages map to pipeline stages. Chat is a floating sidebar toggle on every page. System page is hidden from sidebar navigation (underscore prefix `_System.py`), accessible via gear icon on home page.

### Style (`streamlit_app/style.py`)
- Inter font, cream background (`#faf8f5`), dark sidebar, gold accents (`#d4a019`)
- CSS classes: `.pipeline-card` (white, thin border, gold hover), `.pipeline-arrow`, `.section-header`, `.chat-toggle-btn`
- Shared constants: `STATUS_COLOR` (ok/partial/failed/running), `CONDITION_COLOR`, `CONDITION_EMOJI`
- `inject_css()` called on every page

### Home Page (`streamlit_app/app.py`)
- Clean centered header: "Weather AI" + tagline
- **Clickable pipeline diagram**: 6 stage cards in horizontal `st.columns` with gold arrow connectors. Each card shows: stage name + live stat (from `load_pipeline_stage_stats()`). Below each card, `st.page_link()` navigates to the corresponding page. Stages pair up: Ingest+Heal → Data, Forecast+Downscale → Forecasts, Translate+Deliver → Advisories.
- Key stats row: Pipeline Runs, Data Freshness (avg quality), Advisories count, Deliveries count
- Latest run summary card with color-coded status badge
- Run history in expander (compact HTML rows)
- Manual Pipeline Run button (bottom-right, clearly labeled — Dagster/scheduler handles automatic)
- Sidebar: project title, active stations metric, avg quality metric, refresh button, System gear link, chat toggle
- Auto-imports `src.daily_scheduler` on startup for auto-resume

### Data Page (`streamlit_app/pages/1_Data.py`)
Covers **Ingest + Heal**. 4 tabs:
- **Map**: pydeck ScatterplotLayer with CARTO Positron tiles. Color-coded: green (good data), orange (low quality < 0.7), red (no data). Tooltip shows station name, state, crops, record count, avg quality. Station table below.
- **Sources**: Bar chart of data source distribution (IMD API / imdlib / synthetic). Per-station source breakdown table. Source explanation card describing the three-tier data chain.
- **Healing** (centerpiece): 7 sections showcasing the AI healing agent:
  1. **Agent Status Bar** — model (claude-sonnet-4-6), token count, latency, estimated cost, last run timestamp. Amber badge if rule-based fallback was used.
  2. **Batch Assessment Overview** — colored badges for each assessment type (good/corrected/filled/flagged/dropped) with counts.
  3. **Per-Reading Assessment Cards** — expandable cards per station showing: Claude's reasoning text, before/after value diffs (corrections highlighted gold→green), tool usage pills, quality score. Cards for corrected/flagged readings auto-expanded.
  4. **Tool Usage** — bar chart of how frequently each investigation tool was called.
  5. **Healing Breakdown** — bar chart of heal_action distribution from clean_telemetry.
  6. **Quality Score Distribution** — histogram of quality scores.
  7. **Before/After + Legend** — raw vs clean telemetry side-by-side tables, plus heal action legend covering both AI and rule-based actions.
- **Station Health**: Metrics (total/active/low-quality/no-data). Health table with quality score color coding (green ≥ 0.85, amber ≥ 0.7, red < 0.7). Per-station quality bar chart.

### Forecasts Page (`streamlit_app/pages/2_Forecasts.py`)
Covers **Forecast + Downscale**. 3 tabs:
- **Station Forecasts**: Filter by state/condition. Per-station forecast cards with condition icon, temperature bar, rainfall, model badge. Grouped by state.
- **Model Performance**: Hybrid MOS vs persistence comparison. Confidence distribution histogram. Condition distribution pie chart. Per-station accuracy chart.
- **Downscaling**: Pydeck map with two layers — station points (large, blue) and farmer points (small, orange). Before/after temperature demo table showing station temp vs downscaled farmer temp with IDW weight and lapse-rate delta. Formula card: `Final = IDW_Temp - (0.0065 × alt_delta_m)`.

### Advisories Page (`streamlit_app/pages/3_Advisories.py`)
Covers **Translate + Deliver**. 4 tabs:
- **Advisory Feed**: Full-width advisory cards showing local language (Tamil/Malayalam) by default. Hover-to-English CSS overlay (pure CSS, no JS). Filters: condition, language, provider. SMS preview with character count (160-char segments). Provider distribution (RAG vs rule-based).
- **Lineage**: Forecast→advisory pairs side by side with arrow connector. Shows which forecast (condition, temperature, model, confidence) produced which advisory (text, provider, language). Joined by station_id + time proximity (< 10 min window).
- **Farmers & DPI**: Farmer selector dropdown (all 40+ farmers). Full profile card showing all 6 DPI services: Aadhaar identity, land record with GPS, soil health card with NPK levels, PM-KISAN status, PMFBY insurance details, KCC credit info. Latest advisory for that farmer's station shown below.
- **Delivery**: Delivery log table with color-coded status (delivered=green, failed=red). Metrics: total sent, failed, unique channels, unique recipients.

### System Page (`streamlit_app/pages/_System.py`)
Hidden from sidebar (underscore prefix). 8 tabs:
- **Architecture**: Mermaid diagram rendered via `components.html()` with CDN JS. Plain-text description in expander.
- **Scheduler**: Daily pipeline scheduler toggle (on/off). Shows next run time when active. Uses `src/daily_scheduler.py` (APScheduler, 06:00 IST / 00:30 UTC). State persists in `scheduler_state.json`. Manual control buttons: Run Full Pipeline, Ingest+Heal, Forecast→Deliver, Retrain MOS Model.
- **Pipeline Runs**: Run history table with status badges. Summary stats.
- **Delivery Log**: Delivery records with status filtering.
- **Cost Estimate**: Per-API cost breakdown (Claude, Tomorrow.io, free APIs).
- **Eval Metrics**: Results from offline evaluation suite (healing precision/recall, forecast accuracy, advisory quality, translation quality, RAG retrieval, DPI integration, conversation quality).
- **Agent Log**: Conversation log from NL agent and conversational agent.
- **Delivery Funnel**: Per-station delivery success rates.

### Chat Widget (`streamlit_app/chat_widget.py`)
Floating sidebar toggle on every page. Every page calls `render_chat_toggle()` at the end.
- `init_chat_state()`: session state defaults (session_id, messages, farmer_phone, agent_mode)
- Toggle button: "Chat" / "Close Chat" in sidebar
- When open: farmer identity section (phone input → DPI lookup → profile card), demo farmers list, conversation history (last 6 messages), text input + send button
- Agent dispatch: if farmer identified → `ConversationalAgent` (stateful, DPI-aware), else → `NLAgent` (generic)
- Clear conversation button

### Data Helpers (`streamlit_app/data_helpers.py`)
All DB query functions use `@st.cache_data(ttl=60)` and a `_db()` context manager (try/finally for conn.close()). Key functions:
- `get_station_coords()` / `get_station_name_map()` — station metadata from config
- `load_forecasts()`, `load_alerts()`, `load_clean_telemetry()`, `load_raw_telemetry()` — paginated table reads
- `load_station_health()` — aggregation query (count, avg quality, healed count per station)
- `load_healing_log()` — latest AI healing assessments with reasoning
- `load_healing_stats()` — aggregate: assessment distribution, tool usage frequency, latest run tokens/cost
- `load_pipeline_runs()`, `load_delivery_log()`, `load_delivery_metrics()`, `load_conversation_log()`
- `load_data_source_distribution()` — GROUP BY source from raw_telemetry
- `load_per_station_source()` — per-station source breakdown
- `load_advisory_lineage(limit)` — CTE joining alerts to forecasts by station_id + time proximity
- `load_farmer_profiles()` — all farmers from DPI simulator registry
- `load_farmer_profile_detail(phone)` — full DPI detail for one farmer (all 6 services)
- `load_pipeline_stage_stats()` — counts for home page pipeline diagram

Secrets injection: `_inject_cloud_secrets()` copies `st.secrets` → `os.environ` for Streamlit Cloud compatibility.

---

## Daily Scheduler (`src/daily_scheduler.py`)

Singleton APScheduler background thread that runs the full pipeline once daily at 06:00 IST (00:30 UTC).
- Toggle on/off from System → Scheduler tab
- State persists in `scheduler_state.json` — auto-resumes after HF Spaces restarts
- Auto-imported by `app.py` on startup: `import src.daily_scheduler` triggers `if is_enabled(): start()` at module load
- Functions: `start()`, `stop()`, `is_enabled()`, `is_running()`, `next_run_time()`

---

## Dagster Orchestration (`dagster_pipeline/`)

Alternative to `run_pipeline.py` — same 6 steps as Dagster assets:
- `assets/`: `ingest.py`, `heal.py`, `forecast.py`, `downscale.py`, `translate.py`, `deliver.py`
- `resources.py`: Dagster resources for API clients
- `io_manager.py`: DuckDB I/O manager
- `schedules.py`, `sensors.py`, `hooks.py`, `checks.py` (asset quality checks)
- Launch: `dagster dev -m dagster_pipeline`

---

## Testing & Evaluation

### Unit Tests (`tests/`)
- `test_pipeline_stages.py` — unit tests for ingestion, healing, forecasting, downscaling, advisory
- `test_database.py` — DuckDB CRUD tests
- `test_dpi.py` — DPI agent + services tests
- `test_conversation.py` — conversation agent tests
- `test_models.py` — Pydantic model validation tests
- `conftest.py` — shared fixtures (sample_station, fault_config, etc.)

### Offline Evaluations (`tests/eval_*.py`)
- `eval_healing.py` — Level 1A: detection precision/recall, imputation accuracy
- `eval_forecast.py` — Level 1B: MOS correction accuracy
- `eval_advisory.py` — Level 2: advisory quality scoring
- `eval_translation.py` — Level 3: translation quality
- `eval_rag.py` — RAG retrieval quality (precision@k, relevance)
- `eval_dpi.py` — DPI agent integration eval
- `eval_conversation.py` — Conversation agent integration eval

Results stored as JSON in `tests/eval_results/` and displayed in System → Eval Metrics tab.

---

## HuggingFace Spaces Deployment

HF Spaces free tier: 16 GB RAM — enough for sentence-transformers + FAISS.

**Dockerfile:**
```dockerfile
FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8501
CMD ["streamlit", "run", "streamlit_app/app.py", "--server.port=8501", "--server.address=0.0.0.0", "--server.headless=true"]
```

**README.md** (HF Spaces frontmatter):
```yaml
---
title: Weather AI 2 Kerala Tamil Nadu
sdk: docker
app_port: 8501
pinned: false
license: mit
---
```

**Secrets**: Add `ANTHROPIC_API_KEY` and `TOMORROW_IO_API_KEY` in Space Settings → Variables and Secrets. They are injected as plain env vars into the Docker container.

**`.gitignore`** must exclude:
- `.streamlit/secrets.toml`
- `*.duckdb.wal`
- `__pycache__/`, `*.py[cod]`

**Committed artifacts:** `weather.duckdb` (pre-populated data), `models/faiss_index/` (180 KB pre-built index), `scheduler_state.json`.

---

## Project Structure

```
weather AI 2/
├── CLAUDE.md                  # Architecture reference
├── BUILD_PROMPT.md            # This file — one-shot rebuild guide
├── config.py                  # 20 StationConfig + PipelineConfig dataclasses
├── run_pipeline.py            # Main entry point (--source imd|synthetic)
├── run_chat.py                # NL agent CLI
├── run_monitor.py             # Station health monitor
├── trace_pipeline.py          # Step-by-step pipeline demo
├── requirements.txt
├── pyproject.toml
├── Dockerfile
├── dvc.yaml                   # DVC pipeline: export_training_data → train_mos
├── scheduler_state.json       # Daily scheduler persist (auto-generated)
├── .env                       # API keys (never commit)
├── .streamlit/
│   ├── config.toml            # Theme + server config
│   └── secrets.toml           # API keys for Streamlit Cloud (never commit)
├── src/
│   ├── pipeline.py            # WeatherPipeline orchestrator (6-step linear async)
│   ├── database/              # DuckDB lakehouse (15 tables)
│   │   ├── __init__.py        # DDL, init_db(), re-exports
│   │   ├── telemetry.py       # raw/clean telemetry CRUD + paired join
│   │   ├── forecasts.py       # forecast CRUD + actuals join
│   │   ├── alerts.py          # agricultural_alerts CRUD
│   │   ├── delivery.py        # delivery_log + delivery_metrics CRUD
│   │   ├── pipeline_runs.py   # start/finish pipeline run
│   │   ├── conversation.py    # conversation_log CRUD
│   │   └── health.py          # station health aggregation
│   ├── models.py              # Pydantic v2 data contracts
│   ├── healing.py             # HealingAgent (Claude Sonnet tool-use, 5 tools, 24-entry seasonal context) + RuleBasedFallback
│   ├── ingestion.py           # IMD scraper + imdlib gridded + synthetic fallback
│   ├── weather_clients.py     # IMDClient (JSON API), TomorrowIOClient, OpenMeteoClient, NASAPowerClient, ImdlibClient
│   ├── forecasting.py         # HybridNWPModel: NWP + XGBoost MOS + persistence fallback
│   ├── downscaling/
│   │   ├── __init__.py        # IDWDownscaler
│   │   ├── interpolation.py   # haversine, IDW, lapse-rate math
│   │   └── grid_fetcher.py    # NASA POWER grid retrieval
│   ├── translation/
│   │   ├── __init__.py        # Provider factory + async dispatch
│   │   ├── rag_provider.py    # FAISS+BM25 hybrid search → Claude
│   │   ├── local_provider.py  # Rule-based fallback (no API)
│   │   ├── claude_provider.py # Claude-only provider
│   │   ├── curated_advisories.py  # 17 crops × 10 conditions matrix
│   │   ├── rag_index_builder.py   # Build FAISS + BM25 index
│   │   └── ag_corpus.json     # ~6,000 agriculture texts (pre-extracted)
│   ├── delivery/
│   │   ├── __init__.py        # MultiChannelDelivery
│   │   ├── console_provider.py
│   │   ├── twilio_provider.py
│   │   └── whatsapp_provider.py
│   ├── nl_agent/
│   │   └── __init__.py        # NLAgent: Claude tool-use (5 tools)
│   ├── conversation/
│   │   ├── __init__.py        # ConversationalAgent
│   │   ├── state_machine.py   # onboarding → active → follow-up
│   │   ├── language.py        # Language detection
│   │   ├── prompts.py         # System prompt builder
│   │   ├── tools.py           # 6 conversation tools
│   │   ├── memory.py          # Per-farmer memory extraction
│   │   └── followup.py        # Proactive follow-up scheduling
│   ├── dpi/
│   │   ├── __init__.py        # DPIAgent: 6-service profile assembly
│   │   ├── models.py          # AadhaarProfile, LandRecord, SoilHealthCard, etc.
│   │   ├── simulator.py       # SimulatedDPIRegistry: 40+ farmers
│   │   └── services.py        # DPIService protocol + SimulatedDPIService
│   ├── daily_scheduler.py     # APScheduler singleton (06:00 IST daily)
│   ├── architecture.py        # Mermaid diagram + get_pipeline_stages()
│   ├── event_bus.py           # File-based pub/sub
│   ├── quality_checks.py      # Post-pipeline data quality checks
│   ├── health.py              # FastAPI /health endpoint
│   ├── webhook_receiver.py    # FastAPI webhook receiver
│   ├── scheduler.py           # APScheduler scheduling utilities
│   └── monitor.py             # Station health monitor
├── dagster_pipeline/
│   ├── __init__.py            # Dagster definitions
│   ├── resources.py, io_manager.py, schedules.py, sensors.py, hooks.py, checks.py
│   └── assets/                # ingest, heal, forecast, downscale, translate, deliver
├── scripts/
│   ├── batch_pipeline.py      # Multi-run batch execution
│   ├── export_training_data.py # DVC stage: DuckDB → Parquet
│   └── train_mos.py           # DVC stage: Parquet → XGBoost model
├── streamlit_app/
│   ├── app.py                 # Home: pipeline diagram, stats, manual run
│   ├── data_helpers.py        # DB queries (@st.cache_data) + secrets injection
│   ├── style.py               # CSS + STATUS_COLOR + CONDITION_COLOR/EMOJI
│   ├── chat_widget.py         # Sidebar chat toggle (farmer ID, agent dispatch)
│   └── pages/
│       ├── 1_Data.py          # Ingest+Heal (4 tabs)
│       ├── 2_Forecasts.py     # Forecast+Downscale (3 tabs)
│       ├── 3_Advisories.py    # Translate+Deliver (4 tabs)
│       └── _System.py       # System/ops (8 tabs, hidden from sidebar)
├── tests/
│   ├── conftest.py, test_*.py # Unit tests
│   ├── eval_*.py              # Offline evaluations
│   └── eval_results/          # JSON evaluation results
└── models/
    ├── hybrid_mos.json        # Trained XGBoost model
    └── faiss_index/           # Pre-built FAISS + BM25 index
```

---

## Key Gotchas

1. **IMD API sentinel value 999**: IMD returns 999 for missing data (e.g., 999% humidity). Always filter with `_safe_float()` that returns None for values ≥ 999.
2. **IMD HTTPS with broken cert**: Use `verify=False` in httpx client for IMD API calls. The cert chain is incomplete but the endpoint works over HTTPS.
3. **API key trailing newline**: HF Spaces injects secrets with `\n`. Always `.strip()` env vars before use.
4. **Tomorrow.io rate limit**: 3 req/sec, 500 calls/day free tier. Batch calls in groups of 3 with `asyncio.sleep(1.0)` between batches.
5. **Mermaid in Streamlit**: Must use `components.html()` with Mermaid CDN JS. `st.markdown("```mermaid...")` only renders a code block.
6. **Map tiles**: CARTO Positron is free (`https://basemaps.cartocdn.com/gl/positron-gl-style/style.json`). Mapbox requires a token and silently fails without one.
7. **FAISS index first-run time**: ~3 minutes to embed 6,000 texts on CPU. Pre-build and commit `models/faiss_index/` (180 KB) for instant startup.
8. **Streamlit tabs**: All tab content renders on page load, not lazily. Data loading happens even for hidden tabs.
9. **DuckDB connection safety**: Always use context manager (`with _db() as conn:`) to ensure `conn.close()` in finally block.
10. **HF Spaces SDK**: Must use `sdk: docker` in README frontmatter, not `sdk: streamlit` (native Streamlit SDK no longer offered).
11. **`ca-certificates`** in Dockerfile: Required in `python:3.11-slim` for TLS connections to `api.anthropic.com`.
12. **Scheduler state persistence**: `scheduler_state.json` must survive container restarts. Commit it to the repo so it persists across deploys.
13. **Anthropic credit exhaustion**: When credits are low, Step 5 automatically falls back to rule-based advisories for all stations — expected behavior, not an error.
