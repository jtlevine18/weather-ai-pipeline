import type { VercelRequest, VercelResponse } from '@vercel/node'
import { readFileSync, existsSync } from 'fs'
import { join } from 'path'

export default function handler(_req: VercelRequest, res: VercelResponse) {
  res.setHeader('Access-Control-Allow-Origin', '*')
  const names = ['healing', 'forecast', 'rag', 'advisory', 'translation', 'dpi', 'conversation']
  const results: Record<string, any> = {}

  // Eval results are committed JSON files
  for (const base of [join(process.cwd(), '..'), process.cwd(), '/var/task']) {
    const dir = join(base, 'tests', 'eval_results')
    if (existsSync(dir)) {
      for (const name of names) {
        const path = join(dir, `${name}.json`)
        if (existsSync(path)) {
          try { results[name] = JSON.parse(readFileSync(path, 'utf-8')) } catch {}
        }
      }
      break
    }
  }
  res.json(results)
}
