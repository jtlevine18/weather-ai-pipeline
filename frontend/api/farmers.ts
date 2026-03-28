import type { VercelRequest, VercelResponse } from '@vercel/node'
import { getSQL } from './_db'

export default async function handler(_req: VercelRequest, res: VercelResponse) {
  res.setHeader('Access-Control-Allow-Origin', '*')
  const sql = getSQL()
  try {
    const rows = await sql`SELECT * FROM farmer_profiles ORDER BY created_at DESC`
    res.json(rows)
  } catch {
    // Table might not exist — return empty
    res.json([])
  }
}
