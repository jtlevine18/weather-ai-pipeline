import { useState, useMemo } from 'react'
import { useAlerts, useStations, useForecasts, useDeliveryLog, useFarmers, useFarmerDetail, type Alert } from '../api/hooks'
import { MetricCard } from '../components/MetricCard'
import { TableSkeleton } from '../components/LoadingSpinner'
import { TabPanel } from '../components/TabPanel'
import { REGION } from '../regionConfig'
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
    stations?.forEach(s => { map[s.id] = s.name })
    return map
  }, [stations])

  const allAlerts = alerts ?? []
  const allDeliveries = deliveryLog ?? []

  // Metrics
  const totalAdvisories = allAlerts.length
  const ragCount = allAlerts.filter(a =>
    a.provider === 'rag' || a.provider === 'rag_claude'
  ).length
  const taCount = allAlerts.filter(a => a.language === 'ta').length
  const mlCount = allAlerts.filter(a => a.language === 'ml').length
  const sentCount = allDeliveries.filter(d => d.status === 'sent' || d.status === 'dry_run').length

  // Filter options
  const languages = useMemo(() => {
    const set = new Set(allAlerts.map(a => a.language).filter((x): x is string => !!x))
    return ['All', ...Array.from(set)]
  }, [allAlerts])
  const conditions = useMemo(() => {
    const set = new Set(allAlerts.map(a => a.condition).filter((x): x is string => !!x))
    return ['All', ...Array.from(set)]
  }, [allAlerts])
  const providers = useMemo(() => {
    const set = new Set(allAlerts.map(a => a.provider).filter((x): x is string => !!x))
    return ['All', ...Array.from(set)]
  }, [allAlerts])

  // Filtered alerts
  const filtered = useMemo(() => {
    let items = [...allAlerts]
    if (langFilter !== 'All') items = items.filter(a => a.language === langFilter)
    if (condFilter !== 'All') items = items.filter(a => a.condition === condFilter)
    if (provFilter !== 'All') items = items.filter(a => a.provider === provFilter)
    return items
  }, [allAlerts, langFilter, condFilter, provFilter])

  if (isLoading) return (
    <div>
      <div className="pt-2 pb-6"><h1 className="page-title" style={{ fontFamily: '"Source Serif 4", serif' }}>Advisories</h1></div>
      <TableSkeleton />
    </div>
  )
  if (error) return <div className="text-center py-12"><p className="text-crit text-sm">Failed to load advisories</p></div>

  const TABS = ['Advisory Feed', 'Lineage', 'Farmer Profiles', 'Delivery']

  return (
    <div className="space-y-8">
      <div>
        <h1 className="page-title" data-tour="advisories-title">
          Advisories
        </h1>
        <p className="page-caption" style={{ maxWidth: '680px' }}>
          Farming advice generated weekly and translated into Tamil and Malayalam.
        </p>
      </div>

      {/* 4 Metrics */}
      <div
        data-tour="advisories-metrics"
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(4, 1fr)',
          gap: '32px',
          borderTop: '1px solid #e8e5e1',
          paddingTop: '28px',
        }}
      >
        <MetricCard label="Total Advisories" value={totalAdvisories} />
        <MetricCard label="AI-generated" value={ragCount} />
        <MetricCard label={REGION.languageMetric} value={`${taCount} / ${mlCount}`} />
        <MetricCard label="Deliveries" value={sentCount} />
      </div>

      {/* Tabs */}
      <div data-tour="advisories-tabs" className="tab-list">
        {TABS.map((tab, i) => (
          <button key={tab} className={`tab-item ${activeTab === i ? 'active' : ''}`} onClick={() => setActiveTab(i)}>
            {tab}
          </button>
        ))}
      </div>

      {/* Advisory Feed */}
      <TabPanel active={activeTab === 0}>
        <div className="space-y-4">
          {/* Filters */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <select className="input" value={langFilter} onChange={e => setLangFilter(e.target.value)}>
              {languages.map(l => <option key={l} value={l}>{l === 'All' ? 'All' : (LANG_LABEL[l] ?? l)}</option>)}
            </select>
            <select className="input" value={condFilter} onChange={e => setCondFilter(e.target.value)}>
              {conditions.map(c => <option key={c} value={c}>{c === 'All' ? 'All' : (CONDITION_LABEL[c] ?? c)}</option>)}
            </select>
            <select className="input" value={provFilter} onChange={e => setProvFilter(e.target.value)}>
              {providers.map(p => <option key={p} value={p}>{p === 'All' ? 'All' : (PROVIDER_LABEL[p] ?? p)}</option>)}
            </select>
          </div>

          {filtered.length === 0 ? (
            <p style={{ color: '#8d909e', fontSize: '13px', padding: '32px 0' }}>
              No advisories match your filters
            </p>
          ) : (
            <div style={{ borderTop: '1px solid #e8e5e1' }}>
              {filtered.map((alert, i) => {
                const cond = alert.condition || ''
                const condColor = CONDITION_COLOR[cond] || '#606373'
                const name = alert.station_name || stationMap[alert.station_id] || alert.station_id
                const provider = alert.provider || 'rag'
                const lang = alert.language || 'en'
                return (
                  <div
                    key={alert.id ?? i}
                    style={{
                      borderBottom: '1px solid #e8e5e1',
                      padding: '20px 0',
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
                      <span style={{ color: '#1b1e2d', fontWeight: 500 }}>{name}</span>
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
                      <span style={{ marginLeft: 'auto', color: '#8d909e' }}>
                        {formatTime(alert.issued_at || alert.created_at)}
                      </span>
                    </div>

                    {/* Local-language advisory */}
                    {alert.advisory_local && (
                      <p
                        style={{
                          fontFamily: '"Source Serif 4", "Noto Serif Malayalam", "Noto Serif Tamil", Georgia, serif',
                          fontSize: '14px',
                          lineHeight: 1.6,
                          color: '#1b1e2d',
                          marginTop: '12px',
                          maxWidth: '100%',
                          overflowWrap: 'break-word',
                          wordBreak: 'break-word',
                          whiteSpace: 'pre-wrap',
                        }}
                      >
                        {alert.advisory_local}
                      </p>
                    )}

                    {/* English translation */}
                    {alert.advisory_en && (
                      <p
                        style={{
                          fontFamily: '"Space Grotesk", system-ui, sans-serif',
                          fontSize: '12px',
                          lineHeight: 1.65,
                          color: '#606373',
                          marginTop: alert.advisory_local ? '8px' : '12px',
                          maxWidth: '100%',
                          overflowWrap: 'break-word',
                          wordBreak: 'break-word',
                          whiteSpace: 'pre-wrap',
                        }}
                      >
                        {alert.advisory_en}
                      </p>
                    )}
                  </div>
                )
              })}
            </div>
          )}
        </div>
      </TabPanel>

      {/* Lineage tab */}
      <TabPanel active={activeTab === 1}>
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
                  background: '#fff', border: '1px solid #e8e5e1', borderRadius: '8px', padding: '12px',
                }}>
                  <div style={{ fontWeight: 600, color: '#1b1e2d' }}>{name}</div>
                  {matchingFc ? (
                    <div style={{ fontSize: '0.82rem', color: '#555', marginTop: '4px' }}>
                      {(() => {
                        const t = matchingFc.temp_max ?? matchingFc.temperature
                        return t !== undefined ? `${t.toFixed(1)}\u00B0C` : '--'
                      })()}
                      {' \u00B7 '}
                      {matchingFc.rainfall !== undefined ? `${matchingFc.rainfall.toFixed(1)}mm` : '--'}
                    </div>
                  ) : (
                    <div style={{ fontSize: '0.82rem', color: '#999' }}>No forecast data</div>
                  )}
                  {cond && (
                    <span style={{
                      display: 'inline-block', marginTop: '6px',
                      background: condColor, color: '#fff', padding: '2px 8px',
                      borderRadius: '10px', fontSize: '0.7rem',
                    }}>{CONDITION_LABEL[cond] ?? cond.replace(/_/g, ' ')}</span>
                  )}
                </div>

                {/* Arrow */}
                <div style={{ textAlign: 'center', paddingTop: '20px' }}>
                  <span style={{ color: '#2d5b7d', fontSize: '1.3rem' }}>{'\u2192'}</span>
                </div>

                {/* Advisory card */}
                <div style={{
                  background: '#fff', border: '1px solid #e8e5e1', borderLeft: '3px solid #2d5b7d',
                  borderRadius: '8px', padding: '12px',
                }}>
                  <div style={{ fontSize: '0.72rem', color: '#888' }}>
                    {PROVIDER_LABEL[alert.provider || 'rag'] ?? (alert.provider || 'rag')} {'\u00B7'} {LANG_LABEL[alert.language || 'en'] ?? (alert.language || 'en')}
                  </div>
                  <p style={{ color: '#555', fontSize: '0.82rem', lineHeight: 1.4, marginTop: '4px', maxWidth: '100%', overflowWrap: 'break-word', wordBreak: 'break-word' }}>
                    {(alert.advisory_en || alert.advisory_local || '').slice(0, 150)}
                    {(alert.advisory_en || alert.advisory_local || '').length > 150 ? '...' : ''}
                  </p>
                </div>
              </div>
            )
          })}
        </div>
      </TabPanel>

      {/* Farmers & DPI tab */}
      <TabPanel active={activeTab === 2}>
        <FarmersDPITab alerts={allAlerts} stationMap={stationMap} />
      </TabPanel>

      {/* Delivery tab */}
      <TabPanel active={activeTab === 3}>
        <div className="space-y-4">
          <div className="section-header">Delivery Status</div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
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
                          <span style={{ color: sColor, fontSize: '13px' }}>
                            {d.status || '—'}
                          </span>
                        </td>
                        <td style={{ fontSize: '0.82rem', color: '#555', maxWidth: '200px' }} className="truncate">
                          {(d.message || '').slice(0, 80)}
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
      </TabPanel>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Farmers & DPI Sub-component
