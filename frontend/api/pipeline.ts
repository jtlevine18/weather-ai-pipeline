import type { VercelRequest, VercelResponse } from '@vercel/node'
import { neon } from '@neondatabase/serverless'
import { readFileSync, existsSync } from 'fs'
import { join } from 'path'

export default async function handler(req: VercelRequest, res: VercelResponse) {
  const mode = req.query.mode || 'runs'

  if (mode === 'mos-status') {
    // Check for committed metrics file
    let trained = false
    let metrics = null
    for (const base of [process.cwd(), join(process.cwd(), '..'), '/var/task']) {
      const mp = join(base, 'metrics', 'mos_metrics.json')
      if (existsSync(mp)) {
        try {
          metrics = JSON.parse(readFileSync(mp, 'utf-8'))
          trained = true
          break
        } catch {}
      }
    }
    // Fallback: check DB for MOS-corrected forecasts
    if (!trained) {
      try {
        const sql = neon(process.env.DATABASE_URL!)
        const [row] = await sql`SELECT COUNT(*)::int AS c FROM forecasts WHERE model_used ILIKE '%mos%'`
        if (row?.c > 0) trained = true
      } catch {}
    }
    return res.json({ trained, metrics })
  }

  if (mode === 'stats') {
    const sql = neon(process.env.DATABASE_URL!)
    const tables = ['raw_telemetry', 'clean_telemetry', 'healing_log', 'forecasts', 'agricultural_alerts', 'delivery_log', 'pipeline_runs']
    const counts: Record<string, number> = {}
    for (const t of tables) {
      const [row] = await sql(`SELECT COUNT(*)::int AS c FROM ${t}`)
      counts[t] = row?.c ?? 0
    }
    return res.json(counts)
  }

  // Default: runs
  const sql = neon(process.env.DATABASE_URL!)
  const limit = Math.min(Number(req.query.limit) || 10, 50)
  const rows = await sql`SELECT * FROM pipeline_runs ORDER BY started_at DESC LIMIT ${limit}`
  return res.json(rows)
}
