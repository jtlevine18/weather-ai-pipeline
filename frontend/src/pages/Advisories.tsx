import { useState, useMemo } from 'react'
import {
  useAlerts,
  useStations,
  useDeliveryLog,
  useDeliveryCount,
  useDeliveryByStation,
  useDeliverySamples,
  type Alert,
  type CropSmsBuckets,
  type DeliverySample,
} from '../api/hooks'
import { MetricCard } from '../components/MetricCard'
import { TableSkeleton } from '../components/LoadingSpinner'
import { TabPanel } from '../components/TabPanel'
import { formatTime } from '../lib/format'

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const CONDITION_COLOR: Record<string, string> = {
  heavy_rain: '#2d5b7d', moderate_rain: '#2d5b7d', heat_stress: '#c71f48',
  drought_risk: '#2d5b7d', frost_risk: '#606373', high_wind: '#606373',
  foggy: '#606373', clear: '#606373',
}

const STATUS_COLOR: Record<string, string> = {
  sent: '#606373', dry_run: '#606373', failed: '#c71f48',
}

const PROVIDER_LABEL: Record<string, string> = {
  rag: 'AI + knowledge base',
  rag_claude: 'AI + knowledge base',
  claude: 'AI',
  local: 'Rule-based',
}

const LANG_LABEL: Record<string, string> = {
  ta: 'Tamil',
  ml: 'Malayalam',
  en: 'English',
}

