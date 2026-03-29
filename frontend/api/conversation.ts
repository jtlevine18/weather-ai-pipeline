import type { VercelRequest, VercelResponse } from '@vercel/node'
import { neon } from '@neondatabase/serverless'

export default async function handler(req: VercelRequest, res: VercelResponse) {
  try {
    const sql = neon(process.env.DATABASE_URL!)
    const limit = Math.min(Number(req.query.limit) || 50, 500)
    const rows = await sql`SELECT * FROM conversation_log ORDER BY created_at DESC LIMIT ${limit}`
    return res.json(rows)
  } catch {
    return res.json([])
  }
}
