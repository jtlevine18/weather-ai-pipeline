import type { VercelRequest, VercelResponse } from '@vercel/node'
import { neon } from '@neondatabase/serverless'

export default async function handler(req: VercelRequest, res: VercelResponse) {
  const sql = neon(process.env.DATABASE_URL!)
  const limit = Math.min(Number(req.query.limit) || 200, 500)
  const type = req.query.type

  if (type === 'raw') {
    const rows = await sql`SELECT * FROM raw_telemetry ORDER BY ts DESC LIMIT ${limit}`
    return res.json(rows)
  }

  const rows = await sql`SELECT * FROM clean_telemetry ORDER BY ts DESC LIMIT ${limit}`
  return res.json(rows)
}
