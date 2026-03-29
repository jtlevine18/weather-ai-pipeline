import type { VercelRequest, VercelResponse } from '@vercel/node'
import { readFileSync, existsSync } from 'fs'
import { join } from 'path'

export default function handler(_req: VercelRequest, res: VercelResponse) {
  const names = ['healing', 'forecast', 'rag', 'advisory', 'translation', 'dpi', 'conversation']
  const results: Record<string, any> = {}
  for (const base of [process.cwd(), join(process.cwd(), '..'), '/var/task']) {
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
  return res.json(results)
}
