// ────────────────────────────────────────────────────────────────
// mockData.ts
// In-memory fixtures for the Weather AI dashboard prototype copy.
// No live backend — every hook in `hooks.ts` reads from here so the
// UI renders populated content when running `npm run dev`.
// Focus: Kerala + Tamil Nadu smallholder farming, April pre-monsoon.
// ────────────────────────────────────────────────────────────────

import type {
  Station,
  Forecast,
  Alert,
  StationLatest,
  PipelineRun,
  TelemetryRecord,
  DeliveryRecord,
  HealingRecord,
  HealingStats,
  PipelineStats,
  SourceInfo,
  FarmerSummary,
  FarmerDetail,
  MosStatus,
} from './hooks'

// ── Time helpers ────────────────────────────────────────────────

const NOW = new Date('2026-04-13T08:42:00Z')

function isoMinutesAgo(mins: number): string {
  return new Date(NOW.getTime() - mins * 60_000).toISOString()
}

function isoHoursAgo(hours: number): string {
  return new Date(NOW.getTime() - hours * 3_600_000).toISOString()
}

function isoDaysAgo(days: number): string {
  return new Date(NOW.getTime() - days * 86_400_000).toISOString()
}

function isoDaysAhead(days: number): string {
  return new Date(NOW.getTime() + days * 86_400_000).toISOString()
}

function hash(s: string): number {
  let h = 0
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0
  return h
}

// ── Stations ────────────────────────────────────────────────────
// 20 real districts across Kerala (10) and Tamil Nadu (10).
// 2 stations offline (KL-09, TN-09). All other stations active.

interface StationFixture extends Station {
  language: 'ml' | 'ta'
  primary_crops: string[]
  active: boolean
}

export const STATIONS: StationFixture[] = [
  // Kerala
  { id: 'KL-01', name: 'Thiruvananthapuram', state: 'Kerala', lat: 8.52, lon: 76.94, altitude_m: 18, language: 'ml', primary_crops: ['coconut', 'rubber', 'banana'], source: 'imd_api', active: true },
  { id: 'KL-02', name: 'Kochi', state: 'Kerala', lat: 9.93, lon: 76.26, altitude_m: 7, language: 'ml', primary_crops: ['coconut', 'rice', 'cassava'], source: 'imd_api', active: true },
  { id: 'KL-03', name: 'Alappuzha', state: 'Kerala', lat: 9.50, lon: 76.34, altitude_m: 3, language: 'ml', primary_crops: ['rice', 'coconut'], source: 'imd_api', active: true },
  { id: 'KL-04', name: 'Kannur', state: 'Kerala', lat: 11.87, lon: 75.37, altitude_m: 11, language: 'ml', primary_crops: ['coconut', 'cashew', 'pepper'], source: 'imd_api', active: true },
  { id: 'KL-05', name: 'Kozhikode', state: 'Kerala', lat: 11.25, lon: 75.78, altitude_m: 9, language: 'ml', primary_crops: ['coconut', 'pepper', 'banana'], source: 'imdlib', active: true },
  { id: 'KL-06', name: 'Thrissur', state: 'Kerala', lat: 10.52, lon: 76.21, altitude_m: 28, language: 'ml', primary_crops: ['rice', 'coconut', 'banana'], source: 'imd_api', active: true },
  { id: 'KL-07', name: 'Kottayam', state: 'Kerala', lat: 9.59, lon: 76.52, altitude_m: 14, language: 'ml', primary_crops: ['rubber', 'pepper', 'cardamom'], source: 'imd_api', active: true },
  { id: 'KL-08', name: 'Palakkad', state: 'Kerala', lat: 10.79, lon: 76.65, altitude_m: 138, language: 'ml', primary_crops: ['rice', 'coconut', 'sugarcane'], source: 'imd_api', active: true },
  { id: 'KL-09', name: 'Punalur', state: 'Kerala', lat: 9.02, lon: 76.93, altitude_m: 47, language: 'ml', primary_crops: ['rubber', 'banana', 'pepper'], source: 'imdlib', active: false },
  { id: 'KL-10', name: 'Nilambur', state: 'Kerala', lat: 11.28, lon: 76.23, altitude_m: 42, language: 'ml', primary_crops: ['rubber', 'teak', 'banana'], source: 'synthetic', active: true },
  // Tamil Nadu
  { id: 'TN-01', name: 'Thanjavur', state: 'Tamil Nadu', lat: 10.79, lon: 79.14, altitude_m: 59, language: 'ta', primary_crops: ['rice', 'sugarcane', 'banana'], source: 'imd_api', active: true },
  { id: 'TN-02', name: 'Madurai', state: 'Tamil Nadu', lat: 9.92, lon: 78.12, altitude_m: 101, language: 'ta', primary_crops: ['cotton', 'rice', 'banana'], source: 'imd_api', active: true },
  { id: 'TN-03', name: 'Tiruchirappalli', state: 'Tamil Nadu', lat: 10.79, lon: 78.70, altitude_m: 78, language: 'ta', primary_crops: ['rice', 'banana', 'sugarcane'], source: 'imd_api', active: true },
  { id: 'TN-04', name: 'Salem', state: 'Tamil Nadu', lat: 11.66, lon: 78.15, altitude_m: 278, language: 'ta', primary_crops: ['cotton', 'turmeric', 'mango'], source: 'imd_api', active: true },
  { id: 'TN-05', name: 'Erode', state: 'Tamil Nadu', lat: 11.34, lon: 77.72, altitude_m: 183, language: 'ta', primary_crops: ['turmeric', 'cotton', 'sugarcane'], source: 'imdlib', active: true },
  { id: 'TN-06', name: 'Chennai', state: 'Tamil Nadu', lat: 13.08, lon: 80.27, altitude_m: 6, language: 'ta', primary_crops: ['rice', 'groundnut', 'vegetables'], source: 'imd_api', active: true },
  { id: 'TN-07', name: 'Tirunelveli', state: 'Tamil Nadu', lat: 8.73, lon: 77.70, altitude_m: 47, language: 'ta', primary_crops: ['rice', 'banana', 'cotton'], source: 'imd_api', active: true },
  { id: 'TN-08', name: 'Coimbatore', state: 'Tamil Nadu', lat: 11.01, lon: 76.96, altitude_m: 411, language: 'ta', primary_crops: ['cotton', 'maize', 'vegetables'], source: 'imd_api', active: true },
  { id: 'TN-09', name: 'Vellore', state: 'Tamil Nadu', lat: 12.92, lon: 79.13, altitude_m: 216, language: 'ta', primary_crops: ['rice', 'sugarcane', 'groundnut'], source: 'imdlib', active: false },
  { id: 'TN-10', name: 'Nagapattinam', state: 'Tamil Nadu', lat: 10.77, lon: 79.84, altitude_m: 4, language: 'ta', primary_crops: ['rice', 'coconut', 'groundnut'], source: 'imd_api', active: true },
]

// Plain Station[] view to return from useStations().
export const STATIONS_VIEW: Station[] = STATIONS.map((s) => ({
  id: s.id,
  name: s.name,
  state: s.state,
  lat: s.lat,
  lon: s.lon,
  altitude_m: s.altitude_m,
  source: s.source,
  active: s.active,
}))

