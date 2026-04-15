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
import { TabPanel } from '../components/TabPanel'
import { REGION } from '../regionConfig'

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const STATES = ['All States', ...REGION.states]

const SOURCE_STYLE: Record<string, [string, string]> = REGION.sourceLabels

const HEAL_STYLE: Record<string, [string, string]> = {
  cross_validated: ['Validated', '#606373'],
  null_filled: ['Filled', '#606373'],
  ai_validated: ['AI OK', '#606373'],
  ai_corrected: ['AI fixed', '#2d5b7d'],
  ai_filled: ['AI filled', '#2d5b7d'],
  ai_flagged: ['Needs review', '#c71f48'],
  anomaly_flagged: ['Anomaly', '#c71f48'],
  typo_corrected: ['Typo fix', '#2d5b7d'],
  imputed_from_reference: ['From satellite', '#2d5b7d'],
  none: ['Original', '#8d909e'],
}

const ASSESSMENT_COLOR: Record<string, string> = {
  good: '#606373',
  corrected: '#2d5b7d',
  filled: '#2d5b7d',
  flagged: '#c71f48',
  dropped: '#c71f48',
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function fmtVal(v: number | undefined | null, unit = '', decimals = 1): string {
  if (v === undefined || v === null || Number.isNaN(v)) return '--'
  return `${Number(v).toFixed(decimals)}${unit}`
}

function tempColor(t: number | undefined | null): string {
  if (t === undefined || t === null) return '#1b1e2d'
  if (t >= 36) return '#2d5b7d'
  if (t <= 15) return '#606373'
  return '#1b1e2d'
}

function rainColor(r: number | undefined | null): string {
  if (r === undefined || r === null) return '#1b1e2d'
  if (r >= 5) return '#2d5b7d'
  return '#1b1e2d'
}

function qualityColor(pct: number): string {
  if (pct >= 85) return '#606373'
  if (pct >= 70) return '#2d5b7d'
  return '#c71f48'
}

function healBarColor(action: string): string {
  if (action.includes('validated')) return '#606373'
  if (action.includes('filled')) return '#2d5b7d'
  if (action.includes('flagged') || action.includes('anomaly')) return '#c71f48'
  return '#8d909e'
}

// ---------------------------------------------------------------------------
// Small UI pieces
// ---------------------------------------------------------------------------

function SourceBadge({ source }: { source: string }) {
  const [label, color] = SOURCE_STYLE[source] ?? [source || '--', '#606373']
  return (
    <span
      style={{
        fontSize: '13px',
        color,
        fontFamily: '"Space Grotesk", system-ui, sans-serif',
      }}
    >
      {label}
    </span>
  )
}

function HealBadges({ action }: { action: string }) {
  if (!action || action === 'none') {
    return (
      <span style={{ fontSize: '13px', color: '#8d909e' }}>Original</span>
    )
  }
  const parts = action.split(',').map((a) => a.trim()).filter(Boolean)
  return (
    <span style={{ display: 'inline-flex', flexWrap: 'wrap', gap: '10px' }}>
      {parts.map((p) => {
        const [l, c] = HEAL_STYLE[p] ?? [p, '#606373']
        return (
          <span key={p} style={{ fontSize: '13px', color: c }}>
            {l}
          </span>
        )
      })}
    </span>
  )
}

function QualityBar({ score }: { score: number | undefined | null }) {
  if (score === undefined || score === null || Number.isNaN(score)) {
    return <span style={{ color: '#8d909e' }}>—</span>
  }
  const pct = Math.round(score * 100)
  const color = qualityColor(pct)
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: '10px',
        fontVariantNumeric: 'tabular-nums',
      }}
    >
      <span
        style={{
          display: 'inline-block',
          width: '60px',
          height: '2px',
          background: '#e8e5e1',
          overflow: 'hidden',
        }}
      >
        <span
          style={{
            display: 'block',
            height: '100%',
            width: `${pct}%`,
            background: color,
          }}
        />
      </span>
      <span style={{ fontSize: '13px', color }}>{pct}%</span>
    </span>
  )
}

