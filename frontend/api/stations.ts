import type { VercelRequest, VercelResponse } from '@vercel/node'
import { neon } from '@neondatabase/serverless'

const STATIONS = [
  { id: "KL_TVM", name: "Thiruvananthapuram", lat: 8.4833, lon: 76.95, state: "Kerala", altitude_m: 60 },
  { id: "KL_COK", name: "Kochi", lat: 9.95, lon: 76.2667, state: "Kerala", altitude_m: 1 },
  { id: "KL_ALP", name: "Alappuzha", lat: 9.55, lon: 76.4167, state: "Kerala", altitude_m: 2 },
  { id: "KL_KNR", name: "Kannur", lat: 11.8333, lon: 75.3333, state: "Kerala", altitude_m: 11 },
  { id: "KL_KZD", name: "Kozhikode", lat: 11.25, lon: 75.7833, state: "Kerala", altitude_m: 4 },
  { id: "KL_TCR", name: "Thrissur", lat: 10.5167, lon: 76.2167, state: "Kerala", altitude_m: 40 },
  { id: "KL_KTM", name: "Kottayam", lat: 9.5833, lon: 76.5167, state: "Kerala", altitude_m: 39 },
  { id: "KL_PKD", name: "Palakkad", lat: 10.7667, lon: 76.65, state: "Kerala", altitude_m: 95 },
  { id: "KL_PNL", name: "Punalur", lat: 9.0, lon: 76.9167, state: "Kerala", altitude_m: 33 },
  { id: "KL_NLB", name: "Nilambur", lat: 11.28, lon: 76.23, state: "Kerala", altitude_m: 30 },
  { id: "TN_TNJ", name: "Thanjavur", lat: 10.7833, lon: 79.1333, state: "Tamil Nadu", altitude_m: 0 },
  { id: "TN_MDU", name: "Madurai", lat: 9.8333, lon: 78.0833, state: "Tamil Nadu", altitude_m: 139 },
  { id: "TN_TRZ", name: "Tiruchirappalli", lat: 10.7667, lon: 78.7167, state: "Tamil Nadu", altitude_m: 85 },
  { id: "TN_SLM", name: "Salem", lat: 11.65, lon: 78.1667, state: "Tamil Nadu", altitude_m: 279 },
  { id: "TN_ERD", name: "Erode", lat: 11.34, lon: 77.72, state: "Tamil Nadu", altitude_m: 183 },
  { id: "TN_CHN", name: "Chennai", lat: 13.0, lon: 80.1833, state: "Tamil Nadu", altitude_m: 10 },
  { id: "TN_TNV", name: "Tirunelveli", lat: 8.7333, lon: 77.75, state: "Tamil Nadu", altitude_m: 45 },
  { id: "TN_CBE", name: "Coimbatore", lat: 11.0333, lon: 77.05, state: "Tamil Nadu", altitude_m: 396 },
  { id: "TN_VLR", name: "Vellore", lat: 12.92, lon: 79.13, state: "Tamil Nadu", altitude_m: 215 },
  { id: "TN_NGP", name: "Nagappattinam", lat: 10.7667, lon: 79.85, state: "Tamil Nadu", altitude_m: 2 },
]

const STATION_MAP: Record<string, (typeof STATIONS)[number]> = Object.fromEntries(
  STATIONS.map((s) => [s.id, s])
)

export default async function handler(req: VercelRequest, res: VercelResponse) {
  const id = typeof req.query.id === 'string' ? req.query.id : undefined

  if (!id) {
    return res.json(STATIONS)
  }

  const station = STATION_MAP[id]
  if (!station) {
    return res.status(404).json({ error: `Station ${id} not found` })
  }

  const base = {
    station_id: id,
    station_name: station.name,
    state: station.state,
    latitude: station.lat,
    longitude: station.lon,
  }

  try {
    const sql = neon(process.env.DATABASE_URL!)
    const rows = (await sql`
      SELECT temperature, humidity, wind_speed, rainfall, quality_score, source, ts
      FROM clean_telemetry
      WHERE station_id = ${id}
      ORDER BY ts DESC
      LIMIT 1
    `) as Array<Record<string, any>>

    const latest = rows[0]
    if (!latest) return res.json(base)

    return res.json({
      ...base,
      temperature: latest.temperature ?? undefined,
      humidity: latest.humidity ?? undefined,
      rainfall_mm: latest.rainfall ?? undefined,
      wind_speed: latest.wind_speed ?? undefined,
      quality_score: latest.quality_score ?? undefined,
      observed_at: latest.ts ?? undefined,
      source: latest.source ?? undefined,
    })
  } catch {
    return res.json(base)
  }
}