function stationMeta(id: string): StationFixture | undefined {
  return STATIONS.find((s) => s.id === id)
}

function stationName(id: string): string {
  return stationMeta(id)?.name ?? id
}

function stationCoords(id: string): { lat: number; lon: number } {
  const s = stationMeta(id)
  return { lat: s?.lat ?? 0, lon: s?.lon ?? 0 }
}

// ── Raw telemetry (pre-heal) ────────────────────────────────────
// One most-recent reading per station. April = pre-monsoon.
// Four seeded anomalies: KL-07 temp outlier, KL-09 humidity missing,
// TN-06 rainfall spike, TN-09 stale reading.

interface RawSample {
  station_id: string
  temperature: number
  humidity: number
  rainfall: number
  wind_speed: number
  quality_score: number
  source: string
  minutes_ago: number
  heal_action?: string
}

const RAW_SAMPLES: RawSample[] = [
  { station_id: 'KL-01', temperature: 31.2, humidity: 82, rainfall: 0, wind_speed: 3.1, quality_score: 0.94, source: 'imd_api', minutes_ago: 12 },
  { station_id: 'KL-02', temperature: 30.4, humidity: 86, rainfall: 2.4, wind_speed: 2.8, quality_score: 0.93, source: 'imd_api', minutes_ago: 9 },
  { station_id: 'KL-03', temperature: 30.7, humidity: 85, rainfall: 0, wind_speed: 2.3, quality_score: 0.92, source: 'imd_api', minutes_ago: 14 },
  { station_id: 'KL-04', temperature: 30.1, humidity: 80, rainfall: 0, wind_speed: 3.6, quality_score: 0.95, source: 'imd_api', minutes_ago: 7 },
  { station_id: 'KL-05', temperature: 30.9, humidity: 83, rainfall: 0, wind_speed: 2.7, quality_score: 0.91, source: 'imdlib', minutes_ago: 17 },
  { station_id: 'KL-06', temperature: 32.1, humidity: 74, rainfall: 0, wind_speed: 1.9, quality_score: 0.94, source: 'imd_api', minutes_ago: 11 },
  { station_id: 'KL-07', temperature: 48.2, humidity: 77, rainfall: 0, wind_speed: 2.4, quality_score: 0.58, source: 'imd_api', minutes_ago: 8, heal_action: 'anomaly_flagged' },
  { station_id: 'KL-08', temperature: 33.7, humidity: 68, rainfall: 0, wind_speed: 3.8, quality_score: 0.93, source: 'imd_api', minutes_ago: 13 },
  { station_id: 'KL-09', temperature: 31.6, humidity: 0, rainfall: 0, wind_speed: 2.1, quality_score: 0.61, source: 'imdlib', minutes_ago: 28, heal_action: 'ai_flagged' },
  { station_id: 'KL-10', temperature: 32.3, humidity: 72, rainfall: 0, wind_speed: 2.2, quality_score: 0.88, source: 'synthetic', minutes_ago: 19 },
  { station_id: 'TN-01', temperature: 33.8, humidity: 69, rainfall: 0, wind_speed: 3.4, quality_score: 0.95, source: 'imd_api', minutes_ago: 6 },
  { station_id: 'TN-02', temperature: 35.1, humidity: 62, rainfall: 0, wind_speed: 4.2, quality_score: 0.93, source: 'imd_api', minutes_ago: 10 },
  { station_id: 'TN-03', temperature: 34.6, humidity: 65, rainfall: 0, wind_speed: 3.1, quality_score: 0.92, source: 'imd_api', minutes_ago: 15 },
  { station_id: 'TN-04', temperature: 35.9, humidity: 60, rainfall: 0, wind_speed: 4.6, quality_score: 0.94, source: 'imd_api', minutes_ago: 8 },
  { station_id: 'TN-05', temperature: 35.3, humidity: 63, rainfall: 0, wind_speed: 4.1, quality_score: 0.91, source: 'imdlib', minutes_ago: 22 },
  { station_id: 'TN-06', temperature: 31.4, humidity: 78, rainfall: 8.1, wind_speed: 5.2, quality_score: 0.67, source: 'imd_api', minutes_ago: 5, heal_action: 'anomaly_flagged' },
  { station_id: 'TN-07', temperature: 34.2, humidity: 68, rainfall: 0, wind_speed: 3.7, quality_score: 0.94, source: 'imd_api', minutes_ago: 12 },
  { station_id: 'TN-08', temperature: 33.1, humidity: 64, rainfall: 0, wind_speed: 3.9, quality_score: 0.96, source: 'imd_api', minutes_ago: 4 },
  { station_id: 'TN-09', temperature: 34.4, humidity: 66, rainfall: 0, wind_speed: 2.8, quality_score: 0.52, source: 'imdlib', minutes_ago: 73, heal_action: 'imputed_from_reference' },
  { station_id: 'TN-10', temperature: 31.8, humidity: 79, rainfall: 4.3, wind_speed: 4.1, quality_score: 0.92, source: 'imd_api', minutes_ago: 11 },
]

export const TELEMETRY_RAW: TelemetryRecord[] = RAW_SAMPLES.map((r, idx) => ({
  id: 8200 + idx,
  station_id: r.station_id,
  station_name: stationName(r.station_id),
  temperature: r.temperature,
  humidity: r.humidity,
  rainfall: r.rainfall,
  wind_speed: r.wind_speed,
  ts: isoMinutesAgo(r.minutes_ago),
  quality_score: r.quality_score,
  source: r.source,
  heal_action: r.heal_action,
  fields_filled: r.heal_action ? 1 : 0,
}))

// ── Clean telemetry (post-heal) ─────────────────────────────────

export const TELEMETRY_CLEAN: TelemetryRecord[] = RAW_SAMPLES.map((r, idx) => {
  let temperature = r.temperature
  let humidity = r.humidity
  let rainfall = r.rainfall
  let qualityBump = 0.04
  let heal_action: string = 'cross_validated'

  if (r.station_id === 'KL-07') {
    temperature = 29.1
    qualityBump = 0.37
    heal_action = 'ai_corrected'
  } else if (r.station_id === 'KL-09') {
    humidity = 79
    qualityBump = 0.31
    heal_action = 'ai_filled'
  } else if (r.station_id === 'TN-06') {
    rainfall = 2.1
    qualityBump = 0.27
    heal_action = 'typo_corrected'
  } else if (r.station_id === 'TN-09') {
    qualityBump = 0.38
    temperature = 33.9
    humidity = 67
    heal_action = 'imputed_from_reference'
  } else if (idx % 5 === 0) {
    heal_action = 'ai_validated'
  } else if (idx % 7 === 0) {
    heal_action = 'null_filled'
  }

  return {
    id: 9200 + idx,
    station_id: r.station_id,
    station_name: stationName(r.station_id),
    temperature,
    humidity,
    rainfall,
    wind_speed: r.wind_speed,
    ts: isoMinutesAgo(r.minutes_ago),
    quality_score: Math.min(0.99, r.quality_score + qualityBump),
    source: r.source,
    heal_action,
    fields_filled: heal_action.startsWith('ai_') || heal_action === 'imputed_from_reference' || heal_action === 'null_filled' ? 1 : 0,
  }
})

