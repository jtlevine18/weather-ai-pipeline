import type { VercelRequest, VercelResponse } from '@vercel/node'
import { neon } from '@neondatabase/serverless'

export default async function handler(_req: VercelRequest, res: VercelResponse) {
  const sql = neon(process.env.DATABASE_URL!)
  const rows = await sql`SELECT source, COUNT(*)::int AS count FROM raw_telemetry GROUP BY source`
  return res.json(rows)
}
