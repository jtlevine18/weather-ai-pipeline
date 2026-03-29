import type { VercelRequest, VercelResponse } from '@vercel/node'
import { neon } from '@neondatabase/serverless'

export default async function handler(_req: VercelRequest, res: VercelResponse) {
  try {
    const url = process.env.DATABASE_URL
    if (!url) return res.json({ error: 'DATABASE_URL not set' })
    // Mask the password in the response
    const masked = url.replace(/:([^@]+)@/, ':***@')
    const sql = neon(url)
    const rows = await sql`SELECT COUNT(*)::int AS c FROM pipeline_runs`
    return res.json({ ok: true, url: masked, rows })
  } catch (err: any) {
    return res.status(500).json({ error: err.message, stack: err.stack?.split('\n').slice(0, 3) })
  }
}
