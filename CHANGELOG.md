# Changelog

All notable changes to the Weather AI Pipeline will be documented in this file.

## [1.2.0] - 2025-05-01

### Added
- GenCast 1.0° probabilistic rainfall ensemble (20-member) with quantiles and exceedance probabilities
- Vercel serverless API functions for frontend — pipeline Space can now sleep between runs while frontend stays always-on
- Neon PostgreSQL persistence layer with rich JSONB columns
- NeuralGCM 2.8° fallback for systems without GraphCast dependencies
- GFS real-time initialization (0.25° NOAA data) alternative to ERA5 reanalysis

### Changed
- Migrated from always-on API Space to weekly-triggered runner + serverless backend
- Replaced XGBoost MOS with GenCast ensemble probability outputs
- Improved healing agent quality scoring (only penalizes missing comparisons, not expected NULL fills)
- Timezone handling now region-configurable (was hardcoded to IST)

### Removed
- Always-on API Space (`jtlevine/ai-weather-pipeline`)
- XGBoost MOS retrain loop (superseded by GenCast ensemble)

---

## [1.1.0] - 2025-03-15

### Added
- NeuralGCM integration as primary forecast model (with GraphCast fallback)
- XGBoost MOS bias correction on NWP output
- Healing agent with Claude tool-use (5 tools: station metadata, historical normals, cross-validation, neighbors, seasonal context)
- FAISS + BM25 hybrid RAG for crop-specific advisories
- Multi-language support (Tamil, Malayalam) via Claude translation
- DPI (Digital Public Infrastructure) agent for farmer profile assembly
- Conversation engine with stateful chat and proactive follow-up

### Changed
- Architecture refactored into 6-step pipeline (Ingest → Heal → Forecast → Downscale → Translate → Deliver)
- Database schema expanded to 17 tables
- Streamlit dashboard redesigned with per-stage pages

---

## [1.0.0] - 2025-01-20

### Added
- Initial Weather AI pipeline for Kerala and Tamil Nadu
- Support for 20 stations (10 per state) with verified IMD SYNOP IDs
- IMD scraper + imdlib gridded backup for real weather data
- GraphCast 0.25° neural weather forecasting
- NASA POWER satellite downscaling
- Claude-powered advisory generation
- SMS delivery via Twilio
- PostgreSQL database with 17-table schema
- Streamlit dashboard with 4 main pages (Data, Forecasts, Advisories, System)
- FastAPI REST API for integration
- DVC model versioning and training pipeline
- Comprehensive test suite

---

## [0.1.0] - 2024-11-15

### Added
- Initial proof-of-concept with synthetic data
- Basic pipeline orchestration
- Preliminary Streamlit interface
