---
title: Weather AI 2 Kerala Tamil Nadu
emoji: 🌾
colorFrom: yellow
colorTo: green
sdk: docker
app_port: 7860
pinned: false
license: mit
---

# AI Weather Pipeline

> ML-powered weather forecasting and crop advisory system for smallholder farmers. Works for any region — ships with a Southern India (Kerala & Tamil Nadu) reference implementation.

**[Live Demo →](https://jtlevine-ai-weather-pipeline.hf.space)** | **[Adapt for Your Region →](REBUILD.md)**

## What This Does

A 6-step weather intelligence pipeline that:
- **Ingests** station-level weather observations (bring your own data source, or use the built-in IMD scraper)
- **Heals** anomalies using a Claude AI agent with 5 specialized tools
- **Forecasts** 7 days via NeuralGCM (Google DeepMind) + XGBoost bias correction
- **Downscales** to farmer GPS coordinates using NASA satellite data
- **Translates** into crop-specific advisories in any language via RAG + Claude
- **Delivers** via SMS/WhatsApp

Runs weekly, costs ~$3/month, and degrades gracefully — every component has a zero-cost fallback.

## Fork & Adapt

This pipeline is designed to be forked and adapted for any geography. The core ML infrastructure (NeuralGCM, XGBoost MOS, FAISS RAG, Claude advisory generation) works globally. Only the station config and data source are region-specific.

**See [REBUILD.md](REBUILD.md)** for a Claude Code prompt that adapts the full pipeline to your region in one shot.

**What you provide:**
- Your stations (lat/lon/altitude/crops) → `stations.json`
- Your weather data source (own API, CSV, or Open-Meteo as global fallback)
- Optionally: simulated farmer profiles → `farmers.json`

**What works globally (no changes needed):**
- Open-Meteo weather data, NASA POWER satellite data, NeuralGCM forecasting
- Claude advisory generation (any language), XGBoost MOS correction
- PostgreSQL database, FAISS RAG, full pipeline orchestration

## Architecture

```
Station Data Source  → Ingest    (your API, IMD, or synthetic — pluggable)
Tomorrow.io          → Heal      (AI agent cross-validation)
NeuralGCM / Open-Meteo → Forecast (neural weather model on GPU)
NASA POWER           → Downscale (satellite grid → farmer GPS)
Claude + RAG         → Translate (crop advisories in any language)
Twilio SMS           → Deliver   (console dry-run by default)
```

## Tech Stack

| Component | Technology | Role |
|-----------|-----------|------|
| NWP Model | NeuralGCM (JAX/GPU) | 7-day global weather forecasts |
| ML Correction | XGBoost | MOS bias correction on NWP output |
| AI Healing | Claude Sonnet (tool-use) | Agentic data quality repair |
| Advisory Gen | Claude + FAISS/BM25 RAG | Crop-specific advice in any language |
| Downscaling | NASA POWER + IDW | Satellite grid → farmer GPS |
| Database | PostgreSQL (Neon) | Production data store |
| Frontend | React + Tailwind | Dashboard |
| API | FastAPI | REST endpoints |
| Orchestration | Dagster (optional) | DAG-based pipeline |

## Run Locally

```bash
pip install -r requirements.txt
cp .env.example .env  # add API keys + DATABASE_URL (see Neon free tier)
python run_pipeline.py
```

## What's Global vs Region-Specific

| Component | Global? | Notes |
|-----------|---------|-------|
| NeuralGCM / Open-Meteo | Yes | Works anywhere on Earth |
| NASA POWER | Yes | Global satellite coverage |
| Claude API | Yes | Any language |
| XGBoost MOS | Yes | Trains on local data automatically |
| FAISS RAG | Yes | Rebuild index with local ag corpus |
| Station config | **No** | Replace `stations.json` for your region |
| IMD ingestion | **No** | India-specific; use `custom` ingestion for your data source |
| Farmer profiles | **No** | Replace `farmers.json` or skip |
| Curated advisories | **No** | Replace crop matrix for your region |
| Healing seasonal context | **No** | Regenerate for your climate |

## Cost

~$3/month: Claude API ($1.08) + GPU compute ($0.80) + domain ($1.00). Everything else is free tier.

## License

[MIT](LICENSE)
