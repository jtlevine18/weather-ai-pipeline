import type { VercelRequest, VercelResponse } from '@vercel/node'
import { getSQL } from './_db'

export default async function handler(req: VercelRequest, res: VercelResponse) {
  res.setHeader('Access-Control-Allow-Origin', '*')
  const limit = Math.min(Number(req.query.limit) || 50, 500)
  const sql = getSQL()
  const rows = await sql`SELECT * FROM forecasts ORDER BY issued_at DESC LIMIT ${limit}`
  res.json(rows)
}
