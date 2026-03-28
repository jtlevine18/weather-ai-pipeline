import type { VercelRequest, VercelResponse } from '@vercel/node'
import { getSQL } from '../_db'

export default async function handler(req: VercelRequest, res: VercelResponse) {
  res.setHeader('Access-Control-Allow-Origin', '*')
  const limit = Math.min(Number(req.query.limit) || 50, 500)
  const sql = getSQL()
  try {
    const rows = await sql`SELECT * FROM conversation_log ORDER BY created_at DESC LIMIT ${limit}`
    res.json(rows)
  } catch {
    res.json([])
  }
}