// Station-latest lookup. NOTE: this hook has no backend; the shape here is
// still the legacy frontend one because the port chat will define it.
export const STATION_LATEST_BY_ID: Record<string, StationLatest> = {}
for (const r of TELEMETRY_CLEAN) {
  const meta = stationMeta(r.station_id)
  STATION_LATEST_BY_ID[r.station_id] = {
    station_id: r.station_id,
    station_name: meta?.name,
    state: meta?.state,
    latitude: meta?.lat,
    longitude: meta?.lon,
    temperature: r.temperature,
    humidity: r.humidity,
    rainfall_mm: r.rainfall,
    wind_speed: r.wind_speed,
    quality_score: r.quality_score,
    observed_at: r.ts,
    source: r.source,
  }
}

// ── Forecasts (140 rows: 20 stations × 7 days) ──────────────────

const CONDITION_CYCLE = [
  'clear',
  'clear',
  'moderate_rain',
  'heavy_rain',
  'heat_stress',
  'clear',
  'drought_risk',
] as const

function baseTempForStation(id: string): { max: number; min: number } {
  const alt = stationMeta(id)?.altitude_m ?? 50
  const coastal = alt < 60
  if (id === 'TN-02' || id === 'TN-04') return { max: 36, min: 26 }
  if (id === 'TN-08') return { max: 33, min: 21 }
  if (coastal) return { max: 32, min: 25 }
  return { max: 34, min: 23 }
}

export const FORECASTS: Forecast[] = (() => {
  const rows: Forecast[] = []
  let id = 40_000
  for (const s of STATIONS) {
    const base = baseTempForStation(s.id)
    for (let day = 0; day < 7; day++) {
      const drift = day * 0.2 - 0.4
      const condition = CONDITION_CYCLE[day]
      const isRainy = condition === 'moderate_rain' || condition === 'heavy_rain'
      const coastal = (s.altitude_m ?? 50) < 60
      const rain = isRainy
        ? +(coastal ? 6 + day * 0.4 : 3 + day * 0.3).toFixed(1)
        : 0
      const humidity = coastal
        ? 78 + (isRainy ? 6 : -2) + Math.round(drift * 2)
        : 62 + (isRainy ? 8 : 0) + Math.round(drift * 2)
      // MOS trained model ~0.85 RMSE, so base confidence high; decay with day
      const confidence = 0.78 + (6 - day) * 0.025 - (s.id === 'TN-09' ? 0.08 : 0)
      // Rotate models: neuralgcm_mos is the primary, hybrid_mos secondary
      const modelIdx = (day + hash(s.id)) % 4
      const model =
        modelIdx === 0 ? 'neuralgcm_mos'
        : modelIdx === 1 ? 'hybrid_mos'
        : modelIdx === 2 ? 'neuralgcm_only'
        : 'nwp_only'
      const tMax = +(base.max + drift - (coastal && isRainy ? 1.2 : 0)).toFixed(1)
      const tMin = +(base.min - 0.1 * day).toFixed(1)
      rows.push({
        id: id++,
        station_id: s.id,
        station_name: s.name,
        issued_at: isoHoursAgo(4),
        valid_for_ts: isoDaysAhead(day),
        forecast_day: day,
        // DB stores a single `temperature` column; we fill it with the daily
        // max so the one-temperature-per-row UI keeps working, and also keep
        // temp_min/temp_max as optional helpers (not in DB — port chat may
        // need to drop them).
        temperature: tMax,
        temp_max: tMax,
        temp_min: tMin,
        rainfall: rain,
        humidity: Math.max(52, Math.min(94, humidity)),
        condition,
        model_used: model,
        confidence: Math.max(0.62, Math.min(0.96, +confidence.toFixed(2))),
        created_at: isoHoursAgo(4),
      })
    }
  }
  return rows
})()

// ── Advisory templates (EN + ML + TA with real script) ─────────

interface AdvisoryTemplate {
  condition: string
  en: string
  ml: string
  ta: string
}

const ADVISORY_TEMPLATES: AdvisoryTemplate[] = [
  {
    condition: 'heavy_rain',
    en: 'Heavy rain expected Thursday afternoon — 35mm in 4 hours. Drain paddy fields and secure banana supports before evening.',
    ml: 'വ്യാഴാഴ്ച ഉച്ചതിരിഞ്ഞ് ശക്തമായ മഴ. നെല്‍വയലിലെ വെള്ളം കളയുക, വാഴച്ചെടികള്‍ക്ക് താങ്ങ് ഉറപ്പിക്കുക.',
    ta: 'வியாழன் மதியம் கனமழை எதிர்பார்க்கப்படுகிறது. நெல் வயல்களில் நீரை வடிக்கவும், வாழை ஆதரவுகளை பாதுகாக்கவும்.',
  },
  {
    condition: 'moderate_rain',
    en: 'Moderate rain Friday night, 8-12mm total. Good window for transplanting rice in lowland plots. Skip irrigation today.',
    ml: 'വെള്ളിയാഴ്ച രാത്രി മിതമായ മഴ. നെല്ല് നടാന്‍ നല്ല സമയം. ഇന്നത്തെ നനവ് ഒഴിവാക്കാം.',
    ta: 'வெள்ளி இரவு மிதமான மழை. நெல் நடவுக்கு சரியான நேரம். இன்றைய பாசனத்தை தவிர்க்கவும்.',
  },
  {
    condition: 'heat_stress',
    en: 'Heat peaks 36-37°C next three days. Irrigate banana clumps in early morning only and apply mulch to sugarcane rows.',
    ml: 'അടുത്ത മൂന്ന് ദിവസം 36-37°C ചൂട്. വാഴക്ക് രാവിലെ മാത്രം നനയ്ക്കുക, കരിമ്പിന് പുതയിടുക.',
    ta: 'அடுத்த மூன்று நாட்கள் 36-37°C. வாழைக்கு காலை மட்டும் பாசனம், கரும்புக்கு மல்ச் போடவும்.',
  },
  {
    condition: 'drought_risk',
    en: 'Dry spell continuing. Schedule deep irrigation for coconut palms this weekend and delay any new sowings.',
    ml: 'വരള്‍ച്ച തുടരുന്നു. തെങ്ങിന് ഈ വാരാന്ത്യം ആഴത്തിലുള്ള നനവ്, പുതിയ വിത്ത് നീട്ടുക.',
    ta: 'வறட்சி தொடர்கிறது. தென்னைக்கு இந்த வார இறுதியில் ஆழ பாசனம், புதிய விதைப்பை தள்ளுங்கள்.',
  },
  {
    condition: 'high_wind',
    en: 'Gusty afternoon winds forecast Tuesday, 35-40 km/h. Support young papaya and banana plants before noon.',
    ml: 'ചൊവ്വാഴ്ച ഉച്ചതിരിഞ്ഞ് ശക്തമായ കാറ്റ്. പപ്പായ, വാഴ തൈകള്‍ക്ക് ഉച്ചക്കു മുമ്പ് താങ്ങ് കൊടുക്കുക.',
    ta: 'செவ்வாய் மதியம் வலுவான காற்று. பப்பாளி, வாழை தைகளுக்கு மதியத்திற்கு முன் ஆதரவு வையுங்கள்.',
  },
  {
    condition: 'clear',
    en: 'Clear weather through the weekend. Prime window for black pepper harvest and coconut husk drying.',
    ml: 'വാരാന്ത്യം വരെ തെളിഞ്ഞ കാലാവസ്ഥ. കുരുമുളക് വിളവെടുക്കാനും തൊണ്ട് ഉണക്കാനും നല്ല സമയം.',
    ta: 'வார இறுதி வரை தெளிவான வானிலை. மிளகு அறுவடைக்கும் தேங்காய் மட்டை காய வைக்கவும் சரியான நேரம்.',
  },
  {
    condition: 'moderate_rain',
    en: 'Pre-monsoon showers likely Friday. Apply urea to rice only after the rain stops to avoid nutrient loss.',
    ml: 'വെള്ളിയാഴ്ച മണ്‍സൂണ്‍ മുന്‍മഴ സാധ്യത. മഴ നിന്നശേഷം മാത്രം നെല്ലിന് യൂറിയ നല്‍കുക.',
    ta: 'வெள்ளிக்கிழமை பருவமழை. மழைக்கு பிறகு மட்டுமே நெல்லுக்கு யூரியா போடவும்.',
  },
  {
    condition: 'heat_stress',
    en: 'Afternoon highs above 35°C for four days. Scout coconut palms for rhinoceros beetle and avoid midday weeding.',
    ml: 'നാല് ദിവസം ഉച്ചയ്ക്ക് 35°C-ന് മുകളില്‍. തെങ്ങില്‍ കൊമ്പന്‍ ചെല്ലി ശ്രദ്ധിക്കുക, ഉച്ചക്ക് കളപറിക്കരുത്.',
    ta: 'நான்கு நாட்கள் மதியம் 35°C மேல். தென்னையில் கொம்பன் வண்டு கவனிக்கவும், மதியம் களை எடுக்க வேண்டாம்.',
  },
]

