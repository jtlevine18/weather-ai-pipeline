import { useState, useMemo } from 'react'
import { Clock } from 'lucide-react'
import { useAlerts, useStations, useForecasts, useDeliveryLog, useFarmers, useFarmerDetail } from '../api/hooks'
import { MetricCard } from '../components/MetricCard'
import { PageLoader } from '../components/LoadingSpinner'

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const CONDITION_COLOR: Record<string, string> = {
  heavy_rain: '#1565C0', moderate_rain: '#1976D2', heat_stress: '#C62828',
  drought_risk: '#E65100', frost_risk: '#0277BD', high_wind: '#455A64',
  foggy: '#546E7A', clear: '#2E7D32',
}

const CONDITION_EMOJI: Record<string, string> = {
  heavy_rain: '\u{1F327}\uFE0F', moderate_rain: '\u{1F326}\uFE0F',
  heat_stress: '\u{1F321}\uFE0F', drought_risk: '\u{1F335}',
  frost_risk: '\u2744\uFE0F', high_wind: '\u{1F4A8}',
  foggy: '\u{1F32B}\uFE0F', clear: '\u2600\uFE0F',
}

const STATUS_COLOR: Record<string, string> = {
  sent: '#2a9d8f', dry_run: '#2a9d8f', failed: '#e63946',
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatTime(dateStr: string | undefined): string {
  if (!dateStr) return '--'
  try {
    return new Date(dateStr).toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' })
  } catch { return dateStr }
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function Advisories() {
  const { data: alerts, isLoading, error } = useAlerts(200)
  const { data: stations } = useStations()
  const { data: forecasts } = useForecasts(500)
  const { data: deliveryLog } = useDeliveryLog(200)

  const [activeTab, setActiveTab] = useState(0)
  const [langFilter, setLangFilter] = useState('All')
  const [condFilter, setCondFilter] = useState('All')
  const [provFilter, setProvFilter] = useState('All')

  const stationMap = useMemo(() => {
    const map: Record<string, string> = {}
    stations?.forEach(s => { map[s.station_id] = s.name })
    return map
  }, [stations])

  const allAlerts = alerts ?? []
  const allDeliveries = deliveryLog ?? []

  // Metrics
  const totalAdvisories = allAlerts.length
  const ragCount = allAlerts.filter(a =>
    (a as any).provider === 'rag' || (a as any).provider === 'rag_claude'
  ).length
  const taCount = allAlerts.filter(a => a.language === 'ta').length
  const mlCount = allAlerts.filter(a => a.language === 'ml').length
  const sentCount = allDeliveries.filter(d => d.status === 'sent' || d.status === 'dry_run').length

  // Filter options
  const languages = useMemo(() => {
    const set = new Set(allAlerts.map(a => a.language).filter(Boolean))
    return ['All', ...Array.from(set)]
  }, [allAlerts])
  const conditions = useMemo(() => {
    const set = new Set(allAlerts.map(a => a.condition).filter(Boolean))
    return ['All', ...Array.from(set)]
  }, [allAlerts])
  const providers = useMemo(() => {
    const set = new Set(allAlerts.map(a => (a as any).provider).filter(Boolean))
    return ['All', ...Array.from(set)]
  }, [allAlerts])

  // Filtered alerts
  const filtered = useMemo(() => {
    let items = [...allAlerts]
    if (langFilter !== 'All') items = items.filter(a => a.language === langFilter)
    if (condFilter !== 'All') items = items.filter(a => a.condition === condFilter)
    if (provFilter !== 'All') items = items.filter(a => (a as any).provider === provFilter)
    return items
  }, [allAlerts, langFilter, condFilter, provFilter])

  if (isLoading) return <PageLoader label="Loading advisories..." />
  if (error) return <div className="text-center py-12"><p className="text-error text-sm">Failed to load advisories</p></div>

  const TABS = ['Advisory Feed', 'Lineage', 'Farmers & DPI', 'Delivery']

  return (
    <div className="space-y-6">
      <div>
        <h1 className="page-title">Advisories</h1>
        <p className="page-caption">
          Translation, delivery, and farmer profiles
        </p>
      </div>

      {/* 4 Metrics */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <MetricCard label="Total Advisories" value={totalAdvisories} />
        <MetricCard label="RAG+Claude" value={ragCount} />
        <MetricCard label="Tamil / Malayalam" value={`${taCount} / ${mlCount}`} />
        <MetricCard label="Deliveries" value={sentCount} />
      </div>

      {/* Tabs */}
      <div className="tab-list">
        {TABS.map((tab, i) => (
          <button key={tab} className={`tab-item ${activeTab === i ? 'active' : ''}`} onClick={() => setActiveTab(i)}>
            {tab}
          </button>
        ))}
      </div>

      {/* Advisory Feed */}
      {activeTab === 0 && (
        <div className="space-y-4">
          {/* Filters */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <select className="input" value={langFilter} onChange={e => setLangFilter(e.target.value)}>
              {languages.map(l => <option key={l}>{l}</option>)}
            </select>
            <select className="input" value={condFilter} onChange={e => setCondFilter(e.target.value)}>
              {conditions.map(c => <option key={c}>{c}</option>)}
            </select>
            <select className="input" value={provFilter} onChange={e => setProvFilter(e.target.value)}>
              {providers.map(p => <option key={p}>{p}</option>)}
            </select>
          </div>

          {filtered.length === 0 ? (
            <div className="card card-body text-center py-12">
              <p style={{ color: '#888', fontSize: '0.85rem' }}>No advisories match your filters</p>
            </div>
          ) : (
            <div className="space-y-2">
              {filtered.map((alert, i) => {
                const cond = alert.condition || ''
                const condColor = CONDITION_COLOR[cond] || '#888'
                const condEmoji = CONDITION_EMOJI[cond] || ''
                const name = alert.station_name || stationMap[alert.station_id] || alert.station_id
                const provider = (alert as any).provider || 'rag'
                const lang = alert.language || 'en'
                const forecastDays = (alert as any).forecast_days
                return (
                  <div
                    key={alert.id ?? i}
                    style={{
                      border: '1px solid #e0dcd5', borderLeft: `3px solid ${condColor}`,
                      borderRadius: '8px', padding: '10px 14px', marginBottom: '8px',
                      background: '#fff',
                    }}
                  >
                    {/* Header */}
                    <div className="flex items-center gap-2 flex-wrap">
                      <span style={{ fontSize: '1.1rem' }}>{condEmoji}</span>
                      <strong style={{ color: '#1a1a1a' }}>{name}</strong>
                      <span style={{ color: '#aaa', fontSize: '0.75rem' }}>{alert.station_id}</span>
                      {forecastDays >= 7 && (
                        <span style={{
                          background: '#4361ee', color: '#fff', padding: '2px 8px',
                          borderRadius: '10px', fontSize: '0.7rem',
                        }}>WEEKLY</span>
                      )}
                      {cond && (
                        <span style={{
                          background: condColor, color: '#fff', padding: '2px 8px',
                          borderRadius: '10px', fontSize: '0.7rem',
                        }}>{cond.replace(/_/g, ' ')}</span>
                      )}
                      <span style={{ marginLeft: 'auto', color: '#888', fontSize: '0.7rem' }}>
                        {provider} {'\u00B7'} {lang}
                      </span>
                    </div>

                    {/* Advisory text (local language) */}
                    {alert.advisory_local && (
                      <p style={{ color: '#555', fontSize: '0.85rem', lineHeight: 1.5, margin: '4px 0' }}>
                        {alert.advisory_local}
                      </p>
                    )}

                    {/* English (shown below if no local, or as secondary) */}
                    {alert.advisory_en && (
                      <p style={{
                        color: alert.advisory_local ? '#888' : '#555',
                        fontSize: '0.85rem', lineHeight: 1.5, margin: '4px 0',
                        fontStyle: alert.advisory_local ? 'italic' : 'normal',
                        paddingLeft: alert.advisory_local ? '12px' : '0',
                        borderLeft: alert.advisory_local ? '2px solid #e0dcd5' : 'none',
                      }}>
                        {alert.advisory_en}
                      </p>
                    )}

                    {/* Timestamp */}
                    <div style={{ color: '#aaa', fontSize: '0.72rem', marginTop: '2px' }}>
                      {formatTime(alert.issued_at || alert.created_at)}
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      )}

      {/* Lineage tab */}
      {activeTab === 1 && (
        <div className="space-y-4">
          <div className="section-header">Forecast to Advisory Lineage</div>
          {allAlerts.slice(0, 20).map((alert, i) => {
            const matchingFc = (forecasts ?? []).find(f =>
              f.station_id === alert.station_id && (f.forecast_day === 0 || f.forecast_day === undefined)
            )
            const name = alert.station_name || stationMap[alert.station_id] || alert.station_id
            const cond = alert.condition || ''
            const condColor = CONDITION_COLOR[cond] || '#888'
            return (
              <div key={alert.id ?? i} className="grid grid-cols-[1fr_auto_1fr] gap-4 items-start">
                {/* Forecast card */}
                <div style={{
                  background: '#fff', border: '1px solid #e0dcd5', borderRadius: '8px', padding: '12px',
                }}>
                  <div style={{ fontWeight: 600, color: '#1a1a1a' }}>{name}</div>
                  {matchingFc ? (
                    <div style={{ fontSize: '0.82rem', color: '#555', marginTop: '4px' }}>
                      {matchingFc.temp_max !== undefined ? `${matchingFc.temp_max.toFixed(1)}\u00B0C` : '--'}
                      {' \u00B7 '}
                      {matchingFc.rainfall_mm !== undefined ? `${matchingFc.rainfall_mm.toFixed(1)}mm` : '--'}
                    </div>
                  ) : (
                    <div style={{ fontSize: '0.82rem', color: '#999' }}>No forecast data</div>
                  )}
                  {cond && (
                    <span style={{
                      display: 'inline-block', marginTop: '6px',
                      background: condColor, color: '#fff', padding: '2px 8px',
                      borderRadius: '10px', fontSize: '0.7rem',
                    }}>{cond.replace(/_/g, ' ')}</span>
                  )}
                </div>

                {/* Arrow */}
                <div style={{ textAlign: 'center', paddingTop: '20px' }}>
                  <span style={{ color: '#d4a019', fontSize: '1.3rem' }}>{'\u2192'}</span>
                </div>

                {/* Advisory card */}
                <div style={{
                  background: '#fff', border: '1px solid #e0dcd5', borderLeft: '3px solid #d4a019',
                  borderRadius: '8px', padding: '12px',
                }}>
                  <div style={{ fontSize: '0.72rem', color: '#888' }}>
                    {(alert as any).provider || 'rag'} {'\u00B7'} {alert.language || 'en'}
                  </div>
                  <p style={{ color: '#555', fontSize: '0.82rem', lineHeight: 1.4, marginTop: '4px' }}>
                    {(alert.advisory_en || alert.advisory_local || '').slice(0, 150)}
                    {(alert.advisory_en || '').length > 150 ? '...' : ''}
                  </p>
                </div>
              </div>
            )
          })}
        </div>
      )}

      {/* Farmers & DPI tab */}
      {activeTab === 2 && <FarmersDPITab alerts={allAlerts} stationMap={stationMap} />}

      {/* Delivery tab */}
      {activeTab === 3 && (
        <div className="space-y-4">
          <div className="section-header">Delivery Status</div>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <MetricCard label="Sent / Dry-Run" value={sentCount} />
            <MetricCard label="Failed" value={allDeliveries.filter(d => d.status === 'failed').length} />
            <MetricCard label="Channels" value={new Set(allDeliveries.map(d => d.channel)).size || '--'} />
            <MetricCard label="Recipients" value={new Set(allDeliveries.map(d => d.recipient)).size || '--'} />
          </div>

          {allDeliveries.length === 0 ? (
            <div className="card card-body text-center py-8">
              <p style={{ color: '#888', fontSize: '0.85rem' }}>No delivery records yet</p>
            </div>
          ) : (
            <div className="table-container">
              <table>
                <thead>
                  <tr>
                    <th>Station</th>
                    <th>Channel</th>
                    <th>Recipient</th>
                    <th>Status</th>
                    <th>Message</th>
                    <th>Time</th>
                  </tr>
                </thead>
                <tbody>
                  {allDeliveries.map((d, i) => {
                    const sColor = STATUS_COLOR[d.status || ''] || '#888'
                    return (
                      <tr key={d.id ?? i}>
                        <td>{d.station_id || '--'}</td>
                        <td>{d.channel || '--'}</td>
                        <td style={{ fontSize: '0.82rem' }}>{d.recipient || '--'}</td>
                        <td>
                          <span style={{
                            background: `${sColor}26`, color: sColor,
                            padding: '2px 8px', borderRadius: '4px',
                            fontSize: '0.78rem', fontWeight: 600,
                          }}>
                            {d.status || '--'}
                          </span>
                        </td>
                        <td style={{ fontSize: '0.82rem', color: '#555', maxWidth: '200px' }} className="truncate">
                          {(d.message_preview || '').slice(0, 80)}
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
          )}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Farmers & DPI Sub-component
// ---------------------------------------------------------------------------

function DPICard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{
      background: '#fff', border: '1px solid #e0dcd5', borderRadius: '8px',
      padding: '16px', marginTop: '10px',
    }}>
      <div style={{
        fontWeight: 600, color: '#666', fontSize: '0.75rem',
        textTransform: 'uppercase', letterSpacing: '1px',
      }}>{title}</div>
      <div style={{ fontSize: '0.85rem', color: '#555', marginTop: '6px', lineHeight: 1.7 }}>
        {children}
      </div>
    </div>
  )
}

function FarmersDPITab({ alerts, stationMap }: {
  alerts: any[]; stationMap: Record<string, string>
}) {
  const { data: farmers, isLoading } = useFarmers()
  const [selectedPhone, setSelectedPhone] = useState('')
  const { data: detail } = useFarmerDetail(selectedPhone)

  if (isLoading) return <p style={{ color: '#888', fontSize: '0.85rem' }}>Loading farmers...</p>
  if (!farmers || farmers.length === 0) {
    return (
      <div className="card card-body text-center py-8">
        <p style={{ color: '#888', fontSize: '0.85rem' }}>No farmer data available. Run the pipeline first.</p>
      </div>
    )
  }

  const farmerLabels = farmers.map(f => ({
    label: `${f.name} \u2014 ${f.district}, ${f.station}`,
    phone: f.phone,
  }))

  const selectedFarmer = farmers.find(f => f.phone === selectedPhone)

  // Find latest advisory for this farmer's station
  const stationAlert = selectedFarmer
    ? alerts.find(a => a.station_id === selectedFarmer.station)
    : null

  return (
    <div className="space-y-4">
      <div className="section-header">Farmer Profiles & DPI Context</div>
      <p style={{ color: '#888', fontSize: '0.82rem' }}>
        Digital Public Infrastructure data from simulated government services
      </p>

      {/* Farmer selector */}
      <select
        className="input"
        value={selectedPhone}
        onChange={e => setSelectedPhone(e.target.value)}
      >
        <option value="">Select a farmer...</option>
        {farmerLabels.map(f => (
          <option key={f.phone} value={f.phone}>{f.label}</option>
        ))}
      </select>

      {detail && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Left column — Identity + Land */}
          <div>
            {/* Identity card */}
            <div style={{
              background: '#fff', border: '1px solid #e0dcd5', borderRadius: '8px', padding: '16px',
            }}>
              <div style={{ fontWeight: 700, fontSize: '1.1rem', color: '#1a1a1a' }}>
                {detail.aadhaar.name}
              </div>
              <div style={{ color: '#888', fontSize: '0.9rem' }}>
                {detail.aadhaar.name_local}
              </div>
              <div style={{ marginTop: '8px', fontSize: '0.85rem', color: '#555', lineHeight: 1.7 }}>
                District: {detail.aadhaar.district}, {detail.aadhaar.state}<br />
                Language: {detail.aadhaar.language.toUpperCase()}<br />
                Crops: {detail.primary_crops.join(', ')}<br />
                Total area: {detail.total_area.toFixed(2)} ha
              </div>
            </div>

            {/* Land Record */}
            {detail.land_records.length > 0 && (
              <DPICard title="Land Record">
                {detail.land_records.map((lr, i) => (
                  <div key={i}>
                    Survey: {lr.survey_number}<br />
                    GPS: {lr.gps_lat.toFixed(4)}, {lr.gps_lon.toFixed(4)}<br />
                    Soil: {lr.soil_type}<br />
                    Irrigation: {lr.irrigation_type}<br />
                    Area: {lr.area_hectares.toFixed(2)} ha
                  </div>
                ))}
              </DPICard>
            )}
          </div>

          {/* Right column — DPI services */}
          <div>
            {detail.soil_health && (
              <DPICard title="Soil Health Card">
                pH: {detail.soil_health.pH.toFixed(1)} {'\u00B7'} Classification: {detail.soil_health.classification}<br />
                N/P/K: {detail.soil_health.nitrogen_kg_ha.toFixed(0)} / {detail.soil_health.phosphorus_kg_ha.toFixed(0)} / {detail.soil_health.potassium_kg_ha.toFixed(0)} kg/ha<br />
                Organic Carbon: {detail.soil_health.organic_carbon_pct.toFixed(1)}%
              </DPICard>
            )}

            {detail.pmkisan && (
              <DPICard title="PM-KISAN">
                Installments received: {detail.pmkisan.installments_received}<br />
                Total amount: Rs {detail.pmkisan.total_amount.toLocaleString('en-IN')}
              </DPICard>
            )}

            {detail.pmfby && (
              <DPICard title="PMFBY Crop Insurance">
                Status: {detail.pmfby.status}<br />
                Sum insured: Rs {detail.pmfby.sum_insured.toLocaleString('en-IN')}<br />
                Premium paid: Rs {detail.pmfby.premium_paid.toLocaleString('en-IN')}
              </DPICard>
            )}

            {detail.kcc && (
              <DPICard title="Kisan Credit Card">
                Credit limit: Rs {detail.kcc.credit_limit.toLocaleString('en-IN')}<br />
                Outstanding: Rs {detail.kcc.outstanding.toLocaleString('en-IN')}<br />
                Repayment: {detail.kcc.repayment_status}
              </DPICard>
            )}
          </div>
        </div>
      )}

      {/* Latest advisory for this farmer */}
      {detail && stationAlert && (
        <div>
          <div className="section-header" style={{ marginTop: '24px' }}>
            Latest Advisory for This Farmer
          </div>
          <div style={{
            background: '#fff', border: '1px solid #e0dcd5',
            borderLeft: `3px solid ${CONDITION_COLOR[stationAlert.condition || ''] || '#888'}`,
            borderRadius: '8px', padding: '14px',
          }}>
            {stationAlert.condition && (
              <span style={{
                background: CONDITION_COLOR[stationAlert.condition] || '#888',
                color: '#fff', padding: '2px 8px', borderRadius: '10px',
                fontSize: '0.7rem', fontWeight: 600,
              }}>
                {stationAlert.condition.replace(/_/g, ' ')}
              </span>
            )}
            <span style={{ color: '#888', fontSize: '0.75rem', marginLeft: '8px' }}>
              {(stationAlert as any).provider || 'rag'} {'\u00B7'} {stationAlert.language || 'en'}
            </span>
            <div style={{ color: '#555', fontSize: '0.85rem', lineHeight: 1.5, marginTop: '8px' }}>
              {(stationAlert.advisory_local || stationAlert.advisory_en || '').slice(0, 300)}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
