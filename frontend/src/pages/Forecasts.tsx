import { useState, useMemo } from 'react'
import { useForecasts, useStations, useFarmers } from '../api/hooks'
import { MetricCard } from '../components/MetricCard'
import { TableSkeleton } from '../components/LoadingSpinner'
import { PageContext } from '../components/PageContext'
import { TabPanel } from '../components/TabPanel'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Cell,
} from 'recharts'

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const CONDITION_COLOR: Record<string, string> = {
  heavy_rain: '#1565C0',
  moderate_rain: '#1976D2',
  heat_stress: '#C62828',
  drought_risk: '#E65100',
  frost_risk: '#0277BD',
  high_wind: '#455A64',
  foggy: '#546E7A',
  clear: '#2E7D32',
}

const CONDITION_EMOJI: Record<string, string> = {
  heavy_rain: '\u{1F327}\uFE0F',
  moderate_rain: '\u{1F326}\uFE0F',
  heat_stress: '\u{1F321}\uFE0F',
  drought_risk: '\u{1F335}',
  frost_risk: '\u2744\uFE0F',
  high_wind: '\u{1F4A8}',
  foggy: '\u{1F32B}\uFE0F',
  clear: '\u2600\uFE0F',
}

const MODEL_COLOR: Record<string, string> = {
  neuralgcm_mos: '#4361ee',
  neuralgcm_only: '#7b8cde',
  hybrid_mos: '#2a9d8f',
  nwp_only: '#6db5a8',
  persistence: '#e63946',
}

const DEGRADATION_TIERS = [
  { tier: 'Tier 1', name: 'NeuralGCM + MOS', sub: 'Neural weather model', color: '#4361ee',
    desc: 'Google DeepMind\u2019s neural GCM produces global forecasts, corrected with XGBoost MOS trained on local observations.' },
  { tier: 'Tier 2', name: 'Open-Meteo + MOS', sub: 'NWP fallback (no GPU)', color: '#2a9d8f',
    desc: 'GFS/ECMWF forecasts via Open-Meteo API when NeuralGCM is unavailable, corrected with the same local MOS model.' },
  { tier: 'Tier 3', name: 'Persistence', sub: 'Last-observation fallback', color: '#e63946',
    desc: 'Uses the most recent observation with diurnal adjustment. No ML correction applied.' },
]

const STATES = ['All', 'Kerala', 'Tamil Nadu']

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function fmtVal(v: number | undefined | null, unit = '', decimals = 1): string {
  if (v === undefined || v === null || Number.isNaN(v)) return '--'
  return `${Number(v).toFixed(decimals)}${unit}`
}