// ── Agricultural alerts / advisories (30 entries) ──────────────

export const ALERTS: Alert[] = (() => {
  const rows: Alert[] = []
  for (let i = 0; i < 30; i++) {
    const station = STATIONS[i % STATIONS.length]
    const template = ADVISORY_TEMPLATES[i % ADVISORY_TEMPLATES.length]
    const isMl = station.language === 'ml'
    const local = isMl ? template.ml : template.ta
    const hoursAgo = 6 + i * 3 + (i % 3)
    const provider = i % 5 === 0 ? 'rag_claude' : i % 7 === 0 ? 'template' : 'rag'
    const severity = template.condition.includes('heavy') || template.condition.includes('drought') ? 'high' : template.condition.includes('rain') || template.condition.includes('heat') ? 'medium' : 'low'
    rows.push({
      id: 5100 + i,
      station_id: station.id,
      station_name: station.name,
      condition: template.condition,
      severity,
      advisory_en: template.en,
      advisory_local: local,
      language: station.language,
      provider,
      retrieval_docs: provider === 'rag' || provider === 'rag_claude' ? 5 : 0,
      forecast_days: i % 4 === 0 ? 7 : 3,
      issued_at: isoHoursAgo(hoursAgo + 1),
      created_at: isoHoursAgo(hoursAgo + 1),
    })
  }
  return rows
})()

// ── Delivery log (31 entries) ──────────────────────────────────
// 30 tied 1:1 to alerts + 1 extra failed send.
// Pattern: 27 sent, 2 dry_run, 2 failed → "sentCount" = 29 (27+2 dry_run count).

const DELIVERY_STATUSES: Array<'sent' | 'dry_run' | 'failed'> = (() => {
  const arr: Array<'sent' | 'dry_run' | 'failed'> = new Array(30).fill('sent')
  arr[5] = 'dry_run'
  arr[17] = 'dry_run'
  arr[11] = 'failed'
  arr[23] = 'failed'
  return arr
})()

export const DELIVERIES: DeliveryRecord[] = ALERTS.map((a, idx) => {
  const useSms = idx % 5 !== 0
  return {
    id: 7300 + idx,
    alert_id: typeof a.id === 'number' ? String(a.id) : a.id,
    station_id: a.station_id,
    station_name: a.station_name,
    channel: useSms ? 'sms' : 'console',
    recipient: `+91 984${String(10 + (idx % 90)).padStart(2, '0')} ${String(12340 + idx).padStart(5, '0')}`,
    status: DELIVERY_STATUSES[idx],
    message: (a.advisory_local ?? a.advisory_en ?? '').slice(0, 64),
    delivered_at: isoHoursAgo(6 + idx * 3),
    created_at: a.issued_at,
  }
})

// ── Healing log ────────────────────────────────────────────────

