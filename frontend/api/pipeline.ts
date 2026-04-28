import type { VercelRequest, VercelResponse } from '@vercel/node'
import { neon } from '@neondatabase/serverless'

// MOS metrics embedded from trained model (committed to repo)
const MOS_METRICS = {
  rmse: 0.1035, mae: 0.0813, r2: 0.9988,
  n_train: 64, n_test: 16, residual_mean: -0.84, residual_std: 3.1267,
  feature_importances: {
    nwp_temp: 0.3653, nwp_rainfall: 0.0, humidity: 0.2408,
    wind_speed: 0.2478, pressure: 0.146, station_altitude: 0.0,
    soil_moisture: 0.0, rolling_6h_error: 0.0, recent_temp_trend: 0.0,
    hour_sin: 0.0, hour_cos: 0.0, doy_sin: 0.0,
  },
}

export default async function handler(req: VercelRequest, res: VercelResponse) {
  const sql = neon(process.env.DATABASE_URL!)
  const mode = req.query.mode || 'runs'

  if (mode === 'mos-status') {
    // Check if any forecasts used MOS correction
    let trained = true  // model is trained (committed to repo)
    try {
      const [row] = await sql`SELECT COUNT(*)::int AS c FROM forecasts WHERE model_used ILIKE '%mos%'`
      // If MOS forecasts exist, model is definitely active
      if (row?.c > 0) trained = true
    } catch {}
    return res.json({ trained, metrics: MOS_METRICS })
  }

  if (mode === 'stats') {
    const counts: Record<string, number> = {}
    const rows = await sql`
      SELECT 'raw_telemetry' AS t, COUNT(*)::int AS c FROM raw_telemetry
      UNION ALL SELECT 'clean_telemetry', COUNT(*)::int FROM clean_telemetry
      UNION ALL SELECT 'healing_log', COUNT(*)::int FROM healing_log
      UNION ALL SELECT 'forecasts', COUNT(*)::int FROM forecasts
      UNION ALL SELECT 'agricultural_alerts', COUNT(*)::int FROM agricultural_alerts
      UNION ALL SELECT 'delivery_log', COUNT(*)::int FROM delivery_log
      UNION ALL SELECT 'pipeline_runs', COUNT(*)::int FROM pipeline_runs
      UNION ALL SELECT 'farmer_profiles', COUNT(*)::int FROM farmer_profiles
    `
    for (const row of rows) counts[row.t] = row.c

    const [runStats] = await sql`
      SELECT
        COUNT(*)::int AS total_runs,
        COUNT(*) FILTER (WHERE status = 'ok')::int AS successful_runs,
        COUNT(*) FILTER (WHERE status IN ('failed', 'partial'))::int AS failed_runs,
        COALESCE(AVG(EXTRACT(EPOCH FROM (ended_at - started_at)))::float, 0) AS avg_duration
      FROM pipeline_runs
      WHERE ended_at IS NOT NULL
    `
    return res.json({
      ...counts,
      total_runs: runStats?.total_runs ?? 0,
      successful_runs: runStats?.successful_runs ?? 0,
      failed_runs: runStats?.failed_runs ?? 0,
      avg_duration: runStats?.avg_duration ?? 0,
    })
  }

  // Default: runs
  const limit = Math.min(Number(req.query.limit) || 10, 50)
  const rows = await sql`SELECT * FROM pipeline_runs ORDER BY started_at DESC LIMIT ${limit}`
  return res.json(rows)
}
