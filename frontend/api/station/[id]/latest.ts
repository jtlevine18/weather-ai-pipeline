import type { VercelRequest, VercelResponse } from '@vercel/node'
import { neon } from '@neondatabase/serverless'

const STATIONS: Record<string, { name: string; state: string; lat: number; lon: number }> = {
  KL_TVM: { name: 'Thiruvananthapuram', state: 'Kerala', lat: 8.4833, lon: 76.95 },
  KL_COK: { name: 'Kochi', state: 'Kerala', lat: 9.95, lon: 76.2667 },
  KL_ALP: { name: 'Alappuzha', state: 'Kerala', lat: 9.55, lon: 76.4167 },
  KL_KNR: { name: 'Kannur', state: 'Kerala', lat: 11.8333, lon: 75.3333 },
  KL_KZD: { name: 'Kozhikode', state: 'Kerala', lat: 11.25, lon: 75.7833 },
  KL_TCR: { name: 'Thrissur', state: 'Kerala', lat: 10.5167, lon: 76.2167 },
  KL_KTM: { name: 'Kottayam', state: 'Kerala', lat: 9.5833, lon: 76.5167 },
  KL_PKD: { name: 'Palakkad', state: 'Kerala', lat: 10.7667, lon: 76.65 },
  KL_PNL: { name: 'Punalur', state: 'Kerala', lat: 9.0, lon: 76.9167 },
  KL_NLB: { name: 'Nilambur', state: 'Kerala', lat: 11.28, lon: 76.23 },
  TN_TNJ: { name: 'Thanjavur', state: 'Tamil Nadu', lat: 10.7833, lon: 79.1333 },
  TN_MDU: { name: 'Madurai', state: 'Tamil Nadu', lat: 9.8333, lon: 78.0833 },
  TN_TRZ: { name: 'Tiruchirappalli', state: 'Tamil Nadu', lat: 10.7667, lon: 78.7167 },
  TN_SLM: { name: 'Salem', state: 'Tamil Nadu', lat: 11.65, lon: 78.1667 },
  TN_ERD: { name: 'Erode', state: 'Tamil Nadu', lat: 11.34, lon: 77.72 },
  TN_CHN: { name: 'Chennai', state: 'Tamil Nadu', lat: 13.0, lon: 80.1833 },
  TN_TNV: { name: 'Tirunelveli', state: 'Tamil Nadu', lat: 8.7333, lon: 77.75 },
  TN_CBE: { name: 'Coimbatore', state: 'Tamil Nadu', lat: 11.0333, lon: 77.05 },
  TN_VLR: { name: 'Vellore', state: 'Tamil Nadu', lat: 12.92, lon: 79.13 },
  TN_NGP: { name: 'Nagappattinam', state: 'Tamil Nadu', lat: 10.7667, lon: 79.85 },
}

export default async function handler(req: VercelRequest, res: VercelResponse) {
  const id = typeof req.query.id === 'string' ? req.query.id : ''
  const station = STATIONS[id]
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
