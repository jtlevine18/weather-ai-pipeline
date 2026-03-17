---
title: Weather AI 2 Kerala Tamil Nadu
emoji: 🌾
colorFrom: yellow
colorTo: green
sdk: docker
app_port: 8501
pinned: false
license: mit
---

# Weather AI 2 — Kerala & Tamil Nadu Farming Pipeline

AI-powered weather forecasting for smallholder farmers in Kerala and Tamil Nadu.

## Features
- **6-step pipeline**: Ingest → Heal → Forecast (MOS) → Downscale → Translate → Deliver
- **Bilingual advisories**: Tamil and Malayalam via RAG + Claude
- **Hover-to-translate**: Local language shown by default, English on hover
- **Interactive dashboard**: Station map, forecasts, advisories, NL chat agent

## Setup
Add the following secrets in Space Settings → Variables and Secrets:
- `ANTHROPIC_API_KEY`
- `TOMORROW_IO_API_KEY`

Data is pre-populated — the dashboard loads immediately with no pipeline run needed.

See [CLAUDE.md](CLAUDE.md) for full architecture documentation.
