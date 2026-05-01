# AI Weather Pipeline

[![CI](https://github.com/jtlevine18/weather-ai-pipeline/actions/workflows/ci.yml/badge.svg)](https://github.com/jtlevine18/weather-ai-pipeline/actions)
[![CodeQL](https://github.com/jtlevine18/weather-ai-pipeline/actions/workflows/codeql.yml/badge.svg)](https://github.com/jtlevine18/weather-ai-pipeline/security/code-scanning)
[![Weekly Pipeline](https://github.com/jtlevine18/weather-ai-pipeline/actions/workflows/weekly-pipeline.yml/badge.svg)](https://github.com/jtlevine18/weather-ai-pipeline/actions)
[![MIT License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

ML-powered weather forecasting and crop advisory system for smallholder farmers. Works for any region — ships with a Southern India (Kerala & Tamil Nadu) reference implementation.

**[Live Demo →](https://weather-forecast.jeff-levine.com)** | **[Adapt for Your Region →](REBUILD.md)**

## What This Does

A 6-step weather intelligence pipeline that runs weekly and costs ~$3/month:

1. **Ingests** station-level weather observations (real IMD data, imdlib gridded backup, or your own source)
2. **Heals** anomalies using a Claude AI agent with 5 specialized tools
3. **Forecasts** 7 days via GraphCast (Google DeepMind) + GenCast probabilistic ensemble
4. **Downscales** to farmer GPS coordinates using NASA satellite data
5. **Translates** into crop-specific advisories in any language via RAG + Claude
6. **Delivers** via SMS/WhatsApp

Every component has a zero-cost fallback — system works even if Claude API or GPU is unavailable.

## Prerequisites

- **Python 3.11+**
- **Anthropic API key** (Claude — required for advisories; system falls back to rules if absent)
- **PostgreSQL** — free Neon account recommended ([neon.tech](https://neon.tech))
- **Optional:** GPU for NeuralGCM (falls back to Open-Meteo on CPU)
- **Optional:** Tomorrow.io API key for anomaly detection (or use rule-based fallback)

## Quick Start

```bash
git clone https://github.com/jtlevine18/weather-ai-pipeline
cd weather-ai-pipeline

pip install -r requirements.txt
cp .env.example .env

# In .env, set:
# ANTHROPIC_API_KEY=sk-...
# DATABASE_URL=postgres://user:pass@host/db

# Run the pipeline
python run_pipeline.py

# View the live dashboard (or use https://weather-forecast.jeff-levine.com)
streamlit run streamlit_app/app.py
```

## Architecture

```
Station Data Source  → Ingest    (real IMD, imdlib, or your API)
Tomorrow.io / NASA   → Heal      (AI agent cross-validation)
GraphCast 0.25°      → Forecast  (neural weather model, scalar)
GenCast 1.0°         → Ensemble  (probabilistic rainfall)
NASA POWER           → Downscale (grid → farmer GPS coordinates)
Claude + RAG         → Advise    (crop-specific recommendations)
Twilio / SMS         → Deliver   (to farmers, console dry-run default)
```

**Deployment:**
- **Frontend**: Vercel React SPA (always on) — [weather-forecast.jeff-levine.com](https://weather-forecast.jeff-levine.com)
- **Backend**: HF Spaces pipeline runner (paused between weekly runs)
- **Database**: Neon PostgreSQL (persists data so frontend works when backend sleeps)

## Tech Stack

| Component | Technology | Role |
|-----------|-----------|------|
| Deterministic forecast | GraphCast 0.25° (DeepMind, JAX/A100) | 7-day scalar forecasts (temperature, wind, humidity, rainfall) |
| Probabilistic forecast | GenCast 1.0° (DeepMind, 20-member ensemble) | Rainfall quantiles + exceedance probabilities |
| ML correction | XGBoost | Bias correction on raw NWP output |
| AI agents | Claude Sonnet | Data healing, advisory generation, translation |
| RAG retrieval | FAISS + BM25 | Hybrid semantic + keyword search for crop knowledge |
| Backend | FastAPI + Python 3.11 | REST API + pipeline orchestration |
| Frontend | React 18 + TypeScript | Dashboard + advisor interface |
| Database | PostgreSQL (Neon) | Stores pipeline data + model forecasts |

## What's Global vs Region-Specific

| Component | Global? | Notes |
|-----------|---------|-------|
| GraphCast 0.25° / GenCast 1.0° | ✓ Yes | Works anywhere on Earth |
| NASA POWER | ✓ Yes | Global satellite coverage |
| Claude API | ✓ Yes | Any language |
| XGBoost bias correction | ✓ Yes | Trains on local data automatically |
| FAISS RAG | ✓ Yes | Rebuild index with local crop knowledge |
| **Station definitions** | ✗ No | Replace `stations.json` for your region |
| **IMD ingestion** | ✗ No | India-specific; implement your own data source |
| **Farmer profiles** | ✗ No | Replace `farmers.json` or skip |
| **Crop advisories** | ✗ No | Update crop matrix for your region |
| **Healing context** | ✗ No | Regenerate seasonal climate knowledge for your region |

## API Reference

**FastAPI auto-docs:** Visit `/docs` on the live demo or `http://localhost:7860/docs` locally for interactive API explorer.

Key endpoints:
- `GET /health` — Pipeline health status
- `GET /api/stations` — List configured stations
- `GET /api/forecasts?station_id=...` — Station forecasts (7-day)
- `GET /api/alerts?farmer_id=...` — Personalized crop advisories
- `GET /api/pipeline/status` — Current run status
- `POST /api/pipeline/trigger` — Manually trigger pipeline run

## Troubleshooting

**GraphCast GPU not available**
→ System automatically falls back to NeuralGCM (L4 GPU) or Open-Meteo API (no GPU required).

**Claude API rate limit / key missing**
→ Rule-based fallback generates advisories using curated templates.

**Neon PostgreSQL cold start latency**
→ Expected on first query after wake-up; retry after 30s.

**IMD scraper blocked or no data**
→ imdlib gridded data (T-1 day) kicks in automatically. For a new region, implement your own ingestion in `src/ingestion.py`.

**Weather forecasts look incorrect**
→ GraphCast is initialized from ERA5 reanalysis (5-day lag). Use GFS 0.25° for real-time forecasts (set `NWP_INIT_SOURCE=gfs` in `.env`).

## Fork & Adapt for Your Region

This pipeline is designed to be forked. The 6-step architecture is geography-neutral — only the data layer changes.

See [REBUILD.md](REBUILD.md) for a complete guide and a ready-to-paste Claude Code prompt that adapts the pipeline for your region in one go. You'll need to provide:
- Your stations (`lat/lon/altitude/crops`) → `stations.json`
- Your weather data source (own API, CSV, or Open-Meteo as fallback)
- Optionally: farmer profiles → `farmers.json`

## Cost

~$3/month breakdown:
- Claude API ($1.08) — healing + advisory generation
- HF Spaces GPU compute ($0.80) — weekly pipeline runs
- Domain ($1.00) — `weather-forecast.jeff-levine.com`

Everything else is free tier (Neon, NASA POWER, Vercel serverless, Open-Meteo).

## License

[MIT](LICENSE)

---

**Questions?** Open an issue or see [REBUILD.md](REBUILD.md) for detailed deployment and adaptation guidance.
