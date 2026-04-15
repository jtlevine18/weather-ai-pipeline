import type { VercelRequest, VercelResponse } from '@vercel/node'
import { neon } from '@neondatabase/serverless'

export default async function handler(req: VercelRequest, res: VercelResponse) {
  const sql = neon(process.env.DATABASE_URL!)
  const mode = req.query.mode || 'log'
  const limit = Math.min(Number(req.query.limit) || 100, 2500)

  if (mode === 'metrics') {
    const rows = await sql`SELECT * FROM delivery_metrics ORDER BY created_at DESC LIMIT ${limit}`
    return res.json(rows)
  }

  // Total rows delivered during the most recent pipeline run. Delivery_log
  // has no pipeline_run_id column, so we scope by delivered_at falling within
  // an hour of the latest row — the pipeline finishes well under that window.
  if (mode === 'count') {
    const rows = (await sql`
      SELECT COUNT(*)::int AS count
      FROM delivery_log
      WHERE delivered_at >= (
        SELECT COALESCE(MAX(delivered_at), NOW()) - INTERVAL '1 hour'
        FROM delivery_log
      )
    `) as Array<{ count: number }>
    return res.json({ count: rows[0]?.count ?? 0 })
  }

  // Per-station counts for the most recent run — used for the "2,000 across
  // 20 stations" distribution strip on the Advisories page.
  if (mode === 'by_station') {
    const rows = await sql`
      SELECT station_id, COUNT(*)::int AS count
      FROM delivery_log
      WHERE delivered_at >= (
        SELECT COALESCE(MAX(delivered_at), NOW()) - INTERVAL '1 hour'
        FROM delivery_log
      )
      GROUP BY station_id
      ORDER BY count DESC
    `
    return res.json(rows)
  }

  // Sample N real farmers per station from the most recent run, joined with
  // farmer_profiles so the UI can show "Lakshmi Nair (paddy, banana) →
  // <actual Malayalam SMS she received>". Falls back to the raw delivery row
  // when the farmer is not in the cached profile table.
  if (mode === 'samples') {
    const stationId = typeof req.query.station_id === 'string' ? req.query.station_id : ''
    const perStation = Math.min(Math.max(Number(req.query.per_station) || 3, 1), 10)

    if (stationId) {
      const rows = await sql`
        SELECT dl.recipient, dl.sms_text, dl.message, dl.delivered_at,
               fp.name, fp.primary_crops, fp.district
        FROM delivery_log dl
        LEFT JOIN farmer_profiles fp ON dl.recipient = fp.phone
        WHERE dl.station_id = ${stationId}
          AND dl.delivered_at >= (
            SELECT COALESCE(MAX(delivered_at), NOW()) - INTERVAL '1 hour'
            FROM delivery_log
          )
        ORDER BY dl.delivered_at DESC
        LIMIT ${perStation}
      `
      return res.json(rows)
    }

    // No station filter → return N per station across the whole run in one
    // payload using ROW_NUMBER(). Used only if a consumer wants all samples
    // eager-loaded; the Advisories page uses the station-filtered branch.
    const rows = await sql`
      WITH recent AS (
        SELECT dl.station_id, dl.recipient, dl.sms_text, dl.message, dl.delivered_at,
               fp.name, fp.primary_crops, fp.district,
               ROW_NUMBER() OVER (PARTITION BY dl.station_id ORDER BY dl.delivered_at DESC) AS rn
        FROM delivery_log dl
        LEFT JOIN farmer_profiles fp ON dl.recipient = fp.phone
        WHERE dl.delivered_at >= (
          SELECT COALESCE(MAX(delivered_at), NOW()) - INTERVAL '1 hour'
          FROM delivery_log
        )
      )
      SELECT * FROM recent WHERE rn <= ${perStation}
      ORDER BY station_id, rn
    `
    return res.json(rows)
  }

  const rows = await sql`SELECT * FROM delivery_log ORDER BY delivered_at DESC LIMIT ${limit}`
  return res.json(rows)
}