const CONDITION_LABEL: Record<string, string> = {
  heavy_rain: 'Heavy rain',
  moderate_rain: 'Moderate rain',
  heat_stress: 'Heat stress',
  drought_risk: 'Drought risk',
  frost_risk: 'Frost risk',
  high_wind: 'High wind',
  foggy: 'Fog',
  clear: 'Clear',
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function parseCropSms(raw: string | null | undefined): CropSmsBuckets {
  if (!raw) return {}
  if (typeof raw !== 'string') return raw as CropSmsBuckets
  try {
    const parsed = JSON.parse(raw)
    return parsed && typeof parsed === 'object' ? parsed : {}
  } catch {
    return {}
  }
}

function parseFarmerCrops(raw: string | null | undefined): string[] {
  if (!raw) return []
  if (Array.isArray(raw)) return raw
  try {
    const parsed = JSON.parse(raw)
    if (Array.isArray(parsed)) return parsed
  } catch {
    // fall through
  }
  return String(raw).split(',').map(s => s.trim()).filter(Boolean)
}

// Derive a ~160-char plain-text SMS preview from a markdown advisory.
// Used as a fallback when the backend's sms columns are empty on older rows.
function extractSmsPreview(text: string | undefined | null, maxLen = 160): string {
  if (!text) return ''
  const stripped = text
    .replace(/^#+\s+.*$/gm, '')
    .replace(/\*\*([^*]+)\*\*/g, '$1')
    .replace(/\*([^*]+)\*/g, '$1')
    .replace(/`([^`]+)`/g, '$1')
    .replace(/^\s*[-•]\s+/gm, '')
    .replace(/\s+/g, ' ')
    .trim()
  if (!stripped) return ''
  if (stripped.length <= maxLen) return stripped
  return stripped.slice(0, maxLen).replace(/\s+\S*$/, '').trimEnd() + '…'
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function Advisories() {
  const { data: alerts, isLoading, error } = useAlerts(200)
  const { data: stations } = useStations()
  const { data: deliveryLog } = useDeliveryLog(500)
  const { data: deliveryCount } = useDeliveryCount()
  const { data: deliveryByStation } = useDeliveryByStation()

  const [activeTab, setActiveTab] = useState(0)
  const [langFilter, setLangFilter] = useState('All')
  const [condFilter, setCondFilter] = useState('All')

  const stationMap = useMemo(() => {
    const map: Record<string, string> = {}
    stations?.forEach(s => { map[s.id] = s.name })
    return map
  }, [stations])

  const perStationCount = useMemo(() => {
    const map: Record<string, number> = {}
    deliveryByStation?.forEach(d => { map[d.station_id] = d.count })
    return map
  }, [deliveryByStation])

  // Latest alert per station (agricultural_alerts is ordered newest-first
  // from the API). We only want to render one card per station even if the
  // table has multiple historical rows.
  const latestByStation = useMemo(() => {
    const seen = new Set<string>()
    const out: Alert[] = []
    for (const a of alerts ?? []) {
      if (seen.has(a.station_id)) continue
      seen.add(a.station_id)
      out.push(a)
    }
    return out
  }, [alerts])

  const totalAdvisories = latestByStation.length

  // Crops addressed across all current advisories — union of crop_sms keys
  // (case-folded). Falls back to an empty set when crop_sms is absent on
  // every row, so the metric reads 0 instead of a misleading guess.
  const cropsAddressed = useMemo(() => {
    const set = new Set<string>()
    for (const a of latestByStation) {
      const bucket = parseCropSms(a.crop_sms)
      const keys = Object.keys({ ...(bucket.en ?? {}), ...(bucket.local ?? {}) })
      keys.forEach(k => set.add(k.toLowerCase()))
    }
    return Array.from(set)
  }, [latestByStation])

  const languagesInUse = useMemo(() => {
    const set = new Set<string>()
    latestByStation.forEach(a => { if (a.language) set.add(a.language) })
    return Array.from(set)
  }, [latestByStation])

  const farmersReached = deliveryCount?.count ?? 0

  const languageOptions = useMemo(() => {
    const set = new Set(latestByStation.map(a => a.language).filter((x): x is string => !!x))
    return ['All', ...Array.from(set)]
  }, [latestByStation])
  const conditionOptions = useMemo(() => {
    const set = new Set(latestByStation.map(a => a.condition).filter((x): x is string => !!x))
    return ['All', ...Array.from(set)]
  }, [latestByStation])

  const filtered = useMemo(() => {
    let items = [...latestByStation]
    if (langFilter !== 'All') items = items.filter(a => a.language === langFilter)
    if (condFilter !== 'All') items = items.filter(a => a.condition === condFilter)
    return items
  }, [latestByStation, langFilter, condFilter])

  if (isLoading) return (
    <div>
      <div className="pt-2 pb-6"><h1 className="page-title" style={{ fontFamily: '"Source Serif 4", serif' }}>Advisories</h1></div>
      <TableSkeleton />
    </div>
  )
  if (error) return <div className="text-center py-12"><p className="text-crit text-sm">Failed to load advisories</p></div>

  const TABS = ['This week', 'Delivery log']

  return (
    <div className="space-y-8">
      <div>
        <h1 className="page-title" data-tour="advisories-title">
          Advisories
        </h1>
        <p className="page-caption" style={{ maxWidth: '680px' }}>
          Each week the pipeline generates one advisory per station, writes a short SMS for every
          registered crop, and fans those out to every farmer in the registry in their language.
        </p>
      </div>

      {/* Hero metrics — 4 real counts from this week's run */}
      <div
        data-tour="advisories-metrics"
        className="grid grid-cols-2 md:grid-cols-4 gap-6 md:gap-8"
        style={{
          borderTop: '1px solid #e8e5e1',
          paddingTop: '28px',
        }}
      >
        <MetricCard label="Advisories" value={totalAdvisories} />
        <MetricCard label="Crops addressed" value={cropsAddressed.length || '—'} />
        <MetricCard label="Farmers reached" value={farmersReached.toLocaleString()} />
        <MetricCard
          label="Languages"
          value={languagesInUse.length || '—'}
          subtitle={
            languagesInUse.length
              ? languagesInUse.map(l => LANG_LABEL[l] ?? l).join(' · ')
              : undefined
          }
        />
      </div>

      {/* Tabs */}
      <div data-tour="advisories-tabs" className="tab-list">
        {TABS.map((tab, i) => (
          <button key={tab} className={`tab-item ${activeTab === i ? 'active' : ''}`} onClick={() => setActiveTab(i)}>
            {tab}
          </button>
        ))}
      </div>

      {/* ── This week ────────────────────────────────────────── */}
      <TabPanel active={activeTab === 0}>
        <div className="space-y-4">
          {/* Filters */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <select className="input" value={langFilter} onChange={e => setLangFilter(e.target.value)}>
              {languageOptions.map(l => (
                <option key={l} value={l}>{l === 'All' ? 'All languages' : (LANG_LABEL[l] ?? l)}</option>
              ))}
            </select>
            <select className="input" value={condFilter} onChange={e => setCondFilter(e.target.value)}>
              {conditionOptions.map(c => (
                <option key={c} value={c}>{c === 'All' ? 'All conditions' : (CONDITION_LABEL[c] ?? c)}</option>
              ))}
            </select>
          </div>

          {filtered.length === 0 ? (
            <p style={{ color: '#8d909e', fontSize: '13px', padding: '32px 0' }}>
              No advisories match your filters
            </p>
          ) : (
            <div style={{ borderTop: '1px solid #e8e5e1' }}>
              {filtered.map(alert => (
                <AdvisoryCard
                  key={alert.id ?? alert.station_id}
                  alert={alert}
                  stationName={alert.station_name || stationMap[alert.station_id] || alert.station_id}
                  farmersReached={perStationCount[alert.station_id] ?? 0}
                />
              ))}
            </div>
          )}
        </div>
      </TabPanel>

      {/* ── Delivery log ─────────────────────────────────────── */}
      <TabPanel active={activeTab === 1}>
        <DeliveryLogTab rows={deliveryLog ?? []} totalCount={farmersReached} />
      </TabPanel>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Advisory card — per station, with per-crop SMS + lazy farmer examples
// ---------------------------------------------------------------------------

function AdvisoryCard({
  alert,
  stationName,
  farmersReached,
}: {
  alert: Alert
  stationName: string
  farmersReached: number
}) {
  const [showFarmers, setShowFarmers] = useState(false)
  const { data: samples, isLoading: samplesLoading } = useDeliverySamples(
    showFarmers ? alert.station_id : '',
  )

  const cond = alert.condition || ''
  const condColor = CONDITION_COLOR[cond] || '#606373'
  const provider = alert.provider || 'rag'
  const lang = alert.language || 'en'

  const cropSms = useMemo(() => parseCropSms(alert.crop_sms), [alert.crop_sms])
  const localBucket = cropSms.local ?? {}
  const enBucket = cropSms.en ?? {}
  const cropKeys = Array.from(new Set([...Object.keys(localBucket), ...Object.keys(enBucket)]))

  // Fallback station-level SMS preview (for rows from before the 4-stage
  // rollout — the pipeline hasn't written crop_sms for them yet).
  const fallbackSms =
    (alert.sms_local || alert.sms_en || '').trim() ||
    extractSmsPreview(alert.advisory_local || alert.advisory_en)

  return (
    <div
      style={{
        borderBottom: '1px solid #e8e5e1',
        padding: '24px 0',
      }}
    >
      {/* Meta row */}
      <div
        style={{
          display: 'flex',
          alignItems: 'baseline',
          gap: '12px',
          flexWrap: 'wrap',
          fontFamily: '"Space Grotesk", system-ui, sans-serif',
          fontSize: '13px',
          color: '#606373',
        }}
      >
        <span style={{ color: '#1b1e2d', fontWeight: 500 }}>{stationName}</span>
        <span>·</span>
        <span>{LANG_LABEL[lang] ?? lang}</span>
        {cond && (
          <>
            <span>·</span>
            <span style={{ color: condColor }}>{CONDITION_LABEL[cond] ?? cond.replace(/_/g, ' ')}</span>
          </>
        )}
        <span>·</span>
        <span>{PROVIDER_LABEL[provider] ?? provider}</span>
        {farmersReached > 0 && (
          <>
            <span>·</span>
            <span style={{ color: '#2d5b7d' }}>{farmersReached.toLocaleString()} farmers reached</span>
          </>
        )}
        <span style={{ marginLeft: 'auto', color: '#8d909e' }}>
          {formatTime(alert.issued_at || alert.created_at)}
        </span>
      </div>

      {/* Advisory body — local then English */}
      {alert.advisory_local && (
        <p
          style={{
            fontFamily: '"Source Serif 4", "Noto Serif Malayalam", "Noto Serif Tamil", Georgia, serif',
            fontSize: '14px',
            lineHeight: 1.6,
            color: '#1b1e2d',
            marginTop: '14px',
            overflowWrap: 'break-word',
            wordBreak: 'break-word',
            whiteSpace: 'pre-wrap',
          }}
        >
          {alert.advisory_local}
        </p>
      )}
      {alert.advisory_en && (
        <p
          style={{
            fontFamily: '"Space Grotesk", system-ui, sans-serif',
            fontSize: '12px',
            lineHeight: 1.65,
            color: '#606373',
            marginTop: alert.advisory_local ? '8px' : '14px',
            overflowWrap: 'break-word',
            wordBreak: 'break-word',
            whiteSpace: 'pre-wrap',
          }}
        >
          {alert.advisory_en}
        </p>
      )}

      {/* Per-crop SMS chunks */}
      {cropKeys.length > 0 ? (
        <div
          style={{
            marginTop: '18px',
            paddingTop: '14px',
            borderTop: '1px dashed #e8e5e1',
          }}
        >
          <div className="eyebrow" style={{ marginBottom: '10px' }}>
            SMS by crop ({cropKeys.length})
          </div>
          <div style={{ display: 'grid', gap: '10px' }}>
            {cropKeys.map(crop => {
              const primary = localBucket[crop] || enBucket[crop] || ''
              const english = enBucket[crop] || ''
              const len = primary.length
              return (
                <div
                  key={crop}
                  className="grid grid-cols-[80px_1fr_auto] sm:grid-cols-[120px_1fr_auto] gap-3 sm:gap-4"
                  style={{
                    alignItems: 'start',
                    fontSize: '12px',
                    lineHeight: 1.5,
                  }}
                >
                  <span
                    style={{
                      color: '#1b1e2d',
                      textTransform: 'capitalize',
                      fontWeight: 500,
                      fontFamily: '"Space Grotesk", system-ui, sans-serif',
                    }}
                  >
                    {crop}
                  </span>
                  <div style={{ minWidth: 0 }}>
                    <p
                      style={{
                        margin: 0,
                        color: '#1b1e2d',
                        fontFamily:
                          '"Source Serif 4", "Noto Serif Malayalam", "Noto Serif Tamil", Georgia, serif',
                        overflowWrap: 'break-word',
                        wordBreak: 'break-word',
                      }}
                    >
                      {primary || <span style={{ color: '#8d909e' }}>—</span>}
                    </p>
                    {english && english !== primary && (
                      <p
                        style={{
                          margin: '4px 0 0',
                          color: '#8d909e',
                          fontSize: '11px',
                          fontFamily: '"Space Grotesk", system-ui, sans-serif',
                          overflowWrap: 'break-word',
                        }}
                      >
                        {english}
                      </p>
                    )}
                  </div>
                  <span
                    style={{
                      color: len > 160 ? '#c71f48' : '#8d909e',
                      fontFamily: '"Space Grotesk", system-ui, sans-serif',
                      fontVariantNumeric: 'tabular-nums',
                      fontSize: '11px',
                    }}
                  >
                    {len} / 160
                  </span>
                </div>
              )
            })}
          </div>
        </div>
      ) : fallbackSms ? (
        <div
          style={{
            marginTop: '18px',
            paddingTop: '14px',
            borderTop: '1px dashed #e8e5e1',
          }}
        >
          <div className="eyebrow" style={{ marginBottom: '6px' }}>
            SMS preview
          </div>
          <p
            style={{
              fontFamily: '"Space Grotesk", system-ui, sans-serif',
              fontSize: '12px',
              color: '#606373',
              lineHeight: 1.5,
              margin: 0,
            }}
          >
            {fallbackSms}
          </p>
          <p style={{ color: '#8d909e', fontSize: '11px', marginTop: '6px' }}>
            Per-crop SMS will populate after the next pipeline run.
          </p>
        </div>
      ) : null}

      {/* Example farmers — expand on click, lazy-loaded */}
      {farmersReached > 0 && (
        <div style={{ marginTop: '16px' }}>
          <button
            type="button"
            onClick={() => setShowFarmers(v => !v)}
            style={{
              background: 'none',
              border: 'none',
              padding: 0,
              color: '#2d5b7d',
              fontSize: '12px',
              fontFamily: '"Space Grotesk", system-ui, sans-serif',
              cursor: 'pointer',
            }}
          >
            {showFarmers ? '▾' : '▸'} Example farmers reached
          </button>
          {showFarmers && (
            <div style={{ marginTop: '12px', display: 'grid', gap: '10px' }}>
              {samplesLoading && (
                <p style={{ color: '#8d909e', fontSize: '12px', margin: 0 }}>Loading…</p>
              )}
              {!samplesLoading && (!samples || samples.length === 0) && (
                <p style={{ color: '#8d909e', fontSize: '12px', margin: 0 }}>
                  No delivery rows in the registry yet for this station.
                </p>
              )}
              {samples?.map((s, i) => (
                <FarmerSampleRow key={`${s.recipient}-${i}`} sample={s} />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Farmer sample row
// ---------------------------------------------------------------------------

function FarmerSampleRow({ sample }: { sample: DeliverySample }) {
  const crops = parseFarmerCrops(sample.primary_crops)
  const name = sample.name || sample.recipient
  // Prefer the dedicated sms_text column (populated by the 4-stage delivery
  // step). Old rows have it null — fall through to `message`, but strip
  // markdown so a 2,000-char advisory body doesn't blow up the card.
  const sms = sample.sms_text?.trim()
    ? sample.sms_text.trim()
    : extractSmsPreview(sample.message)
  return (
    <div
      style={{
        background: '#fcfaf7',
        border: '1px solid #e8e5e1',
        borderRadius: '6px',
        padding: '12px 14px',
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'baseline',
          gap: '10px',
          flexWrap: 'wrap',
          fontSize: '12px',
          fontFamily: '"Space Grotesk", system-ui, sans-serif',
        }}
      >
        <span style={{ color: '#1b1e2d', fontWeight: 500 }}>{name}</span>
        {crops.length > 0 && (
          <span style={{ color: '#606373' }}>· {crops.join(', ')}</span>
        )}
        <span style={{ marginLeft: 'auto', color: '#8d909e', fontSize: '11px' }}>
          {sample.recipient}
        </span>
      </div>
      {sms ? (
        <p
          style={{
            margin: '8px 0 0',
            color: '#1b1e2d',
            fontFamily: '"Source Serif 4", "Noto Serif Malayalam", "Noto Serif Tamil", Georgia, serif',
            fontSize: '13px',
            lineHeight: 1.5,
            overflowWrap: 'break-word',
            wordBreak: 'break-word',
          }}
        >
          {sms}
        </p>
      ) : (
        <p style={{ margin: '8px 0 0', color: '#8d909e', fontSize: '12px' }}>
          (No SMS text recorded for this delivery)
        </p>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Delivery log tab
// ---------------------------------------------------------------------------

function DeliveryLogTab({
  rows,
  totalCount,
}: {
  rows: Array<{
    id?: string | number
    station_id?: string
    channel?: string
    recipient?: string
    status?: string
    message?: string
    sms_text?: string
    delivered_at?: string
    created_at?: string
  }>
  totalCount: number
}) {
  const [search, setSearch] = useState('')
  const [stationFilter, setStationFilter] = useState('All')

  const stationOptions = useMemo(() => {
    const set = new Set(rows.map(r => r.station_id).filter((x): x is string => !!x))
    return ['All', ...Array.from(set).sort()]
  }, [rows])

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    return rows.filter(r => {
      if (stationFilter !== 'All' && r.station_id !== stationFilter) return false
      if (!q) return true
      return (
        (r.recipient || '').toLowerCase().includes(q) ||
        (r.sms_text || r.message || '').toLowerCase().includes(q)
      )
    })
  }, [rows, search, stationFilter])

  const sentCount = rows.filter(r => r.status === 'sent' || r.status === 'dry_run').length
  const failedCount = rows.filter(r => r.status === 'failed').length
  const uniqueRecipients = new Set(rows.map(r => r.recipient)).size

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <MetricCard label="Delivered this run" value={totalCount.toLocaleString()} />
        <MetricCard label="In this view" value={rows.length.toLocaleString()} />
        <MetricCard label="Unique recipients" value={uniqueRecipients.toLocaleString()} />
        <MetricCard label="Failed" value={failedCount} />
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-[1fr_240px] gap-3">
        <input
          className="input"
          type="search"
          placeholder="Search by phone or SMS text…"
          value={search}
          onChange={e => setSearch(e.target.value)}
        />
        <select className="input" value={stationFilter} onChange={e => setStationFilter(e.target.value)}>
          {stationOptions.map(s => (
            <option key={s} value={s}>{s === 'All' ? 'All stations' : s}</option>
          ))}
        </select>
      </div>

      {rows.length === 0 ? (
        <div className="card card-body text-center py-8">
          <p style={{ color: '#888', fontSize: '0.85rem' }}>
            No delivery records yet. Run the pipeline to populate this view.
          </p>
        </div>
      ) : (
        <>
          <p style={{ color: '#8d909e', fontSize: '12px', margin: 0 }}>
            Showing {filtered.length.toLocaleString()} of {rows.length.toLocaleString()} rows loaded
            {totalCount > rows.length && ` (${totalCount.toLocaleString()} total this run — view caps at ${rows.length.toLocaleString()})`}
            . Sent/dry-run: {sentCount.toLocaleString()}.
          </p>
          <div className="table-container">
            <table>
              <thead>
                <tr>
                  <th>Station</th>
                  <th>Recipient</th>
                  <th>Status</th>
                  <th>SMS text</th>
                  <th>Time</th>
                </tr>
              </thead>
              <tbody>
                {filtered.slice(0, 300).map((d, i) => {
                  const sColor = STATUS_COLOR[d.status || ''] || '#888'
                  const text = d.sms_text || d.message || ''
                  return (
                    <tr key={d.id ?? i}>
                      <td>{d.station_id || '--'}</td>
                      <td style={{ fontSize: '0.82rem' }}>{d.recipient || '--'}</td>
                      <td>
                        <span style={{ color: sColor, fontSize: '13px' }}>
                          {d.status || '—'}
                        </span>
                      </td>
                      <td
                        style={{
                          fontSize: '0.82rem',
                          color: '#555',
                          maxWidth: '420px',
                        }}
                        className="truncate"
                      >
                        {text.slice(0, 120)}
                      </td>
                      <td style={{ fontSize: '0.78rem', color: '#888' }}>
                        {formatTime(d.delivered_at || d.created_at)}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
          {filtered.length > 300 && (
            <p style={{ color: '#8d909e', fontSize: '11px', margin: 0 }}>
              Table capped at 300 rows for performance. Refine filters to see more.
            </p>
          )}
        </>
      )}
    </div>
  )
}