export const HEALING_RECORDS: HealingRecord[] = [
  {
    id: 'heal-4b1c',
    pipeline_run_id: 'run-2026w15-mon',
    reading_id: 'rt-8206',
    station_id: 'KL-07',
    assessment: 'corrected',
    reasoning:
      'Raw temperature 48.2°C is 18°C above neighbouring Kottayam and Alappuzha stations. Satellite LST confirms 29°C surface. Consistent with a stuck sensor pad — imputed from IMD-12 neighbour median and grid reference.',
    corrections: '{"temperature": 29.1}',
    original_values: '{"temperature": 48.2}',
    quality_score: 0.95,
    tools_used: 'neighbor_lookup, satellite_lst',
    model: 'claude-sonnet-4-5',
    tokens_in: 612,
    tokens_out: 187,
    latency_s: 1.83,
    fallback_used: false,
    created_at: isoMinutesAgo(14),
    field: 'temperature',
    original_value: 48.2,
    healed_value: 29.1,
    method: 'claude-agent',
    healed_at: isoMinutesAgo(14),
  },
  {
    id: 'heal-4b21',
    pipeline_run_id: 'run-2026w15-mon',
    reading_id: 'rt-8208',
    station_id: 'KL-09',
    assessment: 'filled',
    reasoning:
      'Humidity sensor returned 0% at Punalur — impossible for a coastal station in April. Inverse distance weighting from Kottayam (82%), Thiruvananthapuram (80%) and Nilambur (72%) gives an imputed 79%. Temperature reading left untouched.',
    corrections: '{"humidity": 79}',
    original_values: '{"humidity": 0}',
    quality_score: 0.92,
    tools_used: 'neighbor_lookup, idw',
    model: 'claude-sonnet-4-5',
    tokens_in: 487,
    tokens_out: 142,
    latency_s: 1.41,
    fallback_used: false,
    created_at: isoMinutesAgo(34),
    field: 'humidity',
    original_value: 0,
    healed_value: 79,
    method: 'claude-agent',
    healed_at: isoMinutesAgo(34),
  },
  {
    id: 'heal-4b25',
    pipeline_run_id: 'run-2026w15-mon',
    reading_id: 'rt-8215',
    station_id: 'TN-06',
    assessment: 'corrected',
    reasoning:
      'Rainfall spike of 8.1mm in 5min at Chennai station not supported by IMERG satellite radar or neighbouring Vellore stations. Looks like a decimal shift — corrected to 2.1mm/hr to match the satellite grid cell.',
    corrections: '{"rainfall": 2.1}',
    original_values: '{"rainfall": 8.1}',
    quality_score: 0.94,
    tools_used: 'satellite_radar, imerg',
    model: 'claude-sonnet-4-5',
    tokens_in: 503,
    tokens_out: 164,
    latency_s: 1.62,
    fallback_used: false,
    created_at: isoMinutesAgo(8),
    field: 'rainfall',
    original_value: 8.1,
    healed_value: 2.1,
    method: 'claude-agent',
    healed_at: isoMinutesAgo(8),
  },
  {
    id: 'heal-4b2a',
    pipeline_run_id: 'run-2026w15-mon',
    reading_id: 'rt-8218',
    station_id: 'TN-09',
    assessment: 'filled',
    reasoning:
      'Station last reported 73 minutes ago, exceeding the 45-minute freshness threshold. Fell back to the NeuralGCM surface hourly grid for this timestep. Confidence reduced accordingly.',
    corrections: '{"temperature": 33.9, "humidity": 67}',
    original_values: '{"temperature": 34.4, "humidity": 66}',
    quality_score: 0.90,
    tools_used: 'neuralgcm_surface',
    model: 'claude-sonnet-4-5',
    tokens_in: 703,
    tokens_out: 221,
    latency_s: 2.14,
    fallback_used: true,
    created_at: isoMinutesAgo(78),
    field: 'temperature',
    original_value: 34.4,
    healed_value: 33.9,
    method: 'claude-agent',
    healed_at: isoMinutesAgo(78),
  },
  {
    id: 'heal-4a91',
    pipeline_run_id: 'run-2026w14-mon',
    reading_id: 'rt-8102',
    station_id: 'KL-03',
    assessment: 'good',
    reasoning:
      'All fields at Alappuzha within neighbour band and satellite agreement. No correction required.',
    corrections: '{}',
    original_values: '{}',
    quality_score: 0.97,
    tools_used: 'neighbor_lookup',
    model: 'claude-sonnet-4-5',
    tokens_in: 287,
    tokens_out: 64,
    latency_s: 0.82,
    fallback_used: false,
    created_at: isoDaysAgo(7),
    field: 'none',
    healed_at: isoDaysAgo(7),
  },
  {
    id: 'heal-4a8e',
    pipeline_run_id: 'run-2026w14-mon',
    reading_id: 'rt-8099',
    station_id: 'TN-04',
    assessment: 'filled',
    reasoning:
      'Pressure reading missing from Salem station. Imputed from ERA5 reanalysis at the station grid cell — 1008 hPa is consistent with the seasonal norm.',
    corrections: '{"pressure_hpa": 1008}',
    original_values: '{"pressure_hpa": null}',
    quality_score: 0.89,
    tools_used: 'era5_reanalysis',
    model: 'claude-sonnet-4-5',
    tokens_in: 398,
    tokens_out: 115,
    latency_s: 1.12,
    fallback_used: false,
    created_at: isoDaysAgo(7),
    field: 'pressure_hpa',
    original_value: null,
    healed_value: 1008,
    method: 'claude-agent',
    healed_at: isoDaysAgo(7),
  },
  {
    id: 'heal-4a7c',
    pipeline_run_id: 'run-2026w13-mon',
    reading_id: 'rt-7921',
    station_id: 'KL-05',
    assessment: 'corrected',
    reasoning:
      'Wind speed spike of 12 m/s inconsistent with the coastal Kozhikode pattern this week. Smoothed against linear interpolation to 4.1 m/s.',
    corrections: '{"wind_speed": 4.1}',
    original_values: '{"wind_speed": 12.0}',
    quality_score: 0.93,
    tools_used: 'linear_interp, neighbor_lookup',
    model: 'claude-sonnet-4-5',
    tokens_in: 451,
    tokens_out: 128,
    latency_s: 1.29,
    fallback_used: false,
    created_at: isoDaysAgo(14),
    field: 'wind_speed',
    original_value: 12.0,
    healed_value: 4.1,
    method: 'claude-agent',
    healed_at: isoDaysAgo(14),
  },
  {
    id: 'heal-4a55',
    pipeline_run_id: 'run-2026w12-mon',
    reading_id: 'rt-7800',
    station_id: 'TN-08',
    assessment: 'corrected',
    reasoning:
      'Humidity returned 100% for 3 consecutive timesteps at Coimbatore — likely a stuck sensor. Imputed from gridded analysis to 64%.',
    corrections: '{"humidity": 64}',
    original_values: '{"humidity": 100}',
    quality_score: 0.91,
    tools_used: 'era5_reanalysis, neighbor_lookup',
    model: 'claude-sonnet-4-5',
    tokens_in: 567,
    tokens_out: 167,
    latency_s: 1.62,
    fallback_used: false,
    created_at: isoDaysAgo(21),
    field: 'humidity',
    original_value: 100,
    healed_value: 64,
    method: 'claude-agent',
    healed_at: isoDaysAgo(21),
  },
  {
    id: 'heal-4a3b',
    pipeline_run_id: 'run-2026w11-mon',
    reading_id: 'rt-7712',
    station_id: 'KL-08',
    assessment: 'good',
    reasoning: 'All fields at Palakkad within threshold. No correction required.',
    corrections: '{}',
    original_values: '{}',
    quality_score: 0.96,
    tools_used: 'neighbor_lookup',
    model: 'claude-sonnet-4-5',
    tokens_in: 241,
    tokens_out: 58,
    latency_s: 0.71,
    fallback_used: false,
    created_at: isoDaysAgo(28),
    field: 'none',
    healed_at: isoDaysAgo(28),
  },
  {
    id: 'heal-4a20',
    pipeline_run_id: 'run-2026w11-mon',
    reading_id: 'rt-7684',
    station_id: 'TN-02',
    assessment: 'corrected',
    reasoning:
      'Temperature dropped 9°C in a single timestep without rain — smoothed against linear interpolation. Consistent with a momentary sensor dropout.',
    corrections: '{"temperature": 33.0}',
    original_values: '{"temperature": 24.1}',
    quality_score: 0.90,
    tools_used: 'linear_interp',
    model: 'claude-sonnet-4-5',
    tokens_in: 419,
    tokens_out: 121,
    latency_s: 1.18,
    fallback_used: false,
    created_at: isoDaysAgo(28),
    field: 'temperature',
    original_value: 24.1,
    healed_value: 33.0,
    method: 'claude-agent',
    healed_at: isoDaysAgo(28),
  },
  {
    id: 'heal-4a0f',
    pipeline_run_id: 'run-2026w10-mon',
    reading_id: 'rt-7581',
    station_id: 'KL-02',
    assessment: 'filled',
    reasoning: 'Rainfall sensor NaN during the pre-monsoon spell at Kochi. Imputed from IMERG satellite data.',
    corrections: '{"rainfall": 3.2}',
    original_values: '{"rainfall": null}',
    quality_score: 0.92,
    tools_used: 'imerg',
    model: 'claude-sonnet-4-5',
    tokens_in: 389,
    tokens_out: 108,
    latency_s: 0.98,
    fallback_used: false,
    created_at: isoDaysAgo(35),
    field: 'rainfall',
    original_value: null,
    healed_value: 3.2,
    method: 'claude-agent',
    healed_at: isoDaysAgo(35),
  },
  {
    id: 'heal-49f0',
    pipeline_run_id: 'run-2026w10-mon',
    reading_id: 'rt-7562',
    station_id: 'TN-07',
    assessment: 'good',
    reasoning: 'Tirunelveli within threshold on every field.',
    corrections: '{}',
    original_values: '{}',
    quality_score: 0.95,
    tools_used: 'neighbor_lookup',
    model: 'claude-sonnet-4-5',
    tokens_in: 218,
    tokens_out: 52,
    latency_s: 0.64,
    fallback_used: false,
    created_at: isoDaysAgo(35),
    field: 'none',
    healed_at: isoDaysAgo(35),
  },
]

