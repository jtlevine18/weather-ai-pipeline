import type { VercelRequest, VercelResponse } from '@vercel/node'
import { neon } from '@neondatabase/serverless'

export default async function handler(req: VercelRequest, res: VercelResponse) {
  const phone = typeof req.query.phone === 'string' ? decodeURIComponent(req.query.phone) : ''
  if (!phone) {
    return res.status(400).json({ error: 'phone required' })
  }

  try {
    const sql = neon(process.env.DATABASE_URL!)
    const rows = (await sql`
      SELECT profile_json FROM farmer_profiles WHERE phone = ${phone} LIMIT 1
    `) as Array<{ profile_json: string | null }>

    if (rows.length === 0 || !rows[0].profile_json) {
      return res.status(404).json({ error: `Farmer ${phone} not found` })
    }
    return res.json(JSON.parse(rows[0].profile_json))
  } catch (err) {
    return res.status(500).json({ error: String(err) })
  }
}
