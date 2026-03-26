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

# AI Weather Pipeline for Southern India

> Live ML-powered weather forecasting and farming advisory system for 20 stations across Kerala and Tamil Nadu.

**[Live Demo →](https://jtlevine-ai-weather-pipeline.hf.space)** | **[How It Works →](#how-it-works)**

## What This Does

An end-to-end weather intelligence pipeline that:
- Scrapes real weather data from India's Meteorological Department (20 stations)
- Heals anomalies using a Claude AI agent with 5 specialized tools
- Generates 7-day forecasts via NeuralGCM (Google DeepMind's neural weather model) + XGBoost bias correction
- Downscales to farmer GPS coordinates using NASA satellite data
- Produces crop-specific advisories in Tamil and Malayalam via RAG + Claude
- Delivers via SMS

The pipeline runs weekly, costs ~$3/month, and degrades gracefully — every component has a zero-cost fallback.

## Architecture

```
IMD Scraper + imdlib  → Ingest    (real station data, 3-level fallback)
Tomorrow.io           → Heal      (AI agent cross-validation)
NeuralGCM / Open-Meteo → Forecast (neural weather model on GPU)
NASA POWER            → Downscale (satellite → farmer GPS)
Claude + RAG          → Translate (bilingual advisories)
Twilio SMS            → Deliver   (console dry-run)
```

## Tech Stack

| Component | Technology | Role |
|-----------|-----------|------|
| NWP Model | NeuralGCM (JAX/GPU) | 7-day global weather forecasts |
| ML Correction | XGBoost | MOS bias correction on NWP output |
| AI Healing | Claude Sonnet (tool-use) | Agentic data quality repair |
| Advisory Gen | Claude + FAISS/BM25 RAG | Bilingual crop-specific advice |
| Downscaling | NASA POWER + IDW | Satellite grid → farmer GPS |
| Database | PostgreSQL (Neon) | Production data store |
| Frontend | React + Tailwind | Portfolio dashboard |
| Dashboard | Streamlit | Operator view |
| API | FastAPI | REST endpoints |
| Scheduling | GitHub Actions | Weekly pipeline trigger |
| Orchestration | Dagster (optional) | DAG-based pipeline |

## Run Locally

```bash
pip install -r requirements.txt
cp .env.example .env  # add API keys
python run_pipeline.py
streamlit run streamlit_app/app.py
```

## Adapt for Your Location

This pipeline works globally — only the station config is region-specific. See [REBUILD.md](REBUILD.md) for a Claude Code prompt that adapts it to any region.

## Cost

~$3/month: Claude API ($1.08) + GPU compute ($0.80) + domain ($1.00). Everything else is free tier.

## License

MIT
