import { useState, useMemo } from 'react'
import {
  ChevronRight,
  Database,
  Shield,
  CloudSun,
  MapPin,
  Languages,
  Send,
} from 'lucide-react'
import { MetricCard } from '../components/MetricCard'
import { ForecastStrip } from '../components/ForecastStrip'
import { PageLoader } from '../components/LoadingSpinner'
import {
  useStations,
  useForecasts,
  useAlerts,
  usePipelineRuns,
  usePipelineStats,
  useSources,
  useDeliveryLog,
  useTelemetryClean,
} from '../api/hooks'

/* ── constants ─────────────────────────────────────────── */

const STATUS_COLOR: Record<string, string> = {
  ok: '#2a9d8f',
  partial: '#f4a261',
  failed: '#e63946',
  running: '#1976D2',
  success: '#2a9d8f',
  completed: '#2a9d8f',
  error: '#e63946',
}

interface PipelineStep {
  icon: typeof Database
  name: string
  desc: string
}

const PIPELINE_STEPS: PipelineStep[] = [
  { icon: Database, name: 'Ingest', desc: 'Scrape real weather data from India Met Dept' },
  { icon: Shield, name: 'Heal', desc: 'AI agent detects and fixes anomalies' },
  { icon: CloudSun, name: 'Forecast', desc: 'NeuralGCM + XGBoost 7-day predictions' },
  { icon: MapPin, name: 'Downscale', desc: 'NASA satellite data \u2192 farmer GPS' },
  { icon: Languages, name: 'Translate', desc: 'RAG + Claude bilingual advisories' },
  { icon: Send, name: 'Deliver', desc: 'SMS to farmers in Tamil & Malayalam' },
]

interface TechItem {
  name: string
  role: string
}

const TECH_STACK: TechItem[] = [
  { name: 'NeuralGCM', role: 'Google DeepMind neural weather model' },
  { name: 'XGBoost', role: 'ML bias correction' },
  { name: 'Claude', role: 'Advisory generation + translation' },
  { name: 'FAISS', role: 'Vector search for RAG' },
  { name: 'PostgreSQL', role: 'Production database' },
  { name: 'NASA POWER', role: 'Satellite downscaling data' },
  { name: 'IMD', role: 'India Met Dept station data' },
  { name: 'Open-Meteo', role: 'NWP forecast fallback' },
]

/* ── helpers ───────────────────────────────────────────── */

function formatDate(iso: string | undefined): string {
  if (!iso) return '--'
  try {
    return new Date(iso).toLocaleDateString('en-IN', {
      day: 'numeric',
      month: 'short',
      year: 'numeric',
    })
  } catch {
    return iso.slice(0, 10)
  }
}

function daysSince(iso: string | undefined): number {
  if (!iso) return 999
  try {
    return Math.floor((Date.now() - new Date(iso).getTime()) / 86_400_000)
  } catch {
    return 999
  }
}

/* ── component ─────────────────────────────────────────── */

