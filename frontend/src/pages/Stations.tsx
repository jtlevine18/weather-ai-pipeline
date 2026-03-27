import { useState, useMemo } from 'react'
import { ChevronDown, ChevronRight } from 'lucide-react'
import {
  useStations,
  useTelemetryRaw,
  useTelemetryClean,
  useHealingLog,
  useHealingStats,
} from '../api/hooks'
import type {
  Station,
  TelemetryRecord,
  HealingRecord,
  HealingStats,
} from '../api/hooks'
import { MetricCard } from '../components/MetricCard'
import { TableSkeleton } from '../components/LoadingSpinner'
import { PageContext } from '../components/PageContext'

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const STATES = ['All States', 'Kerala', 'Tamil Nadu']

const SOURCE_STYLE: Record<string, [string, string]> = {
  imd_api: ['India Met Dept', '#2E7D32'],
  imdlib: ['IMD Gridded Archive', '#1565C0'],
  synthetic: ['Synthetic', '#888'],
}

const HEAL_STYLE: Record<string, [string, string]> = {
  cross_validated: ['Validated', '#2a9d8f'],
  null_filled: ['Filled', '#d4a019'],
  ai_validated: ['AI OK', '#2a9d8f'],
  ai_corrected: ['AI Fixed', '#4361ee'],
  ai_filled: ['AI Filled', '#d4a019'],
  ai_flagged: ['AI Flagged', '#e76f51'],
  anomaly_flagged: ['Anomaly', '#e63946'],
  typo_corrected: ['Typo Fix', '#4361ee'],
  imputed_from_reference: ['Imputed', '#e76f51'],
  none: ['Original', '#888'],
}

const ASSESSMENT_COLOR: Record<string, string> = {
  good: '#2a9d8f',
  corrected: '#4361ee',
  filled: '#d4a019',
  flagged: '#e76f51',
  dropped: '#e63946',
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function fmtVal(v: number | undefined | null, unit = '', decimals = 1): string {
  if (v === undefined || v === null || Number.isNaN(v)) return '--'
  return `${Number(v).toFixed(decimals)}${unit}`
}

function tempColor(t: number | undefined | null): string {
  if (t === undefined || t === null) return '#1a1a1a'
  if (t >= 40) return '#C62828'
  if (t >= 36) return '#E65100'
  if (t <= 15) return '#0277BD'
  return '#1a1a1a'
}

function rainColor(r: number | undefined | null): string {
  if (r === undefined || r === null) return '#1a1a1a'
  if (r >= 20) return '#1565C0'
  if (r >= 5) return '#1976D2'
  return '#1a1a1a'
}

function qualityColor(pct: number): string {
  if (pct >= 85) return '#2a9d8f'
  if (pct >= 70) return '#d4a019'
  return '#e63946'
}

function healBarColor(action: string): string {
  if (action.includes('validated')) return '#2a9d8f'
  if (action.includes('filled')) return '#d4a019'
  if (action.includes('flagged') || action.includes('anomaly')) return '#e63946'
  return '#888'
}

// ---------------------------------------------------------------------------
// Small UI pieces
// ---------------------------------------------------------------------------

function SourceBadge({ source }: { source: string }) {
  const [label, color] = SOURCE_STYLE[source] ?? [source || '--', '#888']
  return (
    <span
      className="inline-block rounded px-2 py-0.5 text-xs font-semibold"
      style={{
        background: `${color}18`,
        color,
        border: `1px solid ${color}44`,
      }}
    >
      {label}
    </span>
  )
}

function HealBadges({ action }: { action: string }) {
  if (!action || action === 'none') {
    return (
      <span
        className="inline-block rounded px-1.5 py-0.5 text-[0.72rem] font-semibold"
        style={{ background: '#88818', color: '#888', border: '1px solid #88844' }}
      >
        Original
      </span>
    )
  }
  const parts = action.split(',').map((a) => a.trim()).filter(Boolean)
  return (
    <span className="inline-flex flex-wrap gap-1">
      {parts.map((p) => {
        const [l, c] = HEAL_STYLE[p] ?? [p, '#888']
        return (
          <span
            key={p}
            className="inline-block rounded px-1.5 py-0.5 text-[0.72rem] font-semibold"
            style={{ background: `${c}18`, color: c, border: `1px solid ${c}44` }}
          >
            {l}
          </span>
        )
      })}
    </span>
  )
}

function QualityBar({ score }: { score: number | undefined | null }) {
  if (score === undefined || score === null || Number.isNaN(score)) {
    return <span className="text-warm-muted">--</span>
  }
  const pct = Math.round(score * 100)
  const color = qualityColor(pct)
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className="inline-block w-[60px] h-2 rounded bg-warm-border overflow-hidden">
        <span
          className="block h-full rounded"
          style={{ width: `${pct}%`, background: color }}
        />
      </span>
      <span className="text-[0.82rem] font-semibold" style={{ color }}>
        {pct}%
      </span>
    </span>
  )
}

