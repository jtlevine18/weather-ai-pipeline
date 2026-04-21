import type { VercelRequest, VercelResponse } from '@vercel/node'
import { neon } from '@neondatabase/serverless'

export default async function handler(req: VercelRequest, res: VercelResponse) {
  const sql = neon(process.env.DATABASE_URL!)
  const limit = Math.min(Number(req.query.limit) || 50, 500)
  // Explicit SELECT so probabilistic columns (added in Phase 2 schema
  // migration) flow through even when the row shape changes. Existing
  // consumers reading the scalar `rainfall`, `temperature`, etc. are
  // unaffected. All `rain_p*` / `rain_prob_*` / `ensemble_size` /
  // `nwp_model_version` columns are nullable — historical rows render
  // identically to pre-hybrid behavior.
  const rows = await sql`
    SELECT
      id,
      station_id,
      issued_at,
      valid_for_ts,
      forecast_day,
      temperature,
      humidity,
      wind_speed,
      rainfall,
      condition,
      model_used,
      nwp_source,
      nwp_temp,
      correction,
      confidence,
      created_at,
      rain_p10,
      rain_p50,
      rain_p90,
      rain_prob_1mm,
      rain_prob_5mm,
      rain_prob_15mm,
      ensemble_size,
      nwp_model_version
    FROM forecasts
    ORDER BY issued_at DESC
    LIMIT ${limit}
  `
  return res.json(rows)
}