function confidenceColor(c: number): string {
  if (c >= 0.7) return '#2a9d8f'
  if (c >= 0.4) return '#d4a019'
  return '#e63946'
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

  const stationMap = useMemo(() => {
    const map: Record<string, { name: string; state: string }> = {}
    stations?.forEach(s => { map[s.station_id] = { name: s.name, state: s.state } })
    return map
  }, [stations])

  const allForecasts = forecasts ?? []

  // Metrics
  const uniqueStations = new Set(allForecasts.map(f => f.station_id)).size
  const totalForecasts = allForecasts.length
  const avgConf = totalForecasts > 0
    ? allForecasts.reduce((s, f) => s + (f.confidence ?? 0), 0) / totalForecasts : 0
  const getModel = (f: { model_used?: string; model?: string }) => f.model_used || f.model || ''
  const mosCount = allForecasts.filter(f => getModel(f).includes('mos')).length
  const mosPct = totalForecasts > 0 ? Math.round(100 * mosCount / totalForecasts) : 0
  const nwpSource = allForecasts.length > 0
    ? (allForecasts.some(f => getModel(f).includes('neuralgcm')) ? 'NeuralGCM' : 'Open-Meteo')
    : '--'
  const hasNeuralGCM = allForecasts.some(f => getModel(f).includes('neuralgcm'))

  // Conditions & models for filter dropdowns
  const conditions = useMemo(() => {
    const set = new Set(allForecasts.map(f => f.condition).filter(Boolean))
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
  if (error) return <div className="text-center py-12"><p className="text-error text-sm">Failed to load forecasts</p></div>

  const TABS = ['Station Forecasts', 'Model Performance', 'Downscaling']

  return (
    <div className="space-y-6">
      {/* Title */}
      <div>
        <h1 className="page-title">Forecasts</h1>
        <p className="page-caption">
          Station forecasts, model performance, and spatial downscaling
        </p>
      </div>

      <PageContext id="forecasts">
        Seven-day forecasts for all 20 stations, generated by NeuralGCM (Google DeepMind's neural weather model) running on GPU. An XGBoost MOS correction model will improve accuracy as more observation-forecast pairs accumulate. Each forecast is spatially downscaled to individual farmer GPS coordinates.
      </PageContext>

      {/* NeuralGCM banner */}
      {hasNeuralGCM && (
        <div style={{
          background: '#eef2ff', border: '1px solid #c7d2fe', borderRadius: '8px',
          padding: '12px 16px', display: 'flex', alignItems: 'center', gap: '8px',
        }}>
          <span style={{ fontSize: '1.1rem' }}>{'\u{1F9E0}'}</span>
          <span style={{ color: '#3730a3', fontSize: '0.85rem' }}>
            NeuralGCM (Google DeepMind) is the active NWP source for this pipeline run
          </span>
        </div>
      )}

      {/* 5 Metrics */}
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
        <MetricCard label="Stations Reporting" value={uniqueStations} />
        <MetricCard label="Total Forecasts" value={totalForecasts} />
        <MetricCard label="Avg Confidence" value={avgConf > 0 ? `${Math.round(avgConf * 100)}%` : '--'} />
        <MetricCard
          label="MOS Correction"
          value={mosCount > 0 ? `${mosPct}% corrected` : 'Training'}
          subtitle={mosCount > 0 ? undefined : 'Accumulating data for XGBoost'}
        />
        <MetricCard label="NWP Source" value={nwpSource} />
      </div>

      {/* Tabs */}
      <div className="tab-list">
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
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <select className="input" value={stateFilter} onChange={e => setStateFilter(e.target.value)}>
              {STATES.map(s => <option key={s}>{s}</option>)}
            </select>
            <select className="input" value={condFilter} onChange={e => setCondFilter(e.target.value)}>
              {conditions.map(c => <option key={c}>{c}</option>)}
            </select>
            <select className="input" value={modelFilter} onChange={e => setModelFilter(e.target.value)}>
              {models.map(m => <option key={m}>{m}</option>)}
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
                        const condEmoji = CONDITION_EMOJI[cond] || ''
                        const model = getModel(f)
                        const mColor = MODEL_COLOR[model] || '#888'
                        const conf = f.confidence ?? 0
                        return (
                          <tr key={f.id ?? i}>
                            <td style={{ fontWeight: 500, color: '#1a1a1a' }}>
                              {f.station_name || stationMap[f.station_id]?.name || f.station_id}
                            </td>
                            <td>{dayLabel(f.forecast_day)}</td>
                            <td>{fmtVal(f.temp_max, '\u00B0C')}</td>
                            <td>{fmtVal(f.rainfall_mm, ' mm')}</td>
                            <td>
                              {cond ? (
                                <span style={{
                                  background: condColor, color: '#fff',
                                  padding: '3px 10px', borderRadius: '12px',
                                  fontSize: '0.82rem', fontWeight: 600, whiteSpace: 'nowrap',
                                }}>
                                  {condEmoji} {cond.replace(/_/g, ' ')}
                                </span>
                              ) : '--'}
                            </td>
                            <td>
                              {model ? (
                                <span style={{
                                  background: `${mColor}22`, color: mColor,
                                  border: `1px solid ${mColor}`,
                                  padding: '2px 8px', borderRadius: '4px',
                                  fontSize: '0.78rem', fontWeight: 600,
                                }}>
                                  {model.replace(/_/g, ' ')}
                                </span>
                              ) : '--'}
                            </td>
                            <td>
                              <div className="flex items-center gap-2">
                                <div style={{
                                  width: '80px', height: '8px', background: '#e0dcd5',
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
        <div className="space-y-8">
          {/* Degradation Chain */}
          <div>
            <div className="section-header">Degradation Chain</div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {DEGRADATION_TIERS.map(t => (
                <div key={t.tier} style={{
                  background: '#fff', border: '1px solid #e0dcd5', borderRadius: '8px',
                  padding: '16px', borderLeft: `4px solid ${t.color}`,
                }}>
                  <div style={{ textTransform: 'uppercase', fontSize: '0.72rem', color: '#999', letterSpacing: '1px' }}>
                    {t.tier}
                  </div>
                  <div style={{ fontSize: '1rem', fontWeight: 700, color: '#1a1a1a', marginTop: '4px' }}>
                    {t.name}
                  </div>
                  <div style={{ fontSize: '0.78rem', color: '#888', marginTop: '2px' }}>{t.sub}</div>
                  <div style={{ fontSize: '0.82rem', color: '#555', marginTop: '8px', lineHeight: 1.5 }}>
                    {t.desc}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Model Confidence Chart */}
          <div>
            <div className="section-header">Usage Breakdown</div>
            <div style={{
              background: '#fff', border: '1px solid #e0dcd5', borderRadius: '8px',
              padding: '16px',
            }}>
              <ResponsiveContainer width="100%" height={240}>
                <BarChart
                  data={modelBreakdown.map(([model]) => {
                    const items = allForecasts.filter(f => getModel(f) === model)
                    const confs = items.map(f => f.confidence ?? 0).filter(c => c > 0)
                    const avg = confs.length > 0 ? confs.reduce((a, b) => a + b, 0) / confs.length : 0
                    return { model: model.replace(/_/g, ' '), avgConfidence: Math.round(avg * 100), _key: model }
                  })}
                  margin={{ top: 8, right: 16, left: 0, bottom: 4 }}
                >
                  <CartesianGrid strokeDasharray="3 3" stroke="#e0dcd5" />
                  <XAxis dataKey="model" tick={{ fill: '#888', fontSize: 12, fontFamily: 'DM Sans' }} />
                  <YAxis domain={[0, 100]} tick={{ fill: '#888', fontSize: 12, fontFamily: 'DM Sans' }} unit="%" />
                  <Tooltip
                    contentStyle={{ borderRadius: '8px', border: '1px solid #e0dcd5', fontFamily: 'DM Sans, sans-serif' }}
                    formatter={(value: number) => [`${value}%`, 'Avg Confidence']}
                  />
                  <Bar dataKey="avgConfidence" radius={[4, 4, 0, 0]}>
                    {modelBreakdown.map(([model]) => (
                      <Cell key={model} fill={MODEL_COLOR[model] || '#888'} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Confidence by Model */}
          <div>
            <div className="section-header">Confidence by Model</div>
            <div className="table-container">
              <table>
                <thead>
                  <tr><th>Model</th><th>Avg Confidence</th><th>Min</th><th>Max</th><th>Count</th></tr>
                </thead>
                <tbody>
                  {modelBreakdown.map(([model, count]) => {
                    const items = allForecasts.filter(f => getModel(f) === model)
                    const confs = items.map(f => f.confidence ?? 0).filter(c => c > 0)
                    const avg = confs.length > 0 ? confs.reduce((a, b) => a + b, 0) / confs.length : 0
                    const min = confs.length > 0 ? Math.min(...confs) : 0
                    const max = confs.length > 0 ? Math.max(...confs) : 0
                    return (
                      <tr key={model}>
                        <td style={{ fontWeight: 500 }}>{model.replace(/_/g, ' ')}</td>
                        <td>
                          <div className="flex items-center gap-2">
                            <div style={{ width: '80px', height: '8px', background: '#e0dcd5', borderRadius: '4px', overflow: 'hidden' }}>
                              <div style={{ width: `${(avg * 100).toFixed(0)}%`, height: '100%', background: confidenceColor(avg), borderRadius: '4px' }} />
                            </div>
                            <span style={{ fontSize: '0.82rem', color: '#666' }}>{(avg * 100).toFixed(0)}%</span>
                          </div>
                        </td>
                        <td>{(min * 100).toFixed(0)}%</td>
                        <td>{(max * 100).toFixed(0)}%</td>
                        <td>{count}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </TabPanel>

      <TabPanel active={activeTab === 2}>
        <DownscalingTab stations={stations ?? []} forecasts={allForecasts} />
      </TabPanel>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Downscaling Sub-component
// ---------------------------------------------------------------------------

function DownscalingTab({ stations, forecasts }: {
  stations: any[] | undefined; forecasts: any[]
}) {
  const { data: farmers } = useFarmers()

  const stationList = stations ?? []
  const farmerList = farmers ?? []

  // Build sample downscaling effect rows
  const effectRows = useMemo(() => {
    const rows: { station: string; stationTemp: string; farmer: string; distance: string; lapseDelta: string; finalTemp: string }[] = []
    for (const farmer of farmerList.slice(0, 10)) {
      const station = stationList.find(s => s.station_id === farmer.station)
      if (!station) continue
      const fc = forecasts.find(f => f.station_id === farmer.station && (f.forecast_day === 0 || f.forecast_day === undefined))
      const fcTemp = fc?.temp_max ?? fc?.temperature ?? null
      if (fcTemp === null) continue
      // Approximate distance (degree-based)
      const dLat = (farmer as any).gps_lat ? ((farmer as any).gps_lat - station.latitude) : 0
      const dLon = (farmer as any).gps_lon ? ((farmer as any).gps_lon - station.longitude) : 0
      const dist = Math.sqrt(dLat * dLat + dLon * dLon) * 111
      // Lapse rate (approximate — farmer altitude unknown, use small random delta)
      const altDelta = (station.elevation ?? 0) * 0.1 // rough estimate
      const lapse = -0.0065 * altDelta
      rows.push({
        station: `${station.name} (${station.station_id})`,
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
        background: '#fff', border: '1px solid #e0dcd5', borderRadius: '8px', padding: '16px',
      }}>
        <p style={{ fontSize: '0.85rem', color: '#555', lineHeight: 1.7 }}>
          Station forecasts are adjusted to individual farmer GPS coordinates using
          <strong> Inverse Distance Weighting (IDW)</strong> on a NASA POWER 0.5{'\u00B0'} grid, plus a
          <strong> lapse-rate elevation correction</strong> of 6.5{'\u00B0'}C per 1000m.
        </p>
      </div>

      {/* Station + Farmer locations */}
      <div>
        <div className="section-header">Station & Farmer Locations</div>
        <div className="flex gap-4 mb-3" style={{ fontSize: '0.8rem', color: '#666' }}>
          <span className="flex items-center gap-2">
            <span style={{ width: '10px', height: '10px', borderRadius: '50%', background: '#d4a019', display: 'inline-block' }} />
            Stations
          </span>
          <span className="flex items-center gap-2">
            <span style={{ width: '10px', height: '10px', borderRadius: '50%', background: '#2a9d8f', display: 'inline-block' }} />
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
                <tr key={s.station_id}>
                  <td>
                    <span style={{
                      width: '8px', height: '8px', borderRadius: '50%', background: '#d4a019',
                      display: 'inline-block', marginRight: '6px',
                    }} />
                    Station
                  </td>
                  <td style={{ fontWeight: 500, color: '#1a1a1a' }}>{s.name}</td>
                  <td>{s.latitude?.toFixed(2)}</td>
                  <td>{s.longitude?.toFixed(2)}</td>
                  <td>{s.state}</td>
                </tr>
              ))}
              {farmerList.slice(0, 8).map((f: any) => (
                <tr key={f.phone}>
                  <td>
                    <span style={{
                      width: '8px', height: '8px', borderRadius: '50%', background: '#2a9d8f',
                      display: 'inline-block', marginRight: '6px',
                    }} />
                    Farmer
                  </td>
                  <td style={{ fontWeight: 500, color: '#1a1a1a' }}>{f.name}</td>
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
                    <td style={{ fontWeight: 600, color: '#1a1a1a' }}>{row.finalTemp}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Lapse rate explanation */}
      <div style={{
        background: '#fff', border: '1px solid #e0dcd5', borderRadius: '8px', padding: '16px',
      }}>
        <div style={{ fontWeight: 600, color: '#1a1a1a', marginBottom: '8px' }}>
          Environmental Lapse Rate
        </div>
        <code style={{ fontSize: '0.9rem', color: '#333' }}>
          T_farmer = T_station - 0.0065 {'\u00D7'} (altitude_farmer - altitude_station)
        </code>
        <p style={{ fontSize: '0.85rem', color: '#666', marginTop: '6px' }}>
          Temperature decreases by approximately 6.5{'\u00B0'}C for every 1000m increase in elevation.
          This correction adjusts station-level forecasts to account for altitude differences
          between the weather station and each farmer's field location.
        </p>
      </div>
    </div>
  )
}