function AssessmentBadge({ type, count }: { type: string; count: number }) {
  const color = ASSESSMENT_COLOR[type] ?? '#888'
  return (
    <div
      className="rounded-md px-3.5 py-2 text-center min-w-[90px]"
      style={{ background: `${color}15`, border: `1px solid ${color}40` }}
    >
      <div className="text-2xl font-bold" style={{ color }}>
        {count}
      </div>
      <div
        className="text-[0.72rem] uppercase tracking-[1px]"
        style={{ color: `${color}99` }}
      >
        {type}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Tab: Station Readings
// ---------------------------------------------------------------------------

interface ReadingsTabProps {
  stations: Station[]
  rawData: TelemetryRecord[]
  cleanData: TelemetryRecord[]
}

function StationReadingsTab({ stations, rawData, cleanData }: ReadingsTabProps) {
  const [isRaw, setIsRaw] = useState(false)
  const [stateFilter, setStateFilter] = useState('All States')
  const [showAll, setShowAll] = useState(false)

  const stationNameMap = useMemo(() => {
    const m: Record<string, string> = {}
    stations.forEach((s) => {
      m[s.station_id] = s.name
    })
    return m
  }, [stations])

  const stationStateMap = useMemo(() => {
    const m: Record<string, string> = {}
    stations.forEach((s) => {
      m[s.station_id] = s.state
    })
    return m
  }, [stations])

  const df = isRaw ? rawData : cleanData

  // Compute latest reading per station, enriched with name/state
  const enriched = useMemo(() => {
    return df.map((r) => ({
      ...r,
      station_name: r.station_name || stationNameMap[r.station_id] || r.station_id,
      state: stationStateMap[r.station_id] || '',
    }))
  }, [df, stationNameMap, stationStateMap])

  const filtered = useMemo(() => {
    let d = enriched
    if (stateFilter !== 'All States') {
      d = d.filter((r) => r.state === stateFilter)
    }
    return d
  }, [enriched, stateFilter])

  // Latest per station
  const latest = useMemo(() => {
    const byStation: Record<string, typeof filtered[0]> = {}
    // Data is already sorted DESC by ts from API, so first occurrence is latest
    for (const r of filtered) {
      if (!byStation[r.station_id]) {
        byStation[r.station_id] = r
      }
    }
    return Object.values(byStation).sort((a, b) => {
      const sc = (a.state || '').localeCompare(b.state || '')
      if (sc !== 0) return sc
      return (a.station_name || '').localeCompare(b.station_name || '')
    })
  }, [filtered])

  // Group by state
  const grouped = useMemo(() => {
    const g: Record<string, typeof latest> = {}
    for (const r of latest) {
      const s = r.state || 'Unknown'
      if (!g[s]) g[s] = []
      g[s].push(r)
    }
    return Object.entries(g).sort(([a], [b]) => a.localeCompare(b))
  }, [latest])

  if (df.length === 0) {
    return (
      <div className="card card-body text-center py-12">
        <p className="text-warm-muted text-sm">
          No telemetry data yet. Run the pipeline first.
        </p>
      </div>
    )
  }

  const cols = isRaw
    ? ['Station', 'Temp', 'Humidity', 'Rainfall', 'Wind', 'Source', 'Time']
    : ['Station', 'Temp', 'Humidity', 'Rainfall', 'Wind', 'Quality', 'Healing', 'Time']

  return (
    <div className="space-y-4">
      {/* Controls */}
      <div className="flex flex-wrap items-center gap-4">
        {/* View toggle */}
        <div className="flex rounded-lg border border-warm-border overflow-hidden">
          <button
            onClick={() => setIsRaw(false)}
            className={`px-3 py-1.5 text-sm font-medium transition-colors ${
              !isRaw
                ? 'bg-gold text-white'
                : 'bg-white text-warm-body hover:bg-warm-header-bg'
            }`}
          >
            Clean (healed)
          </button>
          <button
            onClick={() => setIsRaw(true)}
            className={`px-3 py-1.5 text-sm font-medium transition-colors ${
              isRaw
                ? 'bg-gold text-white'
                : 'bg-white text-warm-body hover:bg-warm-header-bg'
            }`}
          >
            Raw (original)
          </button>
        </div>

        {/* State filter */}
        <select
          value={stateFilter}
          onChange={(e) => setStateFilter(e.target.value)}
          className="input w-auto min-w-[160px]"
        >
          {STATES.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </div>

      {filtered.length === 0 ? (
        <div className="card card-body text-center py-8">
          <p className="text-warm-muted text-sm">No readings match the current filters.</p>
        </div>
      ) : (
        <>
          {grouped.map(([stateName, rows]) => (
            <div key={stateName}>
              {/* Section header */}
              <p className="section-header inline-block mt-6">{stateName}</p>

              <div className="table-container">
                <table>
                  <thead>
                    <tr>
                      {cols.map((c) => (
                        <th key={c}>{c}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((row) => {
                      const ts = (row.observed_at || '').slice(0, 16)
                      return (
                        <tr key={row.station_id}>
                          <td>
                            <div className="font-semibold text-[#1a1a1a]">
                              {row.station_name}
                            </div>
                            <div className="text-[0.72rem] text-warm-muted-light font-normal">
                              {row.station_id}
                            </div>
                          </td>
                          <td
                            className="font-semibold tabular-nums"
                            style={{ color: tempColor(row.temperature) }}
                          >
                            {fmtVal(row.temperature, ' \u00B0C')}
                          </td>
                          <td className="tabular-nums">
                            {fmtVal(row.humidity, '%')}
                          </td>
                          <td
                            className="font-semibold tabular-nums"
                            style={{ color: rainColor(row.rainfall_mm) }}
                          >
                            {fmtVal(row.rainfall_mm, ' mm')}
                          </td>
                          <td className="tabular-nums">
                            {fmtVal(row.wind_speed, ' m/s')}
                          </td>
                          {isRaw ? (
                            <td>
                              <SourceBadge source={row.source || ''} />
                            </td>
                          ) : (
                            <>
                              <td>
                                <QualityBar score={row.quality_score} />
                              </td>
                              <td>
                                <HealBadges action={row.heal_action || 'none'} />
                              </td>
                            </>
                          )}
                          <td className="text-warm-muted text-[0.82rem]">{ts}</td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          ))}

          {/* View all readings expander */}
          <div className="card overflow-hidden mt-4">
            <button
              onClick={() => setShowAll(!showAll)}
              className="w-full flex items-center gap-2 px-5 py-3 text-sm font-medium text-warm-body hover:bg-warm-header-bg transition-colors"
            >
              {showAll ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
              View all readings ({filtered.length})
            </button>
            {showAll && (
              <div className="max-h-[400px] overflow-auto border-t border-warm-border">
                <table className="w-full text-sm text-left font-sans">
                  <thead className="bg-warm-header-bg border-b border-warm-border sticky top-0">
                    <tr>
                      <th className="px-3 py-2 text-xs uppercase text-warm-muted tracking-label font-semibold">
                        Station
                      </th>
                      <th className="px-3 py-2 text-xs uppercase text-warm-muted tracking-label font-semibold">
                        Time
                      </th>
                      <th className="px-3 py-2 text-xs uppercase text-warm-muted tracking-label font-semibold">
                        Temp
                      </th>
                      <th className="px-3 py-2 text-xs uppercase text-warm-muted tracking-label font-semibold">
                        Humidity
                      </th>
                      <th className="px-3 py-2 text-xs uppercase text-warm-muted tracking-label font-semibold">
                        Wind
                      </th>
                      <th className="px-3 py-2 text-xs uppercase text-warm-muted tracking-label font-semibold">
                        Rainfall
                      </th>
                      {isRaw ? (
                        <th className="px-3 py-2 text-xs uppercase text-warm-muted tracking-label font-semibold">
                          Source
                        </th>
                      ) : (
                        <>
                          <th className="px-3 py-2 text-xs uppercase text-warm-muted tracking-label font-semibold">
                            Quality
                          </th>
                          <th className="px-3 py-2 text-xs uppercase text-warm-muted tracking-label font-semibold">
                            Healing
                          </th>
                        </>
                      )}
                    </tr>
                  </thead>
                  <tbody>
                    {filtered.map((r, i) => (
                      <tr key={i} className="border-b border-warm-border/50 hover:bg-cream/60">
                        <td className="px-3 py-2 text-[#1a1a1a]">{r.station_id}</td>
                        <td className="px-3 py-2 text-warm-muted text-xs">
                          {(r.observed_at || '').slice(0, 16)}
                        </td>
                        <td className="px-3 py-2 tabular-nums">{fmtVal(r.temperature)}</td>
                        <td className="px-3 py-2 tabular-nums">{fmtVal(r.humidity)}</td>
                        <td className="px-3 py-2 tabular-nums">{fmtVal(r.wind_speed)}</td>
                        <td className="px-3 py-2 tabular-nums">{fmtVal(r.rainfall_mm)}</td>
                        {isRaw ? (
                          <td className="px-3 py-2">
                            <SourceBadge source={r.source || ''} />
                          </td>
                        ) : (
                          <>
                            <td className="px-3 py-2">
                              <QualityBar score={r.quality_score} />
                            </td>
                            <td className="px-3 py-2">
                              <HealBadges action={r.heal_action || 'none'} />
                            </td>
                          </>
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </>
      )}

      {/* Data Sources info card */}
      <div className="card card-body mt-4">
        <div className="font-semibold text-[#1a1a1a] mb-2">Data Sources</div>
        <div className="text-[0.85rem] text-warm-body leading-relaxed space-y-1">
          <p>
            <strong className="text-[#1a1a1a]">India Meteorological Department</strong> --
            Real-time station data scraped from city.imd.gov.in (today's max/min temp,
            humidity, rainfall)
          </p>
          <p>
            <strong className="text-[#1a1a1a]">IMD Gridded Archive</strong> -- Historical
            gridded data at 0.25 deg resolution via imdlib (T-1 day lag, temperature + rainfall
            only)
          </p>
          <p>
            <strong className="text-[#1a1a1a]">Tomorrow.io</strong> -- Used for
            cross-validation and to fill fields IMD doesn't provide (wind speed, pressure,
            humidity)
          </p>
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Tab: Healing
// ---------------------------------------------------------------------------

interface HealingTabProps {
  cleanData: TelemetryRecord[]
  healingLog: HealingRecord[]
  healingStats: HealingStats | undefined
  stationNames: Record<string, string>
}

function HealingTab({ cleanData, healingLog, healingStats, stationNames }: HealingTabProps) {
  const hasAiData = healingLog.length > 0
  const latestRun = healingStats?.latest_run

  // Compute heal action counts from clean data
  const actionCounts = useMemo(() => {
    const counts: Record<string, number> = {}
    for (const r of cleanData) {
      const action = r.heal_action || 'none'
      counts[action] = (counts[action] || 0) + 1
    }
    return Object.entries(counts).sort(([, a], [, b]) => b - a)
  }, [cleanData])

  const totalActions = actionCounts.reduce((sum, [, c]) => sum + c, 0)

  if (cleanData.length === 0) {
    return (
      <div className="card card-body text-center py-12">
        <p className="text-warm-muted text-sm">
          No telemetry data yet. Run the pipeline first.
        </p>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* AI agent metrics */}
      {hasAiData && latestRun ? (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          <MetricCard label="Model" value={latestRun.model || '--'} />
          <MetricCard
            label="Tokens"
            value={((latestRun.tokens_in || 0) + (latestRun.tokens_out || 0)).toLocaleString()}
          />
          <MetricCard
            label="Latency"
            value={`${(latestRun.latency_s || 0).toFixed(1)}s`}
          />
          <MetricCard
            label="Est. Cost"
            value={`$${(
              ((latestRun.tokens_in || 0) * 3.0) / 1_000_000 +
              ((latestRun.tokens_out || 0) * 15.0) / 1_000_000
            ).toFixed(3)}`}
          />
        </div>
      ) : !hasAiData ? (
        <div
          className="rounded-lg p-3 text-[0.85rem]"
          style={{
            background: '#fff8e6',
            border: '1px solid #e0dcd5',
            color: '#8a6d00',
          }}
        >
          No AI healing data yet. Run the pipeline with an Anthropic API key to enable the
          Claude healing agent.
        </div>
      ) : null}

      {latestRun?.fallback_used && (
        <div
          className="rounded-lg p-3 text-[0.85rem]"
          style={{
            background: '#fff8e6',
            border: '1px solid #e0dcd5',
            color: '#8a6d00',
          }}
        >
          Rule-based fallback was used (AI agent unavailable)
        </div>
      )}

      {/* Assessment distribution */}
      {hasAiData && healingStats?.assessment_distribution && (
        <>
          <p className="section-header inline-block">Assessment Summary</p>
          <div className="flex flex-wrap gap-3">
            {(['good', 'corrected', 'filled', 'flagged', 'dropped'] as const).map(
              (atype) => {
                const info = healingStats?.assessment_distribution?.[atype] || {
                  count: 0,
                }
                return (
                  <AssessmentBadge key={atype} type={atype} count={info.count} />
                )
              }
            )}
          </div>
        </>
      )}

      {/* Healing actions breakdown */}
      {actionCounts.length > 0 && (
        <>
          <p className="section-header inline-block mt-4">Healing Actions</p>
          <div className="table-container">
            <table>
              <thead>
                <tr>
                  <th>Action</th>
                  <th>Count</th>
                  <th>Distribution</th>
                </tr>
              </thead>
              <tbody>
                {actionCounts.map(([action, count]) => {
                  const pct = totalActions > 0 ? (count / totalActions) * 100 : 0
                  return (
                    <tr key={action}>
                      <td>
                        <HealBadges action={action} />
                      </td>
                      <td className="font-semibold tabular-nums">{count}</td>
                      <td>
                        <span className="inline-flex items-center gap-2">
                          <span className="inline-block w-[120px] h-2 rounded bg-warm-border overflow-hidden">
                            <span
                              className="block h-full rounded"
                              style={{
                                width: `${pct}%`,
                                background: healBarColor(action),
                              }}
                            />
                          </span>
                          <span className="text-[0.82rem] text-warm-body-light">
                            {pct.toFixed(0)}%
                          </span>
                        </span>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </>
      )}

      {/* Per-reading AI assessments */}
      {hasAiData && (
        <>
          <p className="section-header inline-block mt-6">Per-Reading Assessments</p>
          <p className="text-sm text-warm-muted -mt-3">
            Claude's reasoning for each station reading -- click to expand
          </p>
          <div className="space-y-2">
            {healingLog.map((row, idx) => (
              <HealingLogCard key={idx} row={row} stationNames={stationNames} />
            ))}
          </div>
        </>
      )}

      {/* Healing legend */}
      <HealingLegend />
    </div>
  )
}

function HealingLogCard({
  row,
  stationNames,
}: {
  row: HealingRecord
  stationNames: Record<string, string>
}) {
  const [expanded, setExpanded] = useState(() => {
    const a = row.assessment || 'unknown'
    return a === 'corrected' || a === 'flagged' || a === 'dropped'
  })

  const sid = row.station_id || ''
  const sname = stationNames[sid] || sid
  const assessment: string = row.assessment || 'unknown'
  const color = ASSESSMENT_COLOR[assessment] || '#888'
  const quality: number = row.quality_score || 0
  const reasoning: string = row.reasoning || ''
  const tools: string = row.tools_used || ''

  let corrections: Record<string, any> = {}
  let originals: Record<string, any> = {}
  try {
    corrections = JSON.parse(row.corrections || '{}')
  } catch {
    corrections = {}
  }
  try {
    originals = JSON.parse(row.original_values || '{}')
  } catch {
    originals = {}
  }

  const assessmentDot: Record<string, string> = {
    good: 'bg-success',
    corrected: 'bg-info',
    filled: 'bg-warning',
    flagged: 'bg-[#e76f51]',
    dropped: 'bg-error',
  }

  return (
    <div className="card overflow-hidden">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-2 px-5 py-3 text-sm font-medium text-left hover:bg-warm-header-bg transition-colors"
      >
        {expanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
        <span
          className={`w-2.5 h-2.5 rounded-full shrink-0 ${assessmentDot[assessment] || 'bg-warm-muted'}`}
        />
        <span className="text-[#1a1a1a] font-semibold">{sname}</span>
        <span className="text-warm-muted mx-1">--</span>
        <span style={{ color }} className="font-semibold">
          {assessment}
        </span>
        <span className="text-warm-muted ml-1">(Q: {quality.toFixed(2)})</span>
      </button>
      {expanded && (
        <div className="px-5 pb-4 border-t border-warm-border space-y-3 pt-3">
          {reasoning && (
            <p className="text-[0.9rem] text-warm-body leading-relaxed">{reasoning}</p>
          )}
          {Object.keys(corrections).length > 0 && (
            <div className="flex flex-wrap gap-4">
              {Object.entries(corrections).map(([field, newVal]) => {
                const oldVal = originals[field] ?? '--'
                const oldDisp =
                  typeof oldVal === 'number' ? oldVal.toFixed(1) : String(oldVal)
                const newDisp =
                  typeof newVal === 'number' ? newVal.toFixed(1) : String(newVal)
                return (
                  <div
                    key={field}
                    className="card card-body !p-2 !px-3"
                  >
                    <div className="text-[0.72rem] uppercase text-warm-muted tracking-[1px]">
                      {field}
                    </div>
                    <span className="text-error line-through">{oldDisp}</span>
                    <span className="mx-1 text-warm-muted">&rarr;</span>
                    <span className="text-success font-semibold">{newDisp}</span>
                  </div>
                )
              })}
            </div>
          )}
          {tools && (
            <div className="flex flex-wrap gap-1.5">
              {tools
                .split(',')
                .map((t) => t.trim())
                .filter(Boolean)
                .map((t) => (
                  <span
                    key={t}
                    className="inline-block rounded-full px-2.5 py-0.5 text-[0.72rem] text-warm-body-light"
                    style={{
                      background: '#f0ede8',
                      border: '1px solid #d0ccc5',
                    }}
                  >
                    {t}
                  </span>
                ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

const HEAL_LEGEND: [string, string][] = [
  ['cross_validated', 'Reading matches Tomorrow.io reference within thresholds'],
  [
    'null_filled',
    "Missing fields filled from Tomorrow.io (expected -- IMD doesn't provide wind/pressure/humidity)",
  ],
  [
    'ai_validated',
    'AI agent confirmed reading quality against reference and seasonal norms',
  ],
  [
    'ai_corrected',
    'AI agent corrected a value (e.g. decimal typo) with contextual reasoning',
  ],
  ['ai_filled', 'AI agent filled missing fields from reference data'],
  [
    'ai_flagged',
    "AI agent flagged a suspicious reading it couldn't confidently correct",
  ],
  [
    'anomaly_flagged',
    'Reading diverges beyond acceptable threshold from reference',
  ],
  [
    'typo_corrected',
    'Decimal-place error corrected (e.g. 320 deg C to 32.0 deg C)',
  ],
  [
    'imputed_from_reference',
    'Station offline -- entire reading sourced from reference',
  ],
]

function HealingLegend() {
  const [open, setOpen] = useState(false)
  return (
    <div className="card overflow-hidden">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center gap-2 px-5 py-3 text-sm font-medium text-warm-body hover:bg-warm-header-bg transition-colors"
      >
        {open ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
        Healing Actions Reference
      </button>
      {open && (
        <div className="px-5 pb-4 border-t border-warm-border pt-3 space-y-1.5">
          {HEAL_LEGEND.map(([action, desc]) => {
            const isAi = action.startsWith('ai_')
            return (
              <div key={action} className="text-[0.85rem]">
                <code
                  className="px-1.5 py-0.5 rounded text-[0.82rem]"
                  style={{ background: isAi ? '#e8f4fd' : '#f0ede8' }}
                >
                  {action}
                </code>{' '}
                <span className="text-warm-body">-- {desc}</span>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Tab: Map (table-based for now)
// ---------------------------------------------------------------------------

interface MapTabProps {
  stations: Station[]
  cleanData: TelemetryRecord[]
}

function MapTab({ stations, cleanData }: MapTabProps) {
  // Compute station health from clean data
  const healthMap = useMemo(() => {
    const m: Record<string, { count: number; totalQ: number; lastSeen: string }> = {}
    for (const r of cleanData) {
      if (!m[r.station_id]) {
        m[r.station_id] = { count: 0, totalQ: 0, lastSeen: '' }
      }
      m[r.station_id].count++
      m[r.station_id].totalQ += r.quality_score ?? 0
      const ts = r.observed_at || ''
      if (ts > m[r.station_id].lastSeen) {
        m[r.station_id].lastSeen = ts
      }
    }
    return m
  }, [cleanData])

  type StationHealth = 'good' | 'low' | 'none'

  function getHealth(sid: string): StationHealth {
    const h = healthMap[sid]
    if (!h || h.count === 0) return 'none'
    const avgQ = h.totalQ / h.count
    if (avgQ < 0.7) return 'low'
    return 'good'
  }

  const healthColor: Record<StationHealth, string> = {
    good: 'rgb(50,200,50)',
    low: 'rgb(255,165,0)',
    none: 'rgb(200,50,50)',
  }

  return (
    <div className="space-y-4">
      {/* Legend */}
      <div className="flex gap-4 text-[0.8rem] text-warm-body-light">
        <span className="flex items-center gap-1.5">
          <span
            className="inline-block w-2.5 h-2.5 rounded-full"
            style={{ background: healthColor.good }}
          />
          Good data
        </span>
        <span className="flex items-center gap-1.5">
          <span
            className="inline-block w-2.5 h-2.5 rounded-full"
            style={{ background: healthColor.low }}
          />
          Low quality
        </span>
        <span className="flex items-center gap-1.5">
          <span
            className="inline-block w-2.5 h-2.5 rounded-full"
            style={{ background: healthColor.none }}
          />
          No data
        </span>
      </div>

      {/* Station summary table */}
      <div className="table-container">
        <table>
          <thead>
            <tr>
              <th>Status</th>
              <th>Station</th>
              <th>State</th>
              <th>Lat</th>
              <th>Lon</th>
              <th>Records</th>
              <th>Avg Quality</th>
              <th>Last Seen</th>
            </tr>
          </thead>
          <tbody>
            {stations
              .slice()
              .sort((a, b) => a.state.localeCompare(b.state) || a.name.localeCompare(b.name))
              .map((s) => {
                const h = healthMap[s.station_id]
                const health = getHealth(s.station_id)
                const avgQ = h && h.count > 0 ? h.totalQ / h.count : 0
                return (
                  <tr key={s.station_id}>
                    <td>
                      <span
                        className="inline-block w-3 h-3 rounded-full"
                        style={{ background: healthColor[health] }}
                      />
                    </td>
                    <td>
                      <div className="font-semibold text-[#1a1a1a]">{s.name}</div>
                      <div className="text-[0.72rem] text-warm-muted-light">
                        {s.station_id}
                      </div>
                    </td>
                    <td>{s.state}</td>
                    <td className="tabular-nums">{s.latitude.toFixed(4)}</td>
                    <td className="tabular-nums">{s.longitude.toFixed(4)}</td>
                    <td className="tabular-nums font-semibold">{h?.count || 0}</td>
                    <td>
                      {h && h.count > 0 ? (
                        <QualityBar score={avgQ} />
                      ) : (
                        <span className="text-warm-muted">--</span>
                      )}
                    </td>
                    <td className="text-warm-muted text-[0.82rem]">
                      {h?.lastSeen ? h.lastSeen.slice(0, 16) : '--'}
                    </td>
                  </tr>
                )
              })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

type TabKey = 'readings' | 'healing' | 'health'

export default function Stations() {
  const [activeTab, setActiveTab] = useState<TabKey>('readings')

  const stationsQ = useStations()
  const rawQ = useTelemetryRaw(500)
  const cleanQ = useTelemetryClean(500)
  const healingLogQ = useHealingLog(200)
  const healingStatsQ = useHealingStats()

  const stations = stationsQ.data || []
  const rawData = rawQ.data || []
  const cleanData = cleanQ.data || []
  const healingLog = healingLogQ.data || []
  const healingStats = healingStatsQ.data

  const isLoading =
    stationsQ.isLoading || rawQ.isLoading || cleanQ.isLoading

  const stationNameMap = useMemo(() => {
    const m: Record<string, string> = {}
    stations.forEach((s) => {
      m[s.station_id] = s.name
    })
    return m
  }, [stations])

  // Metric computations
  const totalStations = stations.length
  const activeStations = useMemo(() => {
    const withData = new Set(cleanData.map((r) => r.station_id))
    return withData.size
  }, [cleanData])

  const avgQuality = useMemo(() => {
    const scores = cleanData
      .filter((r) => r.quality_score !== undefined && r.quality_score !== null)
      .map((r) => r.quality_score!)
    if (scores.length === 0) return 0
    return scores.reduce((a, b) => a + b, 0) / scores.length
  }, [cleanData])

  if (isLoading) return <TableSkeleton />

  const tabs: { key: TabKey; label: string }[] = [
    { key: 'readings', label: 'Station Readings' },
    { key: 'healing', label: 'Healing' },
    { key: 'health', label: 'Station Health' },
  ]

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div>
        <h1 className="page-title">Data</h1>
        <p className="page-caption">
          Weather station readings across Kerala and Tamil Nadu — raw ingestion, quality scores, and healing
        </p>
      </div>

      <PageContext id="stations">
        Raw weather observations from India's meteorological network, before and after AI-powered quality healing. Toggle between raw and healed data to see how anomalies are detected and corrected.
      </PageContext>

      {/* Metric cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <MetricCard
          label="Active Stations"
          value={`${activeStations}/${totalStations}`}
        />
        <MetricCard
          label="Avg Quality"
          value={`${Math.round(avgQuality * 100)}%`}
        />
        <MetricCard label="Raw Readings" value={rawData.length} />
        <MetricCard label="Healed Readings" value={cleanData.length} />
      </div>

      {/* Divider */}
      <hr className="border-warm-border" />

      {/* Tabs */}
      <div className="tab-list">
        {tabs.map(({ key, label }) => (
          <button
            key={key}
            onClick={() => setActiveTab(key)}
            className={`tab-item ${activeTab === key ? 'active' : ''}`}
          >
            {label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {activeTab === 'readings' && (
        <StationReadingsTab
          stations={stations}
          rawData={rawData}
          cleanData={cleanData}
        />
      )}
      {activeTab === 'healing' && (
        <HealingTab
          cleanData={cleanData}
          healingLog={healingLog}
          healingStats={healingStats}
          stationNames={stationNameMap}
        />
      )}
      {activeTab === 'health' && <MapTab stations={stations} cleanData={cleanData} />}
    </div>
  )
}
