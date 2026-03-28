import type { VercelRequest, VercelResponse } from '@vercel/node'
import { getSQL } from './_db'

export default async function handler(_req: VercelRequest, res: VercelResponse) {
  res.setHeader('Access-Control-Allow-Origin', '*')
  const sql = getSQL()
  const rows = await sql`SELECT source, COUNT(*)::int AS count FROM raw_telemetry GROUP BY source`
  res.json(rows)
}
