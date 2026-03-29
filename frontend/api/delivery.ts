import type { VercelRequest, VercelResponse } from '@vercel/node'
import { neon } from '@neondatabase/serverless'

export default async function handler(req: VercelRequest, res: VercelResponse) {
  const sql = neon(process.env.DATABASE_URL!)
  const mode = req.query.mode || 'log'
  const limit = Math.min(Number(req.query.limit) || 100, 500)

  if (mode === 'metrics') {
    const rows = await sql`SELECT * FROM delivery_metrics ORDER BY created_at DESC LIMIT ${limit}`
    return res.json(rows)
  }

  const rows = await sql`SELECT * FROM delivery_log ORDER BY delivered_at DESC LIMIT ${limit}`
  return res.json(rows)
}