// ---------------------------------------------------------------------------

function DPICard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{
      background: '#fff', border: '1px solid #e8e5e1', borderRadius: '8px',
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
  alerts: Alert[]; stationMap: Record<string, string>
}) {
  const { data: farmers, isLoading } = useFarmers()
  const [selectedPhone, setSelectedPhone] = useState('')
  const { data: detail } = useFarmerDetail(selectedPhone)

  if (isLoading) return <p style={{ color: '#888', fontSize: '0.85rem' }}>Loading farmers...</p>
  if (!farmers || farmers.length === 0) {
    return (
      <div className="card card-body text-center py-8">
        <p style={{ color: '#888', fontSize: '0.85rem' }}>
          No farmer profiles cached yet. Profiles populate as the conversation agent
          looks up farmers by phone, or after the DPI eval suite runs.
        </p>
      </div>
    )
  }

  const farmerLabels = farmers.map(f => ({
    label: `${f.name} \u2014 ${f.district}, ${f.station_id}`,
    phone: f.phone,
  }))

  const selectedFarmer = farmers.find(f => f.phone === selectedPhone)

  // Find latest advisory for this farmer's station
  const stationAlert = selectedFarmer
    ? alerts.find(a => a.station_id === selectedFarmer.station_id)
    : null

  return (
    <div className="space-y-4">
      <div className="section-header">Farmer Profiles & Government Services</div>
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
              background: '#fff', border: '1px solid #e8e5e1', borderRadius: '8px', padding: '16px',
            }}>
              <div style={{ fontWeight: 700, fontSize: '1.1rem', color: '#1b1e2d' }}>
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
              <DPICard title={REGION.farmerServices.pmkisan}>
                Installments received: {detail.pmkisan.installments_received}<br />
                Total amount: {REGION.currency} {detail.pmkisan.total_amount.toLocaleString(REGION.locale)}
              </DPICard>
            )}

            {detail.pmfby && (
              <DPICard title={REGION.farmerServices.pmfby}>
                Status: {detail.pmfby.status}<br />
                Sum insured: {REGION.currency} {detail.pmfby.sum_insured.toLocaleString(REGION.locale)}<br />
                Premium paid: {REGION.currency} {detail.pmfby.premium_paid.toLocaleString(REGION.locale)}
              </DPICard>
            )}

            {detail.kcc && (
              <DPICard title={REGION.farmerServices.kcc}>
                Credit limit: {REGION.currency} {detail.kcc.credit_limit.toLocaleString(REGION.locale)}<br />
                Outstanding: {REGION.currency} {detail.kcc.outstanding.toLocaleString(REGION.locale)}<br />
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
            background: '#fff', border: '1px solid #e8e5e1',
            borderLeft: `3px solid ${CONDITION_COLOR[stationAlert.condition || ''] || '#888'}`,
            borderRadius: '8px', padding: '14px',
          }}>
            {stationAlert.condition && (
              <span style={{
                background: CONDITION_COLOR[stationAlert.condition] || '#888',
                color: '#fff', padding: '2px 8px', borderRadius: '10px',
                fontSize: '0.7rem', fontWeight: 600,
              }}>
                {CONDITION_LABEL[stationAlert.condition] ?? stationAlert.condition.replace(/_/g, ' ')}
              </span>
            )}
            <span style={{ color: '#888', fontSize: '0.75rem', marginLeft: '8px' }}>
              {PROVIDER_LABEL[stationAlert.provider || 'rag'] ?? (stationAlert.provider || 'rag')} {'\u00B7'} {LANG_LABEL[stationAlert.language || 'en'] ?? (stationAlert.language || 'en')}
            </span>
            <div style={{ color: '#555', fontSize: '0.85rem', lineHeight: 1.5, marginTop: '8px', maxWidth: '100%', overflowWrap: 'break-word', wordBreak: 'break-word' }}>
              {(stationAlert.advisory_local || stationAlert.advisory_en || '').slice(0, 300)}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
