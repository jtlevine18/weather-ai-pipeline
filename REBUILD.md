# Rebuild This Pipeline for Your Region

Fork the repo, open [Claude Code](https://claude.ai/code), fill in the bracketed parts in the prompt below, and paste it. Claude Code will adapt the entire pipeline — stations, data ingestion, farmer profiles, crop advisories, seasonal climate context, and dashboard — for your geography.

## Prerequisites

1. **API Keys** — `ANTHROPIC_API_KEY` ([console.anthropic.com](https://console.anthropic.com/)), `TOMORROW_IO_API_KEY` ([tomorrow.io](https://app.tomorrow.io/signup), free 500 calls/day)
2. **PostgreSQL** — [Neon](https://neon.tech) free tier (serverless, no credit card). Set `DATABASE_URL` in `.env`
3. **Python 3.11+**

## The Prompt

```text
I forked https://github.com/jtlevine18/weather-ai-pipeline — an AI weather forecasting
and crop advisory pipeline. I want to adapt it for my region. Read CLAUDE.md to understand
the full architecture, then make all the changes below.

=== MY REGION ===

Region name: [e.g. "Central Mexico", "East Africa", "Northern France"]
States/provinces: [e.g. "Jalisco, Michoacán, Guanajuato"]
Timezone: [e.g. "America/Mexico_City", "Africa/Nairobi", "Europe/Paris"]
Language(s) for advisories: [e.g. "es" for Spanish, "sw" for Swahili, "fr" for French]
Currency symbol: [e.g. "$", "KSh", "€"]
Locale code: [e.g. "es-MX", "en-KE", "fr-FR"]

=== MY STATIONS (5-20) ===

1. [City], lat: [XX.XX], lon: [XX.XX], altitude: [XXm], state/province: [Name], crops: [crop1, crop2, crop3]
2. [City], lat: [XX.XX], lon: [XX.XX], altitude: [XXm], state/province: [Name], crops: [crop1, crop2, crop3]
... (add more)

=== MY DATA SOURCE ===

[Describe your weather data source. Options:
- "I have my own API at [endpoint] that returns [format]"
- "I have CSV files with columns [list columns]"
- "Use Open-Meteo current conditions (free, global, no API key)"
- "I want to use [NOAA / Bureau of Meteorology / ECMWF / other]"
- "I'll use synthetic data for now, just set up the pipeline structure"]

=== WHAT TO CHANGE ===

Make ALL of the following changes. This is a 6-step weather pipeline that ingests station
data, heals anomalies, generates forecasts, downscales to farmer GPS, produces crop
advisories, and delivers via SMS. The reference implementation is for Southern India
(Kerala & Tamil Nadu). You are adapting it for my region.

--- 1. STATIONS (config layer) ---

Generate stations.json in the project root with my stations. Format:
[
  {
    "station_id": "[XX_CCC]",  // 2-letter region prefix + 3-letter city code
    "name": "[City Name]",
    "lat": [XX.XXXX],
    "lon": [XX.XXXX],
    "altitude_m": [X],
    "state": "[State/Province]",
    "crop_context": "[crop1, crop2, crop3]",
    "language": "[ISO 639-1 code]",
    "imd_id": ""               // leave empty for non-India deployments
  }
]

Update the _HARDCODED_STATIONS list in config.py to match (this is the fallback if
stations.json is missing).

Copy `.env.example` to `.env` and set:
  REGION_NAME=[my region name]
  TIMEZONE=[my timezone]

--- 2. DATA INGESTION (src/ingestion.py) ---

Write a custom async ingestion function for my data source. The function signature is:

  async def my_fetch(station: StationConfig) -> dict:
      return {
          "temperature": float,   # °C
          "humidity": float,      # %
          "wind_speed": float,    # km/h
          "pressure": float,      # hPa
          "rainfall": float,      # mm
      }

Register it at runtime where `PipelineConfig` is instantiated (see `run_pipeline.py`,
which already does `config = get_config(); config.weather.ingestion_source = args.source`).
Add an import for your new `my_fetch` function and assign both fields on the config
instance before calling `WeatherPipeline(config, ...)`:

  from src.ingestion import my_fetch  # or wherever you defined it
  config = get_config()
  config.weather.ingestion_source = "custom"
  config.weather.custom_ingest_fn = my_fetch

The custom ingestion path in ingest_all_stations() will call this function for each
station, wrap the result in the standard raw_telemetry record format, and insert into
the database.

If using Open-Meteo: write a function that calls the Open-Meteo current weather API
(https://api.open-meteo.com/v1/forecast with current=true) for each station's lat/lon.

Update the _baseline() function docstring to note it is region-specific (used only for
synthetic fallback). If my region has very different climate zones than Kerala/Tamil Nadu,
update the altitude thresholds and base temperatures to match my region.

--- 3. FARMER PROFILES (src/dpi/simulator.py) ---

Generate farmers.json in the project root with realistic demo profiles for my stations:
{
  "[station_id]": {
    "district": "[Local district name]",
    "state": "[State/Province]",
    "lang": "[ISO 639-1]",
    "crops": ["crop1", "crop2", "crop3"],
    "soil": ["soil_type1", "soil_type2"],
    "irrigation": ["irrigation_type1", "irrigation_type2"],
    "area": [min_hectares, max_hectares],
    "pH": [min_pH, max_pH],
    "names": [["Full Name", "Name in local script"], ["Full Name 2", "Local 2"]],
    "count": 2
  }
}

Use realistic names, crops, soil types, and farm sizes for my region. Include at least
2 names per station with both Latin script and local script versions. The simulator
loads this file automatically and generates complete farmer profiles with identity,
land records, soil health, subsidy, insurance, and credit data.

--- 4. CROP ADVISORIES (src/translation/curated_advisories.py) ---

Replace the entire ADVISORY_MATRIX dict with crop-specific advisories for MY region's
crops and weather conditions. The structure is:

ADVISORY_MATRIX = {
    "heavy_rain": {
        "crop_name": "Detailed advisory text with specific agronomic guidance...",
        "default": "Generic heavy rain advisory...",
    },
    "moderate_rain": { ... },
    "heat_stress": { ... },
    "drought_risk": { ... },
    "frost_risk": { ... },
    "high_wind": { ... },
    "foggy": { ... },
    "clear": { ... },
    "cyclone_risk": { ... },
}

Each advisory should be 2-4 sentences with specific, actionable farming guidance:
pest/disease risks, irrigation adjustments, harvest timing, fertilizer recommendations.
Write advisories for every crop listed in my stations' crop_context fields. These are
the fallback when the Claude RAG provider is unavailable.

--- 5. SEASONAL CONTEXT (src/healing.py) ---

Replace the SEASONAL_CONTEXT dict (currently 24 entries for Kerala × 12 months +
Tamil Nadu × 12 months) with entries for my region. Format:

SEASONAL_CONTEXT = {
    ("[State/Province]", month_number): {
        "season": "[season name]",
        "weather": "[typical weather description with temp ranges, rainfall amounts]",
        "crops": "[what's growing/being planted/harvested this month]",
    },
    ...
}

Create entries for each of my states/provinces × 12 months. This context is used by the
Claude healing agent to validate whether readings are plausible for the season.

Also update the SYSTEM_PROMPT_TEMPLATE at the top of the file to reference my region
instead of "Kerala and Tamil Nadu" / "IMD stations".

--- 6. DASHBOARD (frontend/src/regionConfig.ts) ---

Replace the entire REGION object with my region's values:

export const REGION = {
  name: '[My Region Name]',
  states: ['[State1]', '[State2]'],
  languages: { [lang_code]: '[Language Name]' } as Record<string, string>,
  get languageList() { return Object.values(this.languages).join(' and ') },
  get languageMetric() { return Object.values(this.languages).join(' / ') },
  dataSource: '[My Data Source Name]',
  sourceLabels: {
    [source_key]: ['[Source Display Name]', '#2E7D32'],
    open_meteo: ['Open-Meteo', '#1565C0'],
    synthetic: ['Synthetic', '#888'],
    custom: ['Custom', '#6B5B95'],
  } as Record<string, [string, string]>,
  locale: '[locale-code]',
  currency: '[symbol]',
  timezoneLabel: '[TZ abbreviation]',
  sidebarFooter: '[State1 · State2]',
  farmerServices: {
    pmkisan: '[Income support program name]',
    pmfby: '[Crop insurance program name]',
    kcc: '[Farm credit program name]',
    soil: '[Soil testing program name]',
  },
}

The sourceLabels keys must match the "source" field your ingestion function writes.
The farmerServices keys (pmkisan, pmfby, kcc, soil) are referenced by React components —
keep the keys, change only the display labels.

--- 7. DOCUMENTATION ---

Update CLAUDE.md:
- Change the project title and vision to reference my region
- Replace the station list with my stations
- Update the Architecture section to reference my data source instead of IMD
- Update language references

--- 8. VERIFICATION ---

After making all changes, run these commands and confirm they pass:

python -c "from config import STATIONS; print(f'{len(STATIONS)} stations loaded'); [print(f'  {s.station_id}: {s.name}') for s in STATIONS]"

python -c "from src.dpi.simulator import get_registry; r = get_registry(); print(f'{r.farmer_count} farmers'); [print(f'  {f[\"name\"]} — {f[\"district\"]}') for f in r.list_farmers()[:5]]"

python run_pipeline.py

If the pipeline run fails, debug and fix the issue. Common problems:
- Database not set up: check DATABASE_URL in .env
- API key missing: check ANTHROPIC_API_KEY and TOMORROW_IO_API_KEY
- Custom ingestion function errors: check the function returns all 5 fields
- Import errors: check the custom_ingest_fn is properly imported in config.py

=== WHAT NOT TO CHANGE ===

These components are globally portable and should work without modification:
- src/forecasting.py — NeuralGCM + XGBoost MOS (timezone is already configurable)
- src/weather_clients.py — OpenMeteo, NASA POWER, Tomorrow.io clients
- src/downscaling/ — IDW + lapse-rate math (universal)
- src/translation/rag_provider.py — FAISS+BM25 RAG (language-agnostic)
- src/translation/claude_provider.py — Claude advisory generation
- src/delivery/ — Console/Twilio/WhatsApp delivery
- src/database/ — All 17 PostgreSQL tables (geography-neutral schemas)
- src/pipeline.py — Pipeline orchestrator
- src/models.py — Pydantic data contracts
- src/api.py, src/auth.py — FastAPI REST API + JWT auth
- dagster_pipeline/ — Dagster orchestration
- tests/ — Test structure (update fixtures if needed)
```

## After the Prompt

Once Claude Code finishes, you should have:
- `stations.json` with your stations
- `farmers.json` with demo farmer profiles
- `.env` with your region name and timezone
- Custom ingestion wired up for your data source
- Crop advisories for your region's crops
- Seasonal climate context for your states
- Dashboard displaying your region's names and languages
- A working pipeline confirmed by `python run_pipeline.py`

## Data Source Reference

| Source | Coverage | Auth | Notes |
|--------|----------|------|-------|
| Open-Meteo | Global | None | Free, best default for non-India regions |
| NOAA ISD/CDO | US + global | API key (free) | Integrated Surface Data, hourly |
| Bureau of Meteorology | Australia | API key | Australian weather stations |
| ECMWF Open Data | Global | None | Medium-range forecasts |
| Copernicus CDS | Global | API key (free) | ERA5 reanalysis + more |
| Your own API/CSV | Your region | Varies | Write a custom fetch function |