export const HEALING_STATS: HealingStats = {
  total_healed: 487,
  by_field: {
    temperature: 147,
    humidity: 126,
    rainfall: 98,
    wind_speed: 74,
    pressure: 42,
  },
  by_method: {
    'claude-agent': 312,
    'rule-based': 175,
  },
  recent_count: 37,
  assessment_distribution: {
    good: { count: 3841, avg_quality: 0.96 },
    corrected: { count: 412, avg_quality: 0.92 },
    filled: { count: 198, avg_quality: 0.90 },
    flagged: { count: 41, avg_quality: 0.74 },
    dropped: { count: 7, avg_quality: null },
  },
  latest_run: {
    model: 'claude-sonnet-4-5',
    tokens_in: 612,
    tokens_out: 187,
    latency_s: 1.83,
    fallback_used: false,
  },
}

// ── Pipeline runs (20 runs, weekly cadence, 17 success/2 failed/1 partial) ──

export const PIPELINE_RUNS: PipelineRun[] = (() => {
  const rows: PipelineRun[] = []
  for (let i = 0; i < 20; i++) {
    const start = new Date(NOW)
    start.setUTCDate(start.getUTCDate() - i * 7)
    start.setUTCHours(0, 30, 0, 0)
    const isFailure = i === 4 || i === 12
    const isPartial = i === 7
    const duration = isFailure ? 234 : isPartial ? 1093 : 840 + ((i * 37) % 280)
    const ended = new Date(start.getTime() + duration * 1000)
    const status = isFailure ? 'failed' : isPartial ? 'partial' : 'success'
    const errDetail = isFailure
      ? i === 4
        ? 'IMD scraper timeout after 180s on station TN-09'
        : 'NeuralGCM inference OOM — falling back to hybrid_mos model'
      : isPartial
        ? 'Translation step timed out on 3 Tamil advisories'
        : undefined
    rows.push({
      id: 2000 + (19 - i),
      run_id: `run-${start.toISOString().slice(0, 10).replace(/-/g, '')}-mon`,
      status,
      started_at: start.toISOString(),
      ended_at: ended.toISOString(),
      steps_ok: isFailure ? 2 : isPartial ? 5 : 6,
      steps_fail: isFailure ? 4 : isPartial ? 1 : 0,
      summary: errDetail,
      // Frontend-only derived fields below — not in DB. Kept so existing UI
      // keeps rendering. Port chat will need to either add these columns,
      // join across tables to compute them, or drop the columns from the UI.
      duration_seconds: duration,
      stations_processed: isFailure ? 0 : isPartial ? 17 : 20,
      records_ingested: isFailure ? 0 : isPartial ? 3982 : 4713 + ((i * 91) % 240),
      errors: isFailure ? 4 : isPartial ? 1 : 0,
      error_detail: errDetail,
    })
  }
  return rows
})()

// ── Pipeline stats ────────────────────────────────────────────

export const PIPELINE_STATS: PipelineStats = {
  raw_telemetry: 4713,
  clean_telemetry: 4689,
  healing_log: 487,
  forecasts: 1148,
  agricultural_alerts: 487,
  delivery_log: 471,
  pipeline_runs: PIPELINE_RUNS.length,
  total_runs: PIPELINE_RUNS.length,
  successful_runs: PIPELINE_RUNS.filter((r) => r.status === 'success').length,
  failed_runs: PIPELINE_RUNS.filter((r) => r.status === 'failed').length,
  avg_duration:
    PIPELINE_RUNS.reduce((s, r) => s + (r.duration_seconds ?? 0), 0) / PIPELINE_RUNS.length,
  last_run: PIPELINE_RUNS[0],
  total_records: 7084,
}

// ── Sources ───────────────────────────────────────────────────

export const SOURCES: SourceInfo[] = [
  { name: 'imd_api', source: 'imd_api', count: 2837, type: 'observation', stations: 16, last_fetch: isoMinutesAgo(11), status: 'healthy' },
  { name: 'imdlib', source: 'imdlib', count: 1398, type: 'gridded', stations: 3, last_fetch: isoMinutesAgo(17), status: 'healthy' },
  { name: 'synthetic', source: 'synthetic', count: 478, type: 'fallback', stations: 1, last_fetch: isoMinutesAgo(19), status: 'degraded' },
]

// ── MOS status ────────────────────────────────────────────────

export const MOS_STATUS: MosStatus = {
  trained: true,
  metrics: {
    rmse: 1.12,
    mae: 0.87,
    r2: 0.91,
    n_train: 17432,
    n_test: 4358,
    residual_mean: 0.03,
    residual_std: 1.08,
    feature_importances: {
      nwp_temp_max: 0.38,
      station_climatology: 0.27,
      elevation: 0.12,
      day_of_year: 0.09,
      nwp_humidity: 0.08,
      terrain_slope: 0.06,
    },
  },
}

// ── Eval metrics (Pipeline page -> EvalMetricsTab) ────────────
// Structure matches Pipeline.tsx extraction (evals.healing, evals.forecast, etc).

