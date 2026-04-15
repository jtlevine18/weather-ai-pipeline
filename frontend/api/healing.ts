import type { VercelRequest, VercelResponse } from '@vercel/node'
import { neon } from '@neondatabase/serverless'

export default async function handler(req: VercelRequest, res: VercelResponse) {
  try {
    const sql = neon(process.env.DATABASE_URL!)
    const mode = req.query.mode || 'log'

    if (mode === 'stats') {
      const assessments = await sql`SELECT assessment, COUNT(*)::int AS count FROM healing_log GROUP BY assessment ORDER BY count DESC`
      // tools_used is stored as a comma-separated VARCHAR, not a Postgres array,
      // so split it before unnest.
      const tools = await sql`
        SELECT tool, COUNT(*)::int AS count
        FROM (
          SELECT trim(unnest(string_to_array(tools_used, ','))) AS tool
          FROM healing_log
          WHERE tools_used IS NOT NULL AND tools_used <> ''
        ) t
        WHERE tool <> ''
        GROUP BY tool
        ORDER BY count DESC
      `
      const latest = await sql`SELECT * FROM healing_log ORDER BY created_at DESC LIMIT 1`
      return res.json({
        assessment_distribution: assessments,
        tool_usage: tools,
        latest_run: latest[0] ?? null,
        total_healed: assessments.reduce((s: number, r: any) => s + r.count, 0),
      })
    }

    const limit = Math.min(Number(req.query.limit) || 100, 500)
    const rows = await sql`SELECT * FROM healing_log ORDER BY created_at DESC LIMIT ${limit}`
    return res.json(rows)
  } catch (e: any) {
    return res.status(500).json({ error: e?.message ?? String(e) })
  }
}
