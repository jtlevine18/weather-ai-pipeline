import type { VercelRequest, VercelResponse } from '@vercel/node'
import { neon } from '@neondatabase/serverless'

export default async function handler(req: VercelRequest, res: VercelResponse) {
  const phone = typeof req.query.phone === 'string' ? decodeURIComponent(req.query.phone) : undefined
  const sql = neon(process.env.DATABASE_URL!)

  if (phone) {
    try {
      const rows = (await sql`
        SELECT primary_crops, total_area, profile_json
        FROM farmer_profiles
        WHERE phone = ${phone}
        LIMIT 1
      `) as Array<{ primary_crops: string | null; total_area: number | null; profile_json: string | null }>

      if (rows.length === 0 || !rows[0].profile_json) {
        return res.status(404).json({ error: `Farmer ${phone} not found` })
      }

      const row = rows[0]
      const profile = JSON.parse(row.profile_json!)

      let primaryCrops: string[] = []
      try {
        primaryCrops = row.primary_crops ? JSON.parse(row.primary_crops) : []
      } catch {
        primaryCrops =
          typeof row.primary_crops === 'string'
            ? row.primary_crops.split(',').map((s: string) => s.trim()).filter(Boolean)
            : []
      }

      return res.json({
        ...profile,
        primary_crops: primaryCrops,
        total_area: Number(row.total_area ?? 0),
      })
    } catch (err) {
      return res.status(500).json({ error: String(err) })
    }
  }

  try {
    const rows = await sql`SELECT * FROM farmer_profiles ORDER BY created_at DESC`
    return res.json(rows)
  } catch {
    return res.json([])
  }
}