export const EVAL_METRICS: Record<string, any> = {
  healing: {
    total_readings: 4713,
    binary_detection: { precision: 0.93, recall: 0.88, f1: 0.905 },
    per_fault_type: {
      stuck_sensor: { count: 142, accuracy: 0.94, imputation_mae: 0.82 },
      decimal_shift: { count: 67, accuracy: 0.97, imputation_mae: 0.31 },
      stale_reading: { count: 54, accuracy: 0.89, imputation_mae: 1.14 },
      missing_field: { count: 198, accuracy: 0.96, imputation_mae: 0.68 },
    },
  },
  forecast: {
    total_pairs: 1148,
    overall: {
      temperature: { mae: 0.87, rmse: 1.12 },
    },
    by_model: {
      neuralgcm_mos: { n: 412, mae: 0.74, rmse: 0.98, bias: 0.08 },
      hybrid_mos: { n: 341, mae: 0.91, rmse: 1.19, bias: -0.04 },
      neuralgcm_only: { n: 217, mae: 1.08, rmse: 1.37, bias: 0.17 },
      nwp_only: { n: 178, mae: 1.24, rmse: 1.58, bias: 0.22 },
    },
  },
  rag: {
    by_mode: {
      hybrid_faiss_bm25: { avg_precision: 0.82, avg_recall: 0.74, n_cases: 147 },
      bm25_only: { avg_precision: 0.68, avg_recall: 0.61, n_cases: 147 },
      faiss_only: { avg_precision: 0.71, avg_recall: 0.66, n_cases: 147 },
    },
  },
  advisory: {
    by_provider: {
      rag: { avg_accuracy: 4.3, avg_actionability: 4.1, avg_safety: 0.2, avg_cultural: 4.4 },
      rag_claude: { avg_accuracy: 4.6, avg_actionability: 4.5, avg_safety: 0.3, avg_cultural: 4.7 },
      template: { avg_accuracy: 3.8, avg_actionability: 3.5, avg_safety: 0.1, avg_cultural: 3.9 },
    },
  },
  translation: {
    avg_similarity: 4.4,
    avg_ag_preservation: 0.92,
    by_language: {
      ml: { n: 241, avg_similarity: 4.5, avg_ag_preservation: 0.94 },
      ta: { n: 246, avg_similarity: 4.3, avg_ag_preservation: 0.91 },
    },
  },
  dpi: {
    total_farmers: 20,
    coverage: { coverage_rate: 1.0 },
    completeness: { completeness_rate: 0.94 },
    consistency: { rate: 0.97 },
  },
  conversation: {
    state_machine: { accuracy: 0.91 },
    language_detection: { accuracy: 0.96 },
    escalation_detection: { accuracy: 0.88 },
    overall: { overall_rate: 0.92 },
  },
}

// ── Conversation log (Pipeline page -> AgentLogTab) ──────────

export const CONVERSATION_LOG: Array<Record<string, any>> = (() => {
  const sessions = ['a12f5bd3', 'b7c49e81', 'cc8f21a4', 'd51e6b7f', 'e3a98042']
  const userMessages = [
    'Will it rain tomorrow in Madurai?',
    'Should I spray my paddy field today?',
    'When should I irrigate coconut trees?',
    'Are banana supports needed this week?',
    'Best time to harvest black pepper?',
    'Is there any storm warning for Kottayam?',
    'What fertilizer should I use for rice?',
    'Did you send my advisory yesterday?',
    'Temperature forecast for Chennai this week',
    'Pest alert for my cotton crop',
  ]
  const assistantMessages = [
    'No rain expected in Madurai tomorrow — heat peaks at 35°C. Irrigate cotton rows early morning.',
    'Hold off — pre-monsoon showers likely Friday night at Kottayam. Spray after skies clear.',
    'Deep irrigation this weekend; dry spell continues at Coimbatore for four days.',
    'Yes — gusty afternoon winds forecast Tuesday at Thiruvananthapuram. Support banana and papaya.',
    'Next four days are dry at Kannur — prime window for upland pepper harvest.',
    'No storm warning active for Kottayam. Moderate rain Thursday, 8-12mm expected.',
    'Wait until rain stops Friday, then apply urea to rice fields. Avoid nutrient washout.',
    'Your advisory was delivered yesterday at 6:14 PM IST via SMS to +91 98474 12346.',
    'Chennai this week: 31-34°C with 8mm rainfall Thursday afternoon. Humidity 78-84%.',
    'Boll-worm risk moderate at Salem — scout cotton twice this week, especially after the rain.',
  ]
  const toolNames = ['lookup_station', 'get_forecast', 'get_advisory', 'search_farmer', 'check_delivery']

  const logs: Array<Record<string, any>> = []
  let id = 1
  for (let s = 0; s < sessions.length; s++) {
    const sid = sessions[s]
    for (let m = 0; m < 4; m++) {
      const idx = (s * 4 + m) % userMessages.length
      const base = 6 + s * 8 + m * 2
      logs.push({
        id: id++,
        session_id: sid,
        role: 'user',
        content: userMessages[idx],
        created_at: isoHoursAgo(base + 0.2),
      })
      if (m % 2 === 0) {
        logs.push({
          id: id++,
          session_id: sid,
          role: 'tool_use',
          tool_name: toolNames[(s + m) % toolNames.length],
          content: '',
          created_at: isoHoursAgo(base + 0.15),
        })
      }
      logs.push({
        id: id++,
        session_id: sid,
        role: 'assistant',
        content: assistantMessages[idx],
        created_at: isoHoursAgo(base + 0.1),
      })
    }
  }
  return logs
})()

// ── Delivery metrics aggregate (Pipeline page -> DeliveryFunnelTab) ──

export const DELIVERY_METRICS_AGG: Array<Record<string, any>> = STATIONS.map((s, i) => ({
  station_id: s.id,
  station_name: s.name,
  forecasts_generated: 7,
  advisories_generated: s.active ? 24 + (i % 5) : 12,
  deliveries_attempted: s.active ? 24 + (i % 5) : 12,
  deliveries_succeeded: s.active ? 23 + (i % 5) - (i % 7 === 0 ? 1 : 0) : 11,
}))

// ── Farmers (DPI) ────────────────────────────────────────────

const FARMER_NAMES_ML: Array<{ name: string; local: string }> = [
  { name: 'Suresh Kumar', local: 'സുരേഷ് കുമാര്‍' },
  { name: 'Lakshmi Nair', local: 'ലക്ഷ്മി നായര്‍' },
  { name: 'Rajesh Menon', local: 'രാജേഷ് മേനോന്‍' },
  { name: 'Anitha Pillai', local: 'അനിത പിള്ള' },
  { name: 'Vinod Kurian', local: 'വിനോദ് കുര്യന്‍' },
  { name: 'Priya Varghese', local: 'പ്രിയ വര്‍ഗീസ്' },
  { name: 'Mohanan Namboothiri', local: 'മോഹനന്‍ നമ്പൂതിരി' },
  { name: 'Sreeja Das', local: 'ശ്രീജ ദാസ്' },
  { name: 'Unnikrishnan P.', local: 'ഉണ്ണികൃഷ്ണന്‍ പി' },
  { name: 'Meera Mohan', local: 'മീര മോഹന്‍' },
]

const FARMER_NAMES_TA: Array<{ name: string; local: string }> = [
  { name: 'Karthik Raja', local: 'கார்த்திக் ராஜா' },
  { name: 'Meena Selvam', local: 'மீனா செல்வம்' },
  { name: 'Arun Prakash', local: 'அருண் பிரகாஷ்' },
  { name: 'Kavitha Devi', local: 'கவிதா தேவி' },
  { name: 'Ravi Sundar', local: 'ரவி சுந்தர்' },
  { name: 'Janani Murugan', local: 'ஜனனி முருகன்' },
  { name: 'Senthil Kumar', local: 'செந்தில் குமார்' },
  { name: 'Divya Kannan', local: 'திவ்யா கண்ணன்' },
  { name: 'Pandian Rajan', local: 'பாண்டியன் ராஜன்' },
  { name: 'Thenmozhi S.', local: 'தென்மொழி எஸ்' },
]

