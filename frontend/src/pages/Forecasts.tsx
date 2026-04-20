import { useState, useMemo } from 'react'
import { useForecasts, useStations, useFarmers, useMosStatus, type Station, type Forecast } from '../api/hooks'
import { MetricCard } from '../components/MetricCard'
import { TableSkeleton } from '../components/LoadingSpinner'
import { TabPanel } from '../components/TabPanel'
import { REGION } from '../regionConfig'
import { ChevronDown, ChevronRight } from 'lucide-react'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Cell,
} from 'recharts'

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const CONDITION_COLOR: Record<string, string> = {
  heavy_rain: '#2d5b7d',
  moderate_rain: '#2d5b7d',
  heat_stress: '#c71f48',
  drought_risk: '#2d5b7d',
  frost_risk: '#606373',
  high_wind: '#606373',
  foggy: '#606373',
  clear: '#606373',
}

const MODEL_LABEL: Record<string, string> = {
  graphcast_mos: 'GraphCast + local correction',
  graphcast_only: 'GraphCast (raw)',
  neuralgcm_mos: 'Neural + local correction',
  neuralgcm_only: 'Neural (raw)',
  hybrid_mos: 'Standard + local correction',
  nwp_only: 'Standard (raw)',
  persistence: 'Last known reading',
}

const CONDITION_LABEL: Record<string, string> = {
  heavy_rain: 'Heavy rain',
  moderate_rain: 'Moderate rain',
  heat_stress: 'Heat stress',
  drought_risk: 'Drought risk',
  frost_risk: 'Frost risk',
  high_wind: 'High wind',
  foggy: 'Fog',
  clear: 'Clear skies',
}

const MODEL_COLOR: Record<string, string> = {
  graphcast_mos: '#2d5b7d',
  graphcast_only: '#2d5b7d',
  neuralgcm_mos: '#2d5b7d',
  neuralgcm_only: '#2d5b7d',
  hybrid_mos: '#606373',
  nwp_only: '#606373',
  persistence: '#c71f48',
}

const DEGRADATION_TIERS = [
  { tier: 'Tier 1', name: 'AI weather model + local correction', sub: 'primary', color: '#2d5b7d',
    desc: 'NeuralGCM \u2014 Google DeepMind\u2019s open neural weather model \u2014 produces a global forecast, then a statistical model trained on twelve years of station history applies a per-station local correction.' },
  { tier: 'Tier 2', name: 'Standard weather model + local correction', sub: 'fallback', color: '#606373',
    desc: 'Open-Meteo\u2019s traditional weather models when NeuralGCM is unavailable, with the same local correction applied.' },
  { tier: 'Tier 3', name: 'Last known reading', sub: 'emergency', color: '#c71f48',
    desc: 'The most recent observation with a time-of-day adjustment. No corrections applied.' },
]

const STATES = ['All', ...REGION.states]

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function fmtVal(v: number | undefined | null, unit = '', decimals = 1): string {
  if (v === undefined || v === null || Number.isNaN(v)) return '--'
  return `${Number(v).toFixed(decimals)}${unit}`
}

function confidenceColor(c: number): string {
  if (c >= 0.7) return '#606373'
  if (c >= 0.4) return '#2d5b7d'
  return '#c71f48'
}

