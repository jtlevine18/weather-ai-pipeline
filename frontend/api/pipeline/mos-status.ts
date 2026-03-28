import type { VercelRequest, VercelResponse } from '@vercel/node'
import { readFileSync, existsSync } from 'fs'
import { join } from 'path'

export default function handler(_req: VercelRequest, res: VercelResponse) {
  res.setHeader('Access-Control-Allow-Origin', '*')
  // MOS metrics are committed to the repo — read from static file
  const metricsPath = join(process.cwd(), '..', 'metrics', 'mos_metrics.json')
  const modelPath = join(process.cwd(), '..', 'models', 'hybrid_mos.json')

  let trained = false
  let metrics = null

  // Try multiple paths since Vercel's cwd may vary
  for (const base of [join(process.cwd(), '..'), process.cwd(), '/var/task']) {
    const mp = join(base, 'metrics', 'mos_metrics.json')
    const mdl = join(base, 'models', 'hybrid_mos.json')
    if (existsSync(mp)) {
      try {
        metrics = JSON.parse(readFileSync(mp, 'utf-8'))
        trained = existsSync(mdl)
        break
      } catch {}
    }
  }

  // Fallback: check DB for forecasts with MOS correction
  if (!trained) {
    try {
      // If no local file, check if any forecasts used MOS
      const { getSQL } = require('./_db')
      const sql = getSQL()
      // This is async but we're in a sync handler — just report from file
    } catch {}
  }

  res.json({ trained, metrics })
}
