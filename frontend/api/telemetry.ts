import type { VercelRequest, VercelResponse } from '@vercel/node'
import { neon } from '@neondatabase/serverless'

export default async function handler(req: VercelRequest, res: VercelResponse) {
  const sql = neon(process.env.DATABASE_URL!)
  const limit = Math.min(Number(req.query.limit) || 200, 500)
  const type = req.query.type || 'clean'
  const table = type === 'raw' ? 'raw_telemetry' : 'clean_telemetry'
  const rows = await sql(`SELECT * FROM ${table} ORDER BY ts DESC LIMIT $1`, [limit])
  return res.json(rows)
}
