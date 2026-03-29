import type { VercelRequest, VercelResponse } from '@vercel/node'
import { neon } from '@neondatabase/serverless'

export default async function handler(_req: VercelRequest, res: VercelResponse) {
  try {
    const sql = neon(process.env.DATABASE_URL!)
    const rows = await sql`SELECT * FROM farmer_profiles ORDER BY created_at DESC`
    return res.json(rows)
  } catch {
    return res.json([])
  }
}