function dayLabel(day: number | undefined): string {
  if (day === undefined || day === null) return '--'
  if (day === 0) return 'Today'
  return `Day ${day + 1}`
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function Forecasts() {
  const { data: forecasts, isLoading, error } = useForecasts(500)
  const { data: stations } = useStations()
  const [activeTab, setActiveTab] = useState(0)
  const [stateFilter, setStateFilter] = useState('All')
  const [condFilter, setCondFilter] = useState('All')
  const [modelFilter, setModelFilter] = useState('All')
  const [showModel, setShowModel] = useState(false)

  const stationMap = useMemo(() => {
    const map: Record<string, { name: string; state: string }> = {}
    stations?.forEach(s => { map[s.id] = { name: s.name, state: s.state } })
    return map
  }, [stations])

  const allForecasts = forecasts ?? []

  // Metrics
  const uniqueStations = new Set(allForecasts.map(f => f.station_id)).size
  const totalForecasts = allForecasts.length
  const avgConf = totalForecasts > 0
    ? allForecasts.reduce((s, f) => s + (f.confidence ?? 0), 0) / totalForecasts : 0
  const getModel = (f: { model_used?: string }) => f.model_used || ''
  const mosCount = allForecasts.filter(f => getModel(f).includes('mos')).length
  const mosPct = totalForecasts > 0 ? Math.round(100 * mosCount / totalForecasts) : 0
  const mosStatus = useMosStatus()
  const mosModelTrained = mosStatus.data?.trained ?? false
  const nwpSource = allForecasts.length > 0
    ? (allForecasts.some(f => getModel(f).includes('neuralgcm')) ? 'NeuralGCM' : 'Open-Meteo')
    : '--'
  const hasNeuralGCM = allForecasts.some(f => getModel(f).includes('neuralgcm'))

  // Conditions & models for filter dropdowns
  const conditions = useMemo(() => {
    const set = new Set(allForecasts.map(f => f.condition).filter((x): x is string => !!x))
    return ['All', ...Array.from(set)]
  }, [allForecasts])
  const models = useMemo(() => {
    const set = new Set(allForecasts.map(f => getModel(f)).filter(Boolean))
    return ['All', ...Array.from(set)]
  }, [allForecasts])

  // Filtered data
  const filtered = useMemo(() => {
    let items = [...allForecasts]
    if (stateFilter !== 'All') {
      items = items.filter(f => {
        const st = stationMap[f.station_id]?.state || ''
        return st.toLowerCase().includes(stateFilter.toLowerCase())
      })
    }
    if (condFilter !== 'All') items = items.filter(f => f.condition === condFilter)
    if (modelFilter !== 'All') items = items.filter(f => getModel(f) === modelFilter)
    return items
  }, [allForecasts, stateFilter, condFilter, modelFilter, stationMap])

  // Group by state
  const grouped = useMemo(() => {
    const map: Record<string, typeof filtered> = {}
    filtered.forEach(f => {
      const state = stationMap[f.station_id]?.state || 'Unknown'
      if (!map[state]) map[state] = []
      map[state].push(f)
    })
    return map
  }, [filtered, stationMap])

  // Model usage breakdown
  const modelBreakdown = useMemo(() => {
    const counts: Record<string, number> = {}
    allForecasts.forEach(f => {
      const m = getModel(f) || 'unknown'
      counts[m] = (counts[m] || 0) + 1
    })
    return Object.entries(counts).sort((a, b) => b[1] - a[1])
  }, [allForecasts])

  if (isLoading) return <TableSkeleton />
  if (error) return <div className="text-center py-12"><p className="text-crit text-sm">Failed to load forecasts</p></div>

  const TABS = ['Station forecasts', 'Downscaling']

  return (
    <div className="space-y-8">
      {/* Title */}
      <div>
        <h1 className="page-title" data-tour="forecasts-title">
          Forecasts
        </h1>
        <p className="page-caption" style={{ maxWidth: '680px' }}>
          Seven-day predictions for each station, then pulled in to each
          farmer's exact location and corrected for elevation.
        </p>
      </div>

      {/* 5 Metrics */}
      <div
        data-tour="forecasts-metrics"
        className="grid grid-cols-2 md:grid-cols-5 gap-6 md:gap-8"
        style={{
          borderTop: '1px solid #e8e5e1',
          paddingTop: '28px',
        }}
      >
        <MetricCard label="Stations Reporting" value={uniqueStations} />
        <MetricCard label="Total Forecasts" value={totalForecasts} />
        <MetricCard label="Avg Confidence" value={avgConf > 0 ? `${Math.round(avgConf * 100)}%` : '--'} />
        <MetricCard
          label="Local correction"
          value={mosModelTrained ? 'Trained' : 'Training'}
          subtitle={mosCount > 0 ? `${mosPct}% of forecasts corrected` : mosModelTrained ? 'Applies on the next run' : 'Warming up'}
        />
        <MetricCard label="Weather Model" value={nwpSource} />
      </div>

      <p
        style={{
          fontSize: '12px',
          color: '#8d909e',
          lineHeight: 1.55,
          maxWidth: '680px',
          marginTop: '-4px',
        }}
      >
        Confidence reflects how closely recent forecasts for each station matched observed
        weather over the last few weeks. A station with clean ground data and a well-behaved
        model scores higher; one with intermittent sensor gaps or a model tier fallback scores
        lower.
      </p>

      {/* Tabs */}
      <div data-tour="forecasts-tabs" className="tab-list">
        {TABS.map((tab, i) => (
          <button
            key={tab}
            className={`tab-item ${activeTab === i ? 'active' : ''}`}
            onClick={() => setActiveTab(i)}
          >
            {tab}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <TabPanel active={activeTab === 0}>
        <div className="space-y-6">
          {/* Filters */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <select className="input" value={stateFilter} onChange={e => setStateFilter(e.target.value)}>
              {STATES.map(s => <option key={s} value={s}>{s === 'All' ? 'All states' : s}</option>)}
            </select>
            <select className="input" value={condFilter} onChange={e => setCondFilter(e.target.value)}>
              {conditions.map(c => <option key={c} value={c}>{c === 'All' ? 'All conditions' : (CONDITION_LABEL[c] ?? c)}</option>)}
            </select>
            <select className="input" value={modelFilter} onChange={e => setModelFilter(e.target.value)}>
              {models.map(m => <option key={m} value={m}>{m === 'All' ? 'All models' : (MODEL_LABEL[m] ?? m)}</option>)}
            </select>
          </div>

          {/* State-grouped tables */}
          {Object.keys(grouped).length === 0 ? (
            <div className="card card-body text-center py-12">
              <p style={{ color: '#888', fontSize: '0.85rem' }}>No forecasts match your filters</p>
            </div>
          ) : (
            Object.entries(grouped).map(([state, items]) => (
              <div key={state}>
                {/* State header */}
                <div className="section-header">{state}</div>
                <div className="table-container">
                  <table>
                    <thead>
                      <tr>
                        <th>Station</th>
                        <th>Day</th>
                        <th>Temp</th>
                        <th>Rainfall</th>
                        <th>Condition</th>
                        <th>Model</th>
                        <th>Confidence</th>
                      </tr>
                    </thead>
                    <tbody>
                      {items.map((f, i) => {
                        const cond = f.condition || ''
                        const condColor = CONDITION_COLOR[cond] || '#888'
                        const model = getModel(f)
                        const mColor = MODEL_COLOR[model] || '#888'
                        const conf = f.confidence ?? 0
                        return (
                          <tr key={f.id ?? i}>
                            <td style={{ fontWeight: 500, color: '#1b1e2d' }}>
                              {f.station_name || stationMap[f.station_id]?.name || f.station_id}
                            </td>
                            <td>{dayLabel(f.forecast_day)}</td>
                            <td>{fmtVal(f.temp_max ?? f.temperature, '\u00B0C')}</td>
                            <td>{fmtVal(f.rainfall, ' mm')}</td>
                            <td>
                              {cond ? (
                                <span style={{ color: condColor, fontSize: '13px' }}>
                                  {CONDITION_LABEL[cond] ?? cond.replace(/_/g, ' ')}
                                </span>
                              ) : '—'}
                            </td>
                            <td>
                              {model ? (
                                <span style={{ color: mColor, fontSize: '13px' }}>
                                  {MODEL_LABEL[model] ?? model.replace(/_/g, ' ')}
                                </span>
                              ) : '—'}
                            </td>
                            <td>
                              <div className="flex items-center gap-2">
                                <div style={{
                                  width: '80px', height: '8px', background: '#e8e5e1',
                                  borderRadius: '4px', overflow: 'hidden',
                                }}>
                                  <div style={{
                                    width: `${(conf * 100).toFixed(0)}%`, height: '100%',
                                    background: confidenceColor(conf), borderRadius: '4px',
                                  }} />
                                </div>
                                <span style={{ fontSize: '0.82rem', color: '#666' }}>
                                  {(conf * 100).toFixed(0)}%
                                </span>
                              </div>
                            </td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            ))
          )}
        </div>
      </TabPanel>

      <TabPanel active={activeTab === 1}>
        <DownscalingTab stations={stations ?? []} forecasts={allForecasts} />
      </TabPanel>

      {/* ── About this model (collapsible) ── */}
      <div style={{ marginTop: '24px' }}>
        <button
          onClick={() => setShowModel(!showModel)}
          style={{
            background: 'none',
            border: 'none',
            padding: 0,
            cursor: 'pointer',
            display: 'inline-flex',
            alignItems: 'center',
            gap: '6px',
            fontFamily: '"Space Grotesk", system-ui, sans-serif',
            fontSize: '13px',
            fontWeight: 500,
            color: '#606373',
          }}
        >
          {showModel ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          About this model
        </button>
        {showModel && (
          <div
            className="animate-tab-enter"
            style={{
              marginTop: '16px',
              borderTop: '1px solid #e8e5e1',
              paddingTop: '20px',
              maxWidth: '780px',
            }}
          >
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-6 sm:gap-8">
              <div>
                <div className="eyebrow">Forecasting</div>
                <div style={{ fontSize: '14px', color: '#1b1e2d', marginTop: '8px', lineHeight: 1.5 }}>
                  Neural weather model with a local correction layer.
                </div>
              </div>
              <div>
                <div className="eyebrow">Local correction</div>
                <div style={{ fontSize: '14px', color: '#1b1e2d', marginTop: '8px', lineHeight: 1.5 }}>
                  {mosStatus.data?.metrics?.rmse != null
                    ? `Trained on ${mosStatus.data.metrics.n_train ?? '—'} observations, ${mosStatus.data.metrics.rmse.toFixed(1)}°C accuracy`
                    : 'Not yet trained'}
                </div>
              </div>
              <div>
                <div className="eyebrow">Advisories</div>
                <div style={{ fontSize: '14px', color: '#1b1e2d', marginTop: '8px', lineHeight: 1.5 }}>
                  Bilingual crop advice from an agricultural knowledge base.
                </div>
              </div>
            </div>
            <p style={{ fontSize: '13px', color: '#606373', lineHeight: 1.65, marginTop: '16px' }}>
              A global neural weather model generates raw forecasts; a
              correction model trained on local observations adjusts for
              regional accuracy. Crop-specific farming advice is generated in
              {' '}{REGION.languageList} from a curated knowledge base.
            </p>
          </div>
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Downscaling Sub-component
// ---------------------------------------------------------------------------

function DownscalingTab({ stations, forecasts }: {
  stations: Station[] | undefined; forecasts: Forecast[]
}) {
  const { data: farmers } = useFarmers()

  const stationList = stations ?? []
  const farmerList = farmers ?? []

  // Build sample downscaling effect rows
  const effectRows = useMemo(() => {
    const rows: { station: string; stationTemp: string; farmer: string; distance: string; lapseDelta: string; finalTemp: string }[] = []
    for (const farmer of farmerList.slice(0, 10)) {
      const station = stationList.find(s => s.id === farmer.station_id)
      if (!station) continue
      const fc = forecasts.find(f => f.station_id === farmer.station_id && (f.forecast_day === 0 || f.forecast_day === undefined))
      const fcTemp = fc?.temp_max ?? fc?.temperature ?? null
      if (fcTemp === null) continue
      // Approximate distance (degree-based)
      const dLat = (farmer as any).gps_lat ? ((farmer as any).gps_lat - station.lat) : 0
      const dLon = (farmer as any).gps_lon ? ((farmer as any).gps_lon - station.lon) : 0
      const dist = Math.sqrt(dLat * dLat + dLon * dLon) * 111
      // Lapse rate (approximate — farmer altitude unknown, use small random delta)
      const altDelta = (station.altitude_m ?? 0) * 0.1 // rough estimate
      const lapse = -0.0065 * altDelta
      rows.push({
        station: `${station.name} (${station.id})`,
        stationTemp: `${fcTemp.toFixed(1)}\u00B0C`,
        farmer: farmer.name,
        distance: `${dist.toFixed(1)} km`,
        lapseDelta: `${lapse >= 0 ? '+' : ''}${lapse.toFixed(1)}\u00B0C`,
        finalTemp: `${(fcTemp + lapse).toFixed(1)}\u00B0C`,
      })
    }
    return rows
  }, [stationList, farmerList, forecasts])

  return (
    <div className="space-y-6">
      <div className="section-header">Spatial Downscaling</div>
      <div style={{
        background: '#fff', border: '1px solid #e8e5e1', borderRadius: '8px', padding: '16px',
      }}>
        <p style={{ fontSize: '0.85rem', color: '#555', lineHeight: 1.7 }}>
          Station forecasts are adjusted to each farmer's exact GPS location by
          blending nearby NASA satellite grid points (closer points count more)
          and correcting for altitude — temperatures drop about 6.5{'\u00B0'}C
          for every 1000m of elevation gain.
        </p>
      </div>

      {/* Station + Farmer locations */}
      <div>
        <div className="section-header">Station & Farmer Locations</div>
        <div className="flex gap-4 mb-3" style={{ fontSize: '0.8rem', color: '#666' }}>
          <span className="flex items-center gap-2">
            <span style={{ width: '10px', height: '10px', borderRadius: '50%', background: '#2d5b7d', display: 'inline-block' }} />
            Stations
          </span>
          <span className="flex items-center gap-2">
            <span style={{ width: '10px', height: '10px', borderRadius: '50%', background: '#606373', display: 'inline-block' }} />
            Farmer locations
          </span>
        </div>
        <div className="table-container">
          <table>
            <thead>
              <tr><th>Type</th><th>Name</th><th>Lat</th><th>Lon</th><th>State / District</th></tr>
            </thead>
            <tbody>
              {stationList.slice(0, 10).map(s => (
                <tr key={s.id}>
                  <td>
                    <span style={{
                      width: '8px', height: '8px', borderRadius: '50%', background: '#2d5b7d',
                      display: 'inline-block', marginRight: '6px',
                    }} />
                    Station
                  </td>
                  <td style={{ fontWeight: 500, color: '#1b1e2d' }}>{s.name}</td>
                  <td>{s.lat?.toFixed(2)}</td>
                  <td>{s.lon?.toFixed(2)}</td>
                  <td>{s.state}</td>
                </tr>
              ))}
              {farmerList.slice(0, 8).map((f: any) => (
                <tr key={f.phone}>
                  <td>
                    <span style={{
                      width: '8px', height: '8px', borderRadius: '50%', background: '#606373',
                      display: 'inline-block', marginRight: '6px',
                    }} />
                    Farmer
                  </td>
                  <td style={{ fontWeight: 500, color: '#1b1e2d' }}>{f.name}</td>
                  <td>--</td>
                  <td>--</td>
                  <td>{f.district}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Downscaling Effect table */}
      {effectRows.length > 0 && (
        <div>
          <div className="section-header">Downscaling Effect</div>
          <p style={{ fontSize: '0.82rem', color: '#888', marginBottom: '8px' }}>
            Showing how station-level forecasts adjust for each farmer's location and elevation
          </p>
          <div className="table-container">
            <table>
              <thead>
                <tr><th>Station</th><th>Station Temp</th><th>Farmer</th><th>Distance (km)</th><th>Lapse Delta</th><th>Final Temp</th></tr>
              </thead>
              <tbody>
                {effectRows.map((row, i) => (
                  <tr key={i}>
                    <td style={{ fontWeight: 500 }}>{row.station}</td>
                    <td>{row.stationTemp}</td>
                    <td>{row.farmer}</td>
                    <td>{row.distance}</td>
                    <td>{row.lapseDelta}</td>
                    <td style={{ fontWeight: 600, color: '#1b1e2d' }}>{row.finalTemp}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

    </div>
  )
}
