# One-Shot Build Prompt: Weather AI 2 — Kerala & Tamil Nadu Farming Pipeline

Build a complete AI-powered weather forecasting pipeline for smallholder farmers in Kerala and Tamil Nadu, deployed on HuggingFace Spaces via Docker. The app is a 6-step data pipeline with a Streamlit dashboard, bilingual advisories (Tamil/Malayalam), and an NL chat agent.

---

## Stack & APIs

- **Python 3.11**, DuckDB (embedded lakehouse), Streamlit + pydeck dashboard
- **anthropic** (Claude claude-sonnet-4-6) — advisory generation + translation + NL chat
- **faiss-cpu** + **sentence-transformers** (BAAI/bge-base-en-v1.5) + **rank-bm25** — hybrid RAG
- **xgboost** + **scikit-learn** — MOS forecast correction
- **httpx** — async HTTP for all weather APIs
- **apscheduler** — scheduled pipeline runs
- **langchain-huggingface** — embedding wrapper
- No `datasets` package — corpus is pre-extracted to a local JSON file

API keys needed: `ANTHROPIC_API_KEY`, `TOMORROW_IO_API_KEY`. NASA POWER and Open-Meteo are free, no key needed.

---

## The 6-Step Pipeline

Each step fails independently — never cascades. Every step has a fallback.

### Step 1: Ingest
Generate synthetic sensor readings for 20 stations (10 Kerala, 10 Tamil Nadu). Inject faults at ~5% rate: `typo`, `drift`, `offline`, `missing`. Store in `raw_telemetry` DuckDB table.

### Step 2: Heal
Fetch real weather from Tomorrow.io for all 20 stations in **batches of 3 with 1-second sleep between batches** (rate limit: 3 req/sec, 500 calls/day free tier). Cross-validate each synthetic reading against the real reference. Use rule-based imputation for anomalies. Fall back to NASA POWER if Tomorrow.io fails. Store in `clean_telemetry` with `quality_score` and `heal_action` columns.

### Step 3: Forecast (MOS)
Get NWP baseline from Open-Meteo (GFS/ECMWF). Train XGBoost on residual between NWP and observations — 12 features: `nwp_temp`, `nwp_rainfall`, `humidity`, `wind_speed`, `pressure`, `station_altitude`, `soil_moisture`, `rolling_6h_error`, `recent_temp_trend`, `hour_sin`, `hour_cos`, `doy_sin`. Final forecast = NWP + XGBoost correction. Fall back to persistence model if XGBoost not trained. Store in `forecasts`.

### Step 4: Downscale
Query NASA POWER for a 5×5 grid (~0.5° radius) around each station. Use IDW (Inverse Distance Weighting) interpolation to the farmer's GPS coordinates. Apply lapse-rate elevation correction (6.5°C per 1000m). Re-classify weather condition at farmer scale. Update `forecasts` table with `farmer_lat`, `farmer_lon`, `downscaled=True`.

### Step 5: Translate (RAG + Claude)
Three-level fallback chain: **RAGProvider → ClaudeProvider → LocalProvider**

**RAGProvider** (primary):
1. Query reformulation: convert forecast dict to NL search query
2. Hybrid retrieval: FAISS dense (BGE embeddings) + BM25 sparse, α=0.5 blend, threshold=0.35, top-5
3. Claude call #1: English advisory grounded in retrieved docs
4. Claude call #2: translate to Tamil (`ta`) or Malayalam (`ml`)

**ClaudeProvider** (fallback if RAG fails):
- Direct Claude call with forecast context, no FAISS needed
- Parse `ENGLISH: [...]` and `TAMIL:/MALAYALAM: [...]` format

**LocalProvider** (final fallback):
- Rule-based lookup in `curated_advisories.py` matrix (condition → crop → advisory)
- Zero API cost

Store both `advisory_en` and `advisory_local` in `agricultural_alerts`.

### Step 6: Deliver
Console SMS output (Twilio dry-run). Log to `delivery_log`. Track in `pipeline_runs` with per-step status.

---

## RAG Corpus

The FAISS index is built from two sources:
1. **`src/translation/ag_corpus.json`** — 6,000 texts extracted from HF datasets (committed as plain JSON — do NOT use the `datasets` package at runtime, the JSON is the source of truth). Original datasets: `KisanVaani/agriculture-qa-english-only`, `Mahesh2841/agriculture`, `YuvrajSingh9886/agriculture-soil-qa-pairs-dataset` — note these are the **current** HF usernames; the old names (`Rahulp007/KisanVaani` etc.) no longer exist.
2. **`src/translation/curated_advisories.py`** — hand-crafted matrix covering Kerala/Tamil Nadu crops: coconut, rubber, rice/paddy, coffee, cardamom, pepper, tea, banana, arecanut, tapioca, cotton, millets, groundnut, sugarcane, turmeric, vegetables, cashew. Ten conditions: `heavy_rain`, `moderate_rain`, `heat_stress`, `drought_risk`, `cyclone_risk`, `monsoon_onset`, `high_wind`, `foggy`, `clear`, `high_humidity`. Each entry 3-4 sentences with specific chemical names, rates, and timing.