function AssessmentBadge({ type, count }: { type: string; count: number }) {
  const color = ASSESSMENT_COLOR[type] ?? '#606373'
  return (
    <div
      style={{
        minWidth: '110px',
        padding: '16px 0',
        borderTop: '1px solid #e8e5e1',
      }}
    >
      <div
        style={{
          fontFamily: '"Source Serif 4", Georgia, serif',
          fontSize: '28px',
          color: '#1b1e2d',
          fontVariantNumeric: 'tabular-nums',
        }}
      >
        {count}
      </div>
      <div
        style={{
          fontSize: '12px',
          color,
          marginTop: '4px',
          textTransform: 'lowercase',
        }}
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
      m[s.id] = s.name
    })
    return m
  }, [stations])

  const stationStateMap = useMemo(() => {
    const m: Record<string, string> = {}
    stations.forEach((s) => {
      m[s.id] = s.state
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
        <p className="text-mute text-sm">
          No telemetry data yet. Run the pipeline first.
        </p>
      </div>
    )
  }

  const cols = isRaw
    ? ['Station', 'Temp', 'Humidity', 'Rainfall', 'Wind', 'Source', 'Time']
    : ['Station', 'Temp', 'Humidity', 'Rainfall', 'Wind', 'Quality', 'Cleaning', 'Time']

  return (
    <div className="space-y-4">
      {/* Controls */}
      <div className="flex flex-wrap items-center gap-3">
        <button
          onClick={() => setIsRaw(false)}
          className={`chip ${!isRaw ? 'active' : ''}`}
        >
          Clean (healed)
        </button>
        <button
          onClick={() => setIsRaw(true)}
          className={`chip ${isRaw ? 'active' : ''}`}
        >
          Raw (original)
        </button>
        <span style={{ width: '1px', height: '20px', background: '#e8e5e1', margin: '0 8px' }} />
        {STATES.map((s) => (
          <button
            key={s}
            className={`chip ${stateFilter === s ? 'active' : ''}`}
            onClick={() => setStateFilter(s)}
          >
            {s}
          </button>
        ))}
      </div>

      {filtered.length === 0 ? (
        <div className="card card-body text-center py-8">
          <p className="text-mute text-sm">No readings match the current filters.</p>
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
                      const ts = (row.ts || '').slice(0, 16)
                      return (
                        <tr key={row.station_id}>
                          <td>
                            <div className="font-semibold text-[#1b1e2d]">
                              {row.station_name}
                            </div>
                            <div className="text-[0.72rem] text-mute font-normal">
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
                            style={{ color: rainColor(row.rainfall) }}
                          >
                            {fmtVal(row.rainfall, ' mm')}
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
                          <td className="text-mute text-[0.82rem]">{ts}</td>
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
              className="w-full flex items-center gap-2 px-5 py-3 text-sm font-medium text-slate hover:bg-cream transition-colors"
            >
              {showAll ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
              View all readings ({filtered.length})
            </button>
            {showAll && (
              <div className="max-h-[400px] overflow-auto border-t border-hairline">
                <table className="w-full text-sm text-left font-sans">
                  <thead className="bg-cream border-b border-hairline sticky top-0">
                    <tr>
                      <th className="px-3 py-2 text-xs uppercase text-mute tracking-wide font-semibold">
                        Station
                      </th>
                      <th className="px-3 py-2 text-xs uppercase text-mute tracking-wide font-semibold">
                        Time
                      </th>
                      <th className="px-3 py-2 text-xs uppercase text-mute tracking-wide font-semibold">
                        Temp
                      </th>
                      <th className="px-3 py-2 text-xs uppercase text-mute tracking-wide font-semibold">
                        Humidity
                      </th>
                      <th className="px-3 py-2 text-xs uppercase text-mute tracking-wide font-semibold">
                        Wind
                      </th>
                      <th className="px-3 py-2 text-xs uppercase text-mute tracking-wide font-semibold">
                        Rainfall
                      </th>
                      {isRaw ? (
                        <th className="px-3 py-2 text-xs uppercase text-mute tracking-wide font-semibold">
                          Source
                        </th>
                      ) : (
                        <>
                          <th className="px-3 py-2 text-xs uppercase text-mute tracking-wide font-semibold">
                            Quality
                          </th>
                          <th className="px-3 py-2 text-xs uppercase text-mute tracking-wide font-semibold">
                            Cleaning
                          </th>
                        </>
                      )}
                    </tr>
                  </thead>
                  <tbody>
                    {filtered.map((r, i) => (
                      <tr key={i} className="border-b border-hairline/60 hover:bg-cream/60">
                        <td className="px-3 py-2 text-[#1b1e2d]">{r.station_id}</td>
                        <td className="px-3 py-2 text-mute text-xs">
                          {(r.ts || '').slice(0, 16)}
                        </td>
                        <td className="px-3 py-2 tabular-nums">{fmtVal(r.temperature)}</td>
                        <td className="px-3 py-2 tabular-nums">{fmtVal(r.humidity)}</td>
                        <td className="px-3 py-2 tabular-nums">{fmtVal(r.wind_speed)}</td>
                        <td className="px-3 py-2 tabular-nums">{fmtVal(r.rainfall)}</td>
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
        <div className="font-semibold text-[#1b1e2d] mb-2">Data Sources</div>
        <div className="text-[0.85rem] text-slate leading-relaxed space-y-1">
          <p>
            <strong className="text-[#1b1e2d]">India Meteorological Department</strong> —
            Real-time station readings (today's max and min temperature, humidity, rainfall)
          </p>
          <p>
            <strong className="text-[#1b1e2d]">IMD historical archive</strong> — Historical
            data from imdlib, used as backup when the live feed is down (temperature and
            rainfall, one day behind)
          </p>
          <p>
            <strong className="text-[#1b1e2d]">Tomorrow.io</strong> — Second-opinion data for
            cross-checking station readings and for fields IMD doesn't report (wind speed,
            pressure, humidity)
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
        <p className="text-mute text-sm">
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
            border: '1px solid #e8e5e1',
            color: '#8a6d00',
          }}
        >
          No AI cleaning results yet. The AI cleaning step runs when the pipeline has an API key configured.
        </div>
      ) : null}

      {latestRun?.fallback_used && (
        <div
          className="rounded-lg p-3 text-[0.85rem]"
          style={{
            background: '#fff8e6',
            border: '1px solid #e8e5e1',
            color: '#8a6d00',
          }}
        >
          AI was unavailable — used rule-based cleaning instead.
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
          <p className="section-header inline-block mt-4">Cleaning Actions</p>
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
                          <span className="inline-block w-[120px] h-2 rounded bg-hairline overflow-hidden">
                            <span
                              className="block h-full rounded"
                              style={{
                                width: `${pct}%`,
                                background: healBarColor(action),
                              }}
                            />
                          </span>
                          <span className="text-[0.82rem] text-slate">
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
          <p className="text-sm text-mute -mt-3">
            Reasoning behind each cleaning decision — click to expand.
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
    good: 'bg-slate',
    corrected: 'bg-slate',
    filled: 'bg-sienna',
    flagged: 'bg-[#e76f51]',
    dropped: 'bg-crit',
  }

  return (
    <div className="card overflow-hidden">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-2 px-5 py-3 text-sm font-medium text-left hover:bg-cream transition-colors"
      >
        {expanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
        <span
          className={`w-2.5 h-2.5 rounded-full shrink-0 ${assessmentDot[assessment] || 'bg-mute'}`}
        />
        <span className="text-[#1b1e2d] font-semibold">{sname}</span>
        <span className="text-mute mx-1">—</span>
        <span style={{ color }} className="font-semibold">
          {assessment}
        </span>
        <span className="text-mute ml-1">(Q: {quality.toFixed(2)})</span>
      </button>
      {expanded && (
        <div className="px-5 pb-4 border-t border-hairline space-y-3 pt-3">
          {reasoning && (
            <p className="text-[0.9rem] text-slate leading-relaxed">{reasoning}</p>
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
                    <div className="text-[0.72rem] uppercase text-mute tracking-[1px]">
                      {field}
                    </div>
                    <span className="text-crit line-through">{oldDisp}</span>
                    <span className="mx-1 text-mute">&rarr;</span>
                    <span className="text-slate font-semibold">{newDisp}</span>
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
                    className="inline-block rounded-full px-2.5 py-0.5 text-[0.72rem] text-slate"
                    style={{
                      background: '#f0ece6',
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
  ['cross_validated', 'Reading matched the reference data within expected tolerances'],
  [
    'null_filled',
    "Missing fields filled from Tomorrow.io (expected — IMD doesn't provide wind/pressure/humidity)",
  ],
  [
    'ai_validated',
    'AI confirmed the reading looked right against reference data and seasonal norms',
  ],
  [
    'ai_corrected',
    'AI corrected a bad value (e.g. a misplaced decimal) with a written explanation',
  ],
  ['ai_filled', 'AI filled missing fields from reference data'],
  [
    'ai_flagged',
    "AI flagged a suspicious reading it couldn't confidently correct",
  ],
  [
    'anomaly_flagged',
    'Reading diverged too far from reference data to be trusted',
  ],
  [
    'typo_corrected',
    'Decimal-place error corrected (e.g. 320°C to 32.0°C)',
  ],
  [
    'imputed_from_reference',
    'Station was offline — the full reading came from reference data',
  ],
]

function HealingLegend() {
  const [open, setOpen] = useState(false)
  return (
    <div className="card overflow-hidden">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center gap-2 px-5 py-3 text-sm font-medium text-slate hover:bg-cream transition-colors"
      >
        {open ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
        What each cleaning action means
      </button>
      {open && (
        <div className="px-5 pb-4 border-t border-hairline pt-3 space-y-1.5">
          {HEAL_LEGEND.map(([action, desc]) => {
            const isAi = action.startsWith('ai_')
            return (
              <div key={action} className="text-[0.85rem]">
                <code
                  className="px-1.5 py-0.5 rounded text-[0.82rem]"
                  style={{ background: isAi ? '#e8f4fd' : '#f0ece6' }}
                >
                  {action}
                </code>{' '}
                <span className="text-slate">— {desc}</span>
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
      const ts = r.ts || ''
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
      <div className="flex gap-4 text-[0.8rem] text-slate">
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
                const h = healthMap[s.id]
                const health = getHealth(s.id)
                const avgQ = h && h.count > 0 ? h.totalQ / h.count : 0
                return (
                  <tr key={s.id}>
                    <td>
                      <span
                        className="inline-block w-3 h-3 rounded-full"
                        style={{ background: healthColor[health] }}
                      />
                    </td>
                    <td>
                      <div className="font-semibold text-[#1b1e2d]">{s.name}</div>
                      <div className="text-[0.72rem] text-mute">
                        {s.id}
                      </div>
                    </td>
                    <td>{s.state}</td>
                    <td className="tabular-nums">{s.lat.toFixed(4)}</td>
                    <td className="tabular-nums">{s.lon.toFixed(4)}</td>
                    <td className="tabular-nums font-semibold">{h?.count || 0}</td>
                    <td>
                      {h && h.count > 0 ? (
                        <QualityBar score={avgQ} />
                      ) : (
                        <span className="text-mute">--</span>
                      )}
                    </td>
                    <td className="text-mute text-[0.82rem]">
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
      m[s.id] = s.name
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
    { key: 'healing', label: 'Cleaning' },
    { key: 'health', label: 'Station Health' },
  ]

  return (
    <div className="space-y-8">
      {/* Page header */}
      <div>
        <h1 className="page-title" data-tour="stations-title">
          Stations
        </h1>
        <p className="page-caption" style={{ maxWidth: '680px' }}>
          Twenty stations across {REGION.states.join(' and ')}. An AI agent
          validates every reading against historical normals, neighboring
          stations, and a satellite reference.
        </p>
      </div>

      {/* Metric row */}
      <div
        data-tour="stations-metrics"
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(4, 1fr)',
          gap: '32px',
          borderTop: '1px solid #e8e5e1',
          paddingTop: '28px',
        }}
      >
        <MetricCard
          label="Active stations"
          value={`${activeStations}/${totalStations}`}
        />
        <MetricCard
          label="Avg quality"
          value={`${Math.round(avgQuality * 100)}%`}
        />
        <MetricCard label="Raw readings" value={rawData.length} />
        <MetricCard label="Cleaned readings" value={cleanData.length} />
      </div>

      {/* Tabs */}
      <div data-tour="stations-tabs" className="tab-list">
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
      <TabPanel active={activeTab === 'readings'}>
        <StationReadingsTab
          stations={stations}
          rawData={rawData}
          cleanData={cleanData}
        />
      </TabPanel>
      <TabPanel active={activeTab === 'healing'}>
        <HealingTab
          cleanData={cleanData}
          healingLog={healingLog}
          healingStats={healingStats}
          stationNames={stationNameMap}
        />
      </TabPanel>
      <TabPanel active={activeTab === 'health'}>
        <MapTab stations={stations} cleanData={cleanData} />
      </TabPanel>
    </div>
  )
}