export default function Dashboard() {
  const stations = useStations()
  const forecasts = useForecasts(500)
  const alerts = useAlerts(200)
  const runs = usePipelineRuns(10)
  const pipelineStats = usePipelineStats()
  const sources = useSources()
  const deliveries = useDeliveryLog(200)
  const clean = useTelemetryClean(200)

  const [selectedStation, setSelectedStation] = useState('')

  const isLoading = stations.isLoading && forecasts.isLoading && pipelineStats.isLoading
  if (isLoading) return <PageLoader label="Loading dashboard..." />

  const stationList = stations.data ?? []
  const forecastList = forecasts.data ?? []
  const alertList = alerts.data ?? []
  const runList = runs.data ?? []
  const deliveryCount = deliveries.data?.length ?? 0
  const okRuns = runList.filter(
    (r) => r.status === 'ok' || r.status === 'success' || r.status === 'completed',
  ).length

  // Avg quality from clean telemetry
  const cleanData = clean.data ?? []
  const avgQuality =
    cleanData.length > 0
      ? cleanData.reduce((sum, r) => sum + (r.quality_score ?? 0), 0) / cleanData.length
      : 0

  // Last pipeline run
  const lastRun = runList.length > 0 ? runList[0] : undefined
  const lastRunDate = lastRun?.started_at
  const daysAgo = daysSince(lastRunDate)
  const isRecent = daysAgo < 7

  // Filtered forecasts/alerts for selected station
  const stationForecasts = useMemo(() => {
    if (!selectedStation) return []
    return forecastList
      .filter((f) => f.station_id === selectedStation)
      .sort((a, b) => (a.forecast_day ?? 0) - (b.forecast_day ?? 0))
      .slice(0, 7)
  }, [selectedStation, forecastList])

  const stationAlert = useMemo(() => {
    if (!selectedStation) return null
    return alertList.find((a) => a.station_id === selectedStation) ?? null
  }, [selectedStation, alertList])

  return (
    <div className="space-y-8">
      {/* ── Hero ────────────────────────────────────────── */}
      <div style={{ padding: '28px 0 0' }}>
        <h1
          style={{
            margin: 0,
            fontWeight: 700,
            color: '#1a1a1a',
            fontFamily: '"Source Serif 4", Georgia, serif',
            letterSpacing: '-0.5px',
            lineHeight: 1.25,
            fontSize: '1.65rem',
          }}
        >
          AI Weather Pipeline for Southern India
        </h1>
        <p
          style={{
            color: '#888',
            lineHeight: 1.6,
            margin: '6px 0 0',
            fontFamily: '"DM Sans", sans-serif',
            fontSize: '0.86rem',
          }}
        >
          ML-powered 7-day forecasts and farming advisories for 20 stations across Kerala &amp;
          Tamil Nadu
        </p>
      </div>

      {/* ── Live Status Badge ──────────────────────────── */}
      <div
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: '10px',
          background: '#fff',
          border: '1px solid #e0dcd5',
          borderRadius: '10px',
          padding: '8px 16px',
          fontFamily: '"DM Sans", sans-serif',
          fontSize: '0.8rem',
        }}
      >
        <span
          style={{
            width: 8,
            height: 8,
            borderRadius: '50%',
            background: isRecent ? '#2a9d8f' : '#d4a019',
            display: 'inline-block',
            flexShrink: 0,
          }}
        />
        <span style={{ color: '#555' }}>
          Last run: <strong style={{ color: '#1a1a1a' }}>{formatDate(lastRunDate)}</strong>
        </span>
        <span style={{ color: '#ccc' }}>|</span>
        <span style={{ color: '#555' }}>
          Next: <strong style={{ color: '#1a1a1a' }}>Monday 6:00 AM IST</strong>
        </span>
      </div>

      {/* ── Pipeline Visualization ─────────────────────── */}
      <div>
        <div
          style={{
            fontFamily: '"DM Sans", sans-serif',
            fontSize: '0.72rem',
            fontWeight: 600,
            textTransform: 'uppercase',
            letterSpacing: '1.5px',
            color: '#888',
            paddingBottom: '8px',
            marginBottom: '16px',
            borderBottom: '2px solid #d4a019',
          }}
        >
          Pipeline
        </div>

        <div
          style={{
            display: 'flex',
            alignItems: 'stretch',
            gap: 0,
            overflowX: 'auto',
            paddingBottom: '4px',
          }}
        >
          {PIPELINE_STEPS.map((step, idx) => {
            const Icon = step.icon
            return (
              <div key={step.name} style={{ display: 'contents' }}>
                <div
                  style={{
                    background: '#fff',
                    border: '1px solid #e0dcd5',
                    borderRadius: '14px',
                    padding: '16px 14px',
                    fontFamily: '"DM Sans", sans-serif',
                    minWidth: '120px',
                    flex: '1 1 0',
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'center',
                    textAlign: 'center',
                    gap: '8px',
                    transition: 'all 0.25s cubic-bezier(0.25, 0.46, 0.45, 0.94)',
                    cursor: 'default',
                  }}
                  onMouseEnter={(e) => {
                    const el = e.currentTarget
                    el.style.borderColor = '#ccc8c0'
                    el.style.boxShadow =
                      '0 8px 28px rgba(0,0,0,0.06), 0 2px 8px rgba(0,0,0,0.03)'
                    el.style.transform = 'translateY(-3px)'
                  }}
                  onMouseLeave={(e) => {
                    const el = e.currentTarget
                    el.style.borderColor = '#e0dcd5'
                    el.style.boxShadow = 'none'
                    el.style.transform = 'translateY(0)'
                  }}
                >
                  <div
                    style={{
                      width: 36,
                      height: 36,
                      borderRadius: '10px',
                      background: 'rgba(212, 160, 25, 0.10)',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                    }}
                  >
                    <Icon size={18} color="#d4a019" strokeWidth={1.8} />
                  </div>
                  <div style={{ fontWeight: 600, fontSize: '0.85rem', color: '#1a1a1a' }}>
                    {step.name}
                  </div>
                  <div style={{ color: '#888', fontSize: '0.72rem', lineHeight: 1.45 }}>
                    {step.desc}
                  </div>
                </div>

                {idx < PIPELINE_STEPS.length - 1 && (
                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      padding: '0 2px',
                      flexShrink: 0,
                    }}
                  >
                    <ChevronRight size={18} color="#c8c0b4" strokeWidth={1.5} />
                  </div>
                )}
              </div>
            )
          })}
        </div>
      </div>

      {/* ── Try It ─────────────────────────────────────── */}
      <div>
        <div
          style={{
            fontFamily: '"DM Sans", sans-serif',
            fontSize: '0.72rem',
            fontWeight: 600,
            textTransform: 'uppercase',
            letterSpacing: '1.5px',
            color: '#888',
            paddingBottom: '8px',
            marginBottom: '16px',
            borderBottom: '2px solid #d4a019',
          }}
        >
          Try It
        </div>

        <div
          style={{
            background: '#fff',
            border: '1px solid #e0dcd5',
            borderRadius: '14px',
            padding: '20px',
          }}
        >
          <label
            style={{
              display: 'block',
              fontFamily: '"DM Sans", sans-serif',
              fontSize: '0.8rem',
              fontWeight: 500,
              color: '#555',
              marginBottom: '8px',
            }}
          >
            Select a station to see the latest forecast and advisory
          </label>
          <select
            value={selectedStation}
            onChange={(e) => setSelectedStation(e.target.value)}
            className="input"
            style={{ maxWidth: '360px' }}
          >
            <option value="">Choose a station...</option>
            {stationList.map((s) => (
              <option key={s.station_id} value={s.station_id}>
                {s.name} ({s.state})
              </option>
            ))}
          </select>

          {selectedStation && (
            <div style={{ marginTop: '20px' }} className="space-y-4">
              {/* Forecast strip */}
              {stationForecasts.length > 0 ? (
                <div>
                  <div
                    style={{
                      fontFamily: '"DM Sans", sans-serif',
                      fontSize: '0.75rem',
                      fontWeight: 600,
                      color: '#999',
                      textTransform: 'uppercase',
                      letterSpacing: '1px',
                      marginBottom: '8px',
                    }}
                  >
                    7-Day Forecast
                  </div>
                  <ForecastStrip forecasts={stationForecasts} />
                </div>
              ) : (
                <p
                  style={{
                    fontFamily: '"DM Sans", sans-serif',
                    fontSize: '0.82rem',
                    color: '#999',
                  }}
                >
                  No forecast data for this station yet.
                </p>
              )}

              {/* Advisory */}
              {stationAlert && (
                <div>
                  <div
                    style={{
                      fontFamily: '"DM Sans", sans-serif',
                      fontSize: '0.75rem',
                      fontWeight: 600,
                      color: '#999',
                      textTransform: 'uppercase',
                      letterSpacing: '1px',
                      marginBottom: '8px',
                    }}
                  >
                    Latest Advisory
                  </div>
                  <div
                    style={{
                      background: '#faf8f5',
                      border: '1px solid #e0dcd5',
                      borderRadius: '10px',
                      padding: '14px 16px',
                    }}
                  >
                    {stationAlert.advisory_local && (
                      <p
                        style={{
                          fontFamily: '"DM Sans", sans-serif',
                          fontSize: '0.82rem',
                          color: '#555',
                          lineHeight: 1.6,
                          margin: 0,
                        }}
                      >
                        {stationAlert.advisory_local}
                      </p>
                    )}
                    {stationAlert.advisory_en && (
                      <p
                        style={{
                          fontFamily: '"DM Sans", sans-serif',
                          fontSize: '0.78rem',
                          color: '#999',
                          lineHeight: 1.6,
                          margin: stationAlert.advisory_local ? '10px 0 0' : 0,
                          fontStyle: 'italic',
                        }}
                      >
                        {stationAlert.advisory_en}
                      </p>
                    )}
                    {stationAlert.language && (
                      <span
                        className="badge-slate"
                        style={{ marginTop: '8px', display: 'inline-block' }}
                      >
                        {stationAlert.language}
                      </span>
                    )}
                  </div>
                </div>
              )}
              {!stationAlert && (
                <p
                  style={{
                    fontFamily: '"DM Sans", sans-serif',
                    fontSize: '0.82rem',
                    color: '#999',
                  }}
                >
                  No advisory for this station yet.
                </p>
              )}
            </div>
          )}
        </div>
      </div>

      {/* ── Metric Cards ───────────────────────────────── */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <MetricCard label="Pipeline Runs" value={`${okRuns}/${runList.length}`} />
        <MetricCard
          label="Avg Quality"
          value={avgQuality > 0 ? `${Math.round(avgQuality * 100)}%` : '0%'}
        />
        <MetricCard label="Advisories" value={alertList.length} />
        <MetricCard label="Deliveries" value={deliveryCount} />
      </div>

      {/* ── Tech Stack Grid ────────────────────────────── */}
      <div>
        <div
          style={{
            fontFamily: '"DM Sans", sans-serif',
            fontSize: '0.72rem',
            fontWeight: 600,
            textTransform: 'uppercase',
            letterSpacing: '1.5px',
            color: '#888',
            paddingBottom: '8px',
            marginBottom: '16px',
            borderBottom: '2px solid #d4a019',
          }}
        >
          Tech Stack
        </div>

        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))',
            gap: '12px',
          }}
        >
          {TECH_STACK.map((tech) => (
            <div
              key={tech.name}
              style={{
                background: '#fff',
                border: '1px solid #e0dcd5',
                borderRadius: '10px',
                padding: '14px 16px',
                fontFamily: '"DM Sans", sans-serif',
              }}
            >
              <div style={{ fontWeight: 600, fontSize: '0.88rem', color: '#1a1a1a' }}>
                {tech.name}
              </div>
              <div style={{ color: '#888', fontSize: '0.75rem', lineHeight: 1.45, marginTop: 4 }}>
                {tech.role}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* ── Run History ────────────────────────────────── */}
      {runList.length > 0 && (
        <details className="group">
          <summary className="cursor-pointer text-sm font-medium text-warm-body hover:text-[#1a1a1a] select-none py-2">
            Run history
          </summary>
          <div
            style={{
              border: '1px solid #e0dcd5',
              borderRadius: '10px',
              overflow: 'hidden',
              background: '#fff',
              marginTop: '8px',
            }}
          >
            {runList.slice(0, 8).map((run, i) => {
              const s = run.status || '?'
              const runId = (run.run_id || run.id?.toString() || '').slice(0, 8)
              const started = (run.started_at || '').slice(0, 16)
              const color = STATUS_COLOR[s] || '#888'
              return (
                <div
                  key={run.id ?? i}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    padding: '8px 14px',
                    borderBottom:
                      i < Math.min(runList.length, 8) - 1 ? '1px solid #f0ede8' : 'none',
                    gap: '12px',
                    fontSize: '0.8rem',
                    fontFamily: '"DM Sans", sans-serif',
                  }}
                >
                  <span
                    style={{
                      background: color,
                      color: '#fff',
                      padding: '2px 10px',
                      borderRadius: '5px',
                      fontSize: '0.68rem',
                      fontWeight: 700,
                      minWidth: '50px',
                      textAlign: 'center',
                    }}
                  >
                    {s}
                  </span>
                  <span
                    style={{ color: '#aaa', fontFamily: 'monospace', fontSize: '0.75rem' }}
                  >
                    {runId}
                  </span>
                  <span style={{ color: '#888' }}>{started}</span>
                  <span style={{ color: '#444', flex: 1 }}>
                    {run.error_detail?.slice(0, 80) ||
                      `${run.stations_processed ?? 0} stations, ${run.records_ingested ?? 0} records`}
                  </span>
                </div>
              )
            })}
          </div>
        </details>
      )}
    </div>
  )
}