export const FARMERS_SUMMARY: FarmerSummary[] = [
  { phone: '+91 98474 12346', name: 'Suresh Kumar', district: 'Kottayam', station_id: 'KL-07', primary_crops: ['rubber', 'pepper'], total_area: 2.1 },
  { phone: '+91 98475 12348', name: 'Lakshmi Nair', district: 'Thiruvananthapuram', station_id: 'KL-01', primary_crops: ['coconut', 'banana'], total_area: 1.7 },
  { phone: '+91 98411 12350', name: 'Rajesh Menon', district: 'Kochi', station_id: 'KL-02', primary_crops: ['rice', 'coconut'], total_area: 1.1 },
  { phone: '+91 98476 12352', name: 'Anitha Pillai', district: 'Kozhikode', station_id: 'KL-05', primary_crops: ['coconut', 'pepper'], total_area: 1.8 },
  { phone: '+91 98477 12354', name: 'Vinod Kurian', district: 'Alappuzha', station_id: 'KL-03', primary_crops: ['rice'], total_area: 0.8 },
  { phone: '+91 98412 12356', name: 'Priya Varghese', district: 'Thrissur', station_id: 'KL-06', primary_crops: ['rice', 'banana'], total_area: 1.5 },
  { phone: '+91 98478 12358', name: 'Mohanan Namboothiri', district: 'Palakkad', station_id: 'KL-08', primary_crops: ['rice', 'coconut', 'sugarcane'], total_area: 3.1 },
  { phone: '+91 98425 12360', name: 'Sreeja Das', district: 'Punalur', station_id: 'KL-09', primary_crops: ['rubber', 'banana'], total_area: 1.4 },
  { phone: '+91 98415 12362', name: 'Unnikrishnan P.', district: 'Nilambur', station_id: 'KL-10', primary_crops: ['rubber', 'teak'], total_area: 3.4 },
  { phone: '+91 98430 12363', name: 'Meera Mohan', district: 'Kannur', station_id: 'KL-04', primary_crops: ['coconut', 'cashew'], total_area: 2.6 },
  { phone: '+91 98412 12345', name: 'Karthik Raja', district: 'Madurai', station_id: 'TN-02', primary_crops: ['cotton', 'banana'], total_area: 1.3 },
  { phone: '+91 98422 12347', name: 'Meena Selvam', district: 'Coimbatore', station_id: 'TN-08', primary_crops: ['cotton', 'maize'], total_area: 0.9 },
  { phone: '+91 98423 12351', name: 'Arun Prakash', district: 'Thanjavur', station_id: 'TN-01', primary_crops: ['rice', 'sugarcane'], total_area: 1.9 },
  { phone: '+91 98431 12353', name: 'Kavitha Devi', district: 'Salem', station_id: 'TN-04', primary_crops: ['cotton', 'turmeric'], total_area: 2.4 },
  { phone: '+91 98413 12355', name: 'Ravi Sundar', district: 'Tiruchirappalli', station_id: 'TN-03', primary_crops: ['rice', 'banana'], total_area: 1.2 },
  { phone: '+91 98424 12357', name: 'Janani Murugan', district: 'Erode', station_id: 'TN-05', primary_crops: ['turmeric', 'cotton'], total_area: 2.2 },
  { phone: '+91 98414 12359', name: 'Senthil Kumar', district: 'Chennai', station_id: 'TN-06', primary_crops: ['rice', 'vegetables'], total_area: 0.7 },
  { phone: '+91 98426 12361', name: 'Divya Kannan', district: 'Tirunelveli', station_id: 'TN-07', primary_crops: ['rice', 'cotton'], total_area: 2.0 },
  { phone: '+91 98427 12364', name: 'Pandian Rajan', district: 'Vellore', station_id: 'TN-09', primary_crops: ['rice', 'groundnut'], total_area: 1.6 },
  { phone: '+91 98428 12365', name: 'Thenmozhi S.', district: 'Nagapattinam', station_id: 'TN-10', primary_crops: ['rice', 'coconut'], total_area: 1.9 },
]

export const FARMERS_DETAIL_BY_PHONE: Record<string, FarmerDetail> = {}
for (const f of FARMERS_SUMMARY) {
  const station = stationMeta(f.station_id)
  const isMl = station?.language === 'ml'
  const localName = isMl
    ? FARMER_NAMES_ML.find((n) => n.name === f.name)?.local ?? f.name
    : FARMER_NAMES_TA.find((n) => n.name === f.name)?.local ?? f.name
  const coords = stationCoords(f.station_id)
  FARMERS_DETAIL_BY_PHONE[f.phone] = {
    aadhaar: {
      name: f.name,
      name_local: localName,
      phone: f.phone,
      district: f.district,
      state: station?.state ?? '',
      language: station?.language ?? 'en',
    },
    primary_crops: f.primary_crops,
    total_area: f.total_area,
    land_records: [
      {
        survey_number: `${f.station_id}-${(Math.abs(hash(f.phone)) % 900) + 100}/${(Math.abs(hash(f.phone + 'b')) % 12) + 1}`,
        area_hectares: +(f.total_area * 0.62).toFixed(2),
        soil_type: isMl ? 'lateritic clay loam' : 'red sandy loam',
        irrigation_type: f.primary_crops.includes('rice') ? 'canal' : 'borewell',
        gps_lat: coords.lat + 0.01,
        gps_lon: coords.lon - 0.01,
      },
      {
        survey_number: `${f.station_id}-${(Math.abs(hash(f.phone + 'c')) % 900) + 100}/${(Math.abs(hash(f.phone + 'd')) % 12) + 1}`,
        area_hectares: +(f.total_area * 0.38).toFixed(2),
        soil_type: isMl ? 'alluvial' : 'black cotton',
        irrigation_type: 'rainfed',
        gps_lat: coords.lat - 0.008,
        gps_lon: coords.lon + 0.012,
      },
    ],
    soil_health: {
      pH: +(6.2 + (Math.abs(hash(f.phone)) % 18) / 20).toFixed(1),
      classification: 'medium',
      nitrogen_kg_ha: 180 + (Math.abs(hash(f.phone)) % 120),
      phosphorus_kg_ha: 22 + (Math.abs(hash(f.phone)) % 18),
      potassium_kg_ha: 140 + (Math.abs(hash(f.phone)) % 90),
      organic_carbon_pct: +(0.48 + (Math.abs(hash(f.phone)) % 40) / 100).toFixed(2),
    },
    pmkisan: { installments_received: 14, total_amount: 28000 },
    pmfby: { status: 'enrolled', sum_insured: 42500, premium_paid: 741 },
    kcc: { credit_limit: 112000, outstanding: 34800, repayment_status: 'current' },
  }
}
