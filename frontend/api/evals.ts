import type { VercelRequest, VercelResponse } from '@vercel/node'
import { neon } from '@neondatabase/serverless'

export default async function handler(_req: VercelRequest, res: VercelResponse) {
  const sql = neon(process.env.DATABASE_URL!)
  const results: Record<string, any> = {}

  try {
    // Healing quality — from healing_log
    const healAssessments = await sql`
      SELECT assessment, COUNT(*)::int AS count,
             AVG(quality_score)::float AS avg_quality
      FROM healing_log GROUP BY assessment ORDER BY count DESC
    `
    const healTools = await sql`
      SELECT unnest(tools_used) AS tool, COUNT(*)::int AS count
      FROM healing_log WHERE tools_used IS NOT NULL
      GROUP BY tool ORDER BY count DESC
    `
    const healTotal = await sql`SELECT COUNT(*)::int AS c FROM healing_log`
    results.healing = {
      total_readings: healTotal[0]?.c ?? 0,
      assessment_distribution: Object.fromEntries(
        healAssessments.map((r: any) => [r.assessment, { count: r.count, avg_quality: r.avg_quality }])
      ),
      tool_usage: Object.fromEntries(healTools.map((r: any) => [r.tool, r.count])),
    }
  } catch {}

  try {
    // Forecast accuracy — join forecasts with clean_telemetry
    const pairs = await sql`
      SELECT
        f.model_used,
        f.temperature AS fc_temp,
        c.temperature AS obs_temp,
        f.rainfall AS fc_rain,
        c.rainfall AS obs_rain
      FROM forecasts f
      INNER JOIN clean_telemetry c
        ON f.station_id = c.station_id
        AND date_trunc('day', f.valid_for_ts) = date_trunc('day', c.ts)
        AND COALESCE(f.forecast_day, 0) = 0
      WHERE f.temperature IS NOT NULL AND c.temperature IS NOT NULL
    `
    if (pairs.length > 0) {
      const errors = pairs.map((p: any) => Math.abs(p.fc_temp - p.obs_temp))
      const mae = errors.reduce((s: number, e: number) => s + e, 0) / errors.length
      const rmse = Math.sqrt(errors.reduce((s: number, e: number) => s + e * e, 0) / errors.length)

      // By model type
      const byModel: Record<string, { errors: number[]; count: number }> = {}
      for (const p of pairs) {
        const m = (p as any).model_used || 'unknown'
        if (!byModel[m]) byModel[m] = { errors: [], count: 0 }
        byModel[m].errors.push(Math.abs((p as any).fc_temp - (p as any).obs_temp))
        byModel[m].count++
      }
      const modelStats = Object.fromEntries(
        Object.entries(byModel).map(([m, d]) => [m, {
          count: d.count,
          mae: d.errors.reduce((s, e) => s + e, 0) / d.errors.length,
          rmse: Math.sqrt(d.errors.reduce((s, e) => s + e * e, 0) / d.errors.length),
        }])
      )

      results.forecast = {
        total_pairs: pairs.length,
        temperature_mae: Math.round(mae * 100) / 100,
        temperature_rmse: Math.round(rmse * 100) / 100,
        by_model: modelStats,
      }
    }
  } catch {}

  try {
    // Farmer profile coverage
    const stationCount = await sql`SELECT COUNT(DISTINCT station_id)::int AS c FROM clean_telemetry`
    results.farmer_profiles = {
      stations_covered: stationCount[0]?.c ?? 0,
      total_stations: 20,
    }
  } catch {}

  try {
    // Delivery success rate
    const delivery = await sql`
      SELECT status, COUNT(*)::int AS count
      FROM delivery_log GROUP BY status
    `
    results.delivery = {
      by_status: Object.fromEntries(delivery.map((r: any) => [r.status, r.count])),
      total: delivery.reduce((s: number, r: any) => s + r.count, 0),
    }
  } catch {}

  try {
    // Advisory coverage
    const advisories = await sql`
      SELECT language, COUNT(*)::int AS count
      FROM agricultural_alerts GROUP BY language
    `
    results.advisories = {
      by_language: Object.fromEntries(advisories.map((r: any) => [r.language, r.count])),
      total: advisories.reduce((s: number, r: any) => s + r.count, 0),
    }
  } catch {}

  return res.json(results)
}