The FAISS index is built at first pipeline run and cached to `models/faiss_index/`. Do NOT commit the `.faiss` binary — HF Spaces rejects binary files. The index rebuilds from `ag_corpus.json` in ~3 minutes on first run, then loads from cache on all subsequent runs.

---

## 20 Stations

**Kerala (10, language=`ml`):** Thiruvananthapuram, Kochi, Kollam, Alappuzha, Kannur, Thrissur, Kottayam, Palakkad, Kozhikode, Wayanad

**Tamil Nadu (10, language=`ta`):** Thanjavur, Madurai, Tiruchirappalli, Dindigul, Salem, Erode, Chennai, Tirunelveli, Coimbatore, Vellore

Each station has: `station_id`, `name`, `lat`, `lon`, `altitude_m`, `state`, `crop_context`, `language`.

---

## Config

All API keys read from `os.getenv()` with `.strip()` — **critical**: HF Spaces secret UI appends `\n` to pasted values; `.strip()` prevents `Illegal header value` errors in httpx.

```python
anthropic_key: str = field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", "").strip())
tomorrow_io_key: str = field(default_factory=lambda: os.getenv("TOMORROW_IO_API_KEY", "").strip())
```

---

## Streamlit Dashboard (5 pages)

Style: Inter font, cream background (`#faf8f5`), dark sidebar (`#1a1a2e`), gold accents (`#d4a019`). Match exactly via `inject_css()` in `style.py`.

- **Homepage (`app.py`)**: forecast table, advisory feed, pipeline trigger button in sidebar
- **1_Network.py**: pydeck map with **CARTO Positron free tiles** (`https://basemaps.cartocdn.com/gl/positron-gl-style/style.json`) — do NOT use Mapbox (requires token). Station health tab, data quality tab.
- **2_Forecasts.py**: two tabs — Station Forecasts (HTML table grouped by state) and Model Performance
- **3_Advisories.py**: full-width advisory feed with hover-to-English CSS overlay (local language default, English on hover — pure CSS, no JS). No condition/provider distribution charts.
- **4_Chat.py**: NL agent chat with greeting message on load, quick prompts in sidebar
- **5_System.py**: Mermaid architecture diagram rendered via `streamlit.components.v1.html()` with Mermaid CDN JS — **not** `st.markdown("```mermaid...")` which only renders a code block

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

**Secrets**: Add `ANTHROPIC_API_KEY` and `TOMORROW_IO_API_KEY` in Space Settings → Variables and Secrets. They are injected as plain env vars into the Docker container — `os.getenv()` reads them directly, no `st.secrets` needed.

**`.gitignore`** must exclude:
- `.streamlit/secrets.toml`
- `*.duckdb`, `*.duckdb.wal`
- `models/faiss_index/` (binary — HF rejects `.faiss` files)
- `__pycache__/`, `*.py[cod]`

**Git push**: HF Spaces uses `main` branch. Push with:
```bash
git push origin master:main
```

If git history contains binary files (`.duckdb`, `.faiss`), HF will reject the push even after `git rm --cached`. Only fix is a clean orphan branch:
```bash
git checkout --orphan fresh
git add -A
git commit -m "Initial commit"
git push origin fresh:main --force
```

**Factory reboot vs restart**: Factory reboot rebuilds the Docker image (needed when `Dockerfile` or `requirements.txt` change). Regular restart suffices for code-only changes. New secrets take effect on regular restart — no factory reboot needed.

---

## Key Gotchas

1. **API key trailing newline**: HF Spaces injects secrets with `\n`. Always `.strip()` env vars before use.
2. **FAISS binary rejection**: HF rejects `.faiss` files. Build index at runtime from committed JSON corpus.
3. **Tomorrow.io rate limit**: 3 req/sec, 500 calls/day free tier. Batch calls in groups of 3 with `asyncio.sleep(1.0)` between batches.
4. **Mermaid in Streamlit**: Must use `components.html()` with Mermaid CDN JS. `st.markdown("```mermaid...")` only renders a code block.
5. **Map tiles**: CARTO Positron is free. Mapbox requires a token and silently fails without one.
6. **`datasets` package**: 600MB, only needed for downloading from HF Hub. Since corpus is pre-extracted to JSON, remove `datasets` from `requirements.txt`.
7. **FAISS index first-run time**: ~3 minutes to embed 6,000 texts on CPU. Subsequent runs load from cache in seconds.
8. **Git credential in URL**: `https://username:hf_token@huggingface.co/spaces/...` — must be one unbroken line, no line wraps.
9. **`ca-certificates`** in Dockerfile: Required in `python:3.11-slim` for TLS connections to `api.anthropic.com`.
10. **HF no longer offers native Streamlit SDK**: Must use Docker + Streamlit template. `README.md` frontmatter must say `sdk: docker`, not `sdk: streamlit`.
