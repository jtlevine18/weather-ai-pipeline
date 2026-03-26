# Rebuild This Pipeline for Your Location

This prompt is designed for [Claude Code](https://claude.ai/code). Copy it, open Claude Code in a fork of this repo, and paste it.

## One-Shot Prompt

> I want to adapt this weather pipeline for [YOUR REGION]. Here are my stations:
>
> 1. [City Name], lat: [XX.XX], lon: [XX.XX], altitude: [XXm], crops: [crop1, crop2]
> 2. [City Name], lat: [XX.XX], lon: [XX.XX], altitude: [XXm], crops: [crop1, crop2]
> ... (5-10 stations)
>
> Language for advisories: [language code, e.g. "es" for Spanish, "fr" for French]
> Region name: [e.g. "Central Mexico", "Northern France"]
>
> Please:
> 1. Generate a new `stations.json` with my stations
> 2. Set `ingestion_source` to `"open_meteo"` in config (since I don't have IMD)
> 3. Update the dashboard title and subtitle for my region
> 4. Update CLAUDE.md with the new station list
> 5. Skip the DPI/farmer services (India-specific)
> 6. Test that the pipeline runs with `python run_pipeline.py`

## What Works Globally (no changes needed)
- Open-Meteo weather data (global coverage, free)
- NASA POWER satellite data (global)
- NeuralGCM forecasting (global neural weather model)
- Claude advisory generation (any language)
- XGBoost MOS correction (trains on local data)
- PostgreSQL database, FAISS RAG, full pipeline orchestration

## What's India-Specific (the prompt handles this)
- IMD/imdlib data ingestion → replaced by Open-Meteo
- Tamil/Malayalam translations → replaced by your language
- Kerala/TN crop context → replaced by your crops
- DPI services (Aadhaar, PM-KISAN) → skipped
