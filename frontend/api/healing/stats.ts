import type { VercelRequest, VercelResponse } from '@vercel/node'
import { getSQL } from '../_db'

export default async function handler(_req: VercelRequest, res: VercelResponse) {
  res.setHeader('Access-Control-Allow-Origin', '*')
  const sql = getSQL()

  const assessments = await sql`
    SELECT assessment, COUNT(*)::int AS count
    FROM healing_log GROUP BY assessment ORDER BY count DESC
  `
  const tools = await sql`
    SELECT unnest(tools_used) AS tool, COUNT(*)::int AS count
    FROM healing_log WHERE tools_used IS NOT NULL GROUP BY tool ORDER BY count DESC
  `
  const latest = await sql`
    SELECT * FROM healing_log ORDER BY created_at DESC LIMIT 1
  `

  res.json({
    assessment_distribution: assessments,
    tool_usage: tools,
    latest_run: latest[0] ?? null,
    total_healed: assessments.reduce((s: number, r: any) => s + r.count, 0),
  })
}
