# Rebuild This Pipeline for Your Region

This guide helps you adapt this weather pipeline for any geography. The fastest path is the **one-shot Claude Code prompt** below — fork the repo, open [Claude Code](https://claude.ai/code), and paste.

## Prerequisites

1. **API Keys** (see `.env.example`):
   - `ANTHROPIC_API_KEY` — [console.anthropic.com](https://console.anthropic.com/) (pay-per-use, ~$0.27/pipeline run)
   - `TOMORROW_IO_API_KEY` — [tomorrow.io/signup](https://app.tomorrow.io/signup) (free tier: 500 calls/day)

2. **PostgreSQL database**:
   - [Neon](https://neon.tech) free tier works great (serverless, no credit card)
   - Set `DATABASE_URL` in your `.env`

3. **Python 3.11+**

## What You Need to Provide

| What | File | Required? |
|------|------|-----------|
| Your weather stations | `stations.json` | Yes |
| Your weather data source | Custom ingestion function or use Open-Meteo | Yes |
| Your timezone and region name | `.env` or `config.py` | Yes |
| Simulated farmer profiles | `farmers.json` | Optional (for demos) |

### stations.json format

```json
[
  {
    "station_id": "US_NYC",
    "name": "New York City",
    "lat": 40.7128,
    "lon": -74.0060,
    "altitude_m": 10,
    "state": "New York",
    "crop_context": "vegetables, apples, grapes, dairy forage",
    "language": "en",
    "imd_id": ""
  }
]
```

### farmers.json format (optional)

```json
{
  "US_NYC": {
    "district": "Long Island", "state": "New York", "lang": "en",
    "crops": ["vegetables", "apples", "grapes"], "soil": ["sandy loam", "clay"],
    "irrigation": ["drip", "rainfed"], "area": [1.0, 5.0], "pH": [5.5, 7.0],
    "names": [["John Smith", "John Smith"], ["Maria Garcia", "Maria Garcia"]],
    "count": 2
  }
}
```

These are **demo profiles** tied to your stations. In a real deployment, you'd connect actual farmer data instead of simulated profiles.

### frontend/src/regionConfig.ts (dashboard strings)

This single file controls every geography-specific string in the dashboard. Here's what it looks like adapted for Central Mexico:

```typescript
export const REGION = {
  name: 'Central Mexico',
  states: ['Jalisco', 'Michoacán', 'Guanajuato'],
  languages: { es: 'Spanish' } as Record<string, string>,
  get languageList() { return Object.values(this.languages).join(' and ') },
  get languageMetric() { return Object.values(this.languages).join(' / ') },

  dataSource: 'CONAGUA',           // your met service name (shown in descriptions)
  sourceLabels: {                   // badge labels for data source types in the UI
    conagua: ['CONAGUA', '#2E7D32'],
    open_meteo: ['Open-Meteo', '#1565C0'],
    synthetic: ['Synthetic', '#888'],
    custom: ['Custom', '#6B5B95'],
  } as Record<string, [string, string]>,

  locale: 'es-MX',                 // date/number formatting
  currency: '$',                    // currency symbol for financial displays
  timezoneLabel: 'CST',            // shown in scheduler description

  sidebarFooter: 'Jalisco \u00B7 Michoacán \u00B7 Guanajuato',

  farmerServices: {                 // labels for the farmer profile cards
    pmkisan: 'PROCAMPO',           // income support program
    pmfby: 'Crop Insurance',       // crop insurance
    kcc: 'Farm Credit',            // credit facility
    soil: 'Soil Health Card',      // soil testing
  },
}
```

The keys in `sourceLabels` should match the `source` field your ingestion function writes to `raw_telemetry`. The keys in `farmerServices` (`pmkisan`, `pmfby`, `kcc`, `soil`) are used by the React components to look up card titles — keep the same keys, just change the display labels.

## One-Shot Claude Code Prompt

Fork the repo, open Claude Code, and paste this (fill in the bracketed parts):

```text
I want to adapt this weather pipeline for [YOUR REGION]. Here are my stations:

1. [City], lat: [XX.XX], lon: [XX.XX], altitude: [XXm], crops: [crop1, crop2]
2. [City], lat: [XX.XX], lon: [XX.XX], altitude: [XXm], crops: [crop1, crop2]
... (5-20 stations)

Region name: [e.g. "Central Mexico", "Northern France", "East Africa"]
Timezone: [e.g. "America/Mexico_City", "Europe/Paris", "Africa/Nairobi"]
Language for advisories: [e.g. "es", "fr", "sw"]

My data source: [describe your weather data — see "Data source options" in REBUILD.md]

Please:
1. Generate stations.json with my stations
2. Generate farmers.json with realistic demo farmer profiles for my region
3. Set REGION_NAME and TIMEZONE in .env
4. Configure ingestion for my data source
5. Update src/translation/curated_advisories.py with crop advisories for my region's crops and weather conditions
6. Update src/healing.py SEASONAL_CONTEXT with my region's seasonal weather patterns
7. Update frontend/src/regionConfig.ts with my region name, states, languages, locale, currency, and data source label
8. Update CLAUDE.md with the new station list and region info
9. Test with python run_pipeline.py
```

### Data source options

Tell Claude Code which applies to you:

**"I have my own weather API"** — Provide the API endpoint and response format. Claude Code will write a custom ingestion function and set `ingestion_source: "custom"`.

**"I have CSV/database weather data"** — Describe the schema. Claude Code will write a loader function.

**"I just want to use Open-Meteo (global, free)"** — Claude Code will write an Open-Meteo-based ingestion function that fetches current conditions for your stations. No API key needed.

**"I have [specific service] data"** (NOAA, Bureau of Meteorology, ECMWF, etc.) — Describe the service. Claude Code will write the appropriate client.

## What Works Globally (no changes needed)

- **Open-Meteo** weather forecasts (global coverage, free, no key)
- **NASA POWER** satellite data (global coverage, free)
- **NeuralGCM** neural weather model (global, runs on GPU)
- **Claude** advisory generation and translation (any language)
- **XGBoost MOS** bias correction (trains automatically on local data)
- **FAISS + BM25 RAG** retrieval (rebuild index with your ag corpus)
- **PostgreSQL** database schema (geography-neutral)
- **Pipeline orchestration** (Dagster, scheduler, quality checks)
- **Delivery** (Twilio SMS/WhatsApp — works globally)

## What's Region-Specific (the prompt handles these)

| Component | File(s) | What to change |
|-----------|---------|---------------|
| **Stations** | `stations.json`, `config.py` | Replace with your stations |
| **Data ingestion** | `src/ingestion.py` | Write custom fetch function for your data source |
| **Farmer profiles** | `farmers.json` | Replace with your region's demo profiles (names, crops, soil types) |
| **Crop advisories** | `src/translation/curated_advisories.py` | Replace advisory matrix with your crops and conditions |
| **Seasonal context** | `src/healing.py` | Replace monthly weather patterns for your region |
| **Farmer services** | `src/dpi/` | India-specific service names (Aadhaar, PM-KISAN, etc.) for universal concepts (identity, land records, soil health, subsidies, insurance, credit). Rename or replace for your country's systems. |
| **Dashboard config** | `frontend/src/regionConfig.ts` | Single file: region name, states, languages, locale, data source label, currency, farmer service names |

## Verification

After adaptation, confirm everything works:

```bash
# 1. Pipeline runs end-to-end
python run_pipeline.py

# 2. Tests pass
pytest tests/

# 3. Check your stations loaded correctly
python -c "from config import STATIONS; print(f'{len(STATIONS)} stations loaded'); print([s.name for s in STATIONS])"

# 4. Check farmer profiles generated
python -c "from src.dpi.simulator import get_registry; r = get_registry(); print(f'{r.farmer_count} farmers generated')"
```

## Common Scenarios

### "I have NOAA stations (US)"
Use NOAA's Climate Data Online API or ISD data. Set your stations to NOAA USAF-WBAN IDs. Claude Code can write a NOAA client that maps to the same reading format.

### "I just want global coverage with no local data source"
Use Open-Meteo for ingestion (it provides current conditions globally, free). Set `ingestion_source: "custom"` with an Open-Meteo current-conditions fetcher.

### "I want to skip the farmer profiles entirely"
Set `config.dpi.simulation = False` and the pipeline will use station-level data for advisories without farmer-specific profiles.

### "I want to change the advisory language"
Set the `language` field in your `stations.json` entries. Claude API handles translation to any language — just specify the ISO 639-1 code (e.g., "es", "fr", "hi", "sw").
