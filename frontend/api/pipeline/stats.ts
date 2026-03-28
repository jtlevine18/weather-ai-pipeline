import type { VercelRequest, VercelResponse } from '@vercel/node'
import { getSQL } from '../_db'

export default async function handler(_req: VercelRequest, res: VercelResponse) {
  res.setHeader('Access-Control-Allow-Origin', '*')
  const sql = getSQL()
  const tables = ['raw_telemetry', 'clean_telemetry', 'healing_log', 'forecasts', 'agricultural_alerts', 'delivery_log', 'pipeline_runs']
  const counts: Record<string, number> = {}
  for (const table of tables) {
    const [row] = await sql`SELECT COUNT(*)::int AS c FROM ${sql(table)}`
    counts[table] = row?.c ?? 0
  }
  res.json(counts)
}
