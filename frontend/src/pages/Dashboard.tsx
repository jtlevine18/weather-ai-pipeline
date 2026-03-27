import { Link } from 'react-router-dom'
import { ChevronRight } from 'lucide-react'
import { MetricCard } from '../components/MetricCard'
import { DashboardSkeleton } from '../components/LoadingSpinner'
import { WelcomeBanner } from '../components/PageContext'
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

const STATUS_COLOR: Record<string, string> = {
  ok: '#2a9d8f',
  partial: '#f4a261',
  failed: '#e63946',
  running: '#1976D2',
  success: '#2a9d8f',
  completed: '#2a9d8f',
  error: '#e63946',
}

interface StageCard {
  key: string
  title: string
  href: string
  icon: string
  color: string
  desc: string
}

const STAGES: StageCard[] = [
  {
    key: 'data',
    title: 'Data',
    href: '/stations',
    icon: '\u{1F4E1}',
    color: '#2E7D32',
    desc: 'Weather readings from 20 stations across Kerala and Tamil Nadu, automatically cleaned and quality-checked',
  },
  {
    key: 'forecasts',
    title: 'Forecasts',
    href: '/forecasts',
    icon: '\u{1F326}\uFE0F',
    color: '#1565C0',
    desc: '7-day forecasts corrected with machine learning, personalized to each farmer\u2019s location and elevation',
  },
  {
    key: 'advisories',
    title: 'Advisories',
    href: '/advisories',
    icon: '\u{1F33E}',
    color: '#d4a019',
    desc: 'Crop-specific farming advice in Tamil and Malayalam, generated daily and delivered by SMS',
  },
]

export default function Dashboard() {
  const stations = useStations()
  const forecasts = useForecasts(500)
  const alerts = useAlerts(200)
  const runs = usePipelineRuns(10)
  const pipelineStats = usePipelineStats()
  const sources = useSources()
  const deliveries = useDeliveryLog(200)
  const clean = useTelemetryClean(200)

  const isLoading = stations.isLoading && forecasts.isLoading && pipelineStats.isLoading
  if (isLoading) return <DashboardSkeleton />

  const stationCount = stations.data?.length ?? 0
  const forecastCount = forecasts.data?.length ?? 0
  const alertCount = alerts.data?.length ?? 0
  const deliveryCount = deliveries.data?.length ?? 0
  const runList = runs.data ?? []
  const okRuns = runList.filter(r => r.status === 'ok' || r.status === 'success' || r.status === 'completed').length

  // Avg quality from clean telemetry
  const cleanData = clean.data ?? []
  const avgQuality = cleanData.length > 0
    ? cleanData.reduce((sum, r) => sum + (r.quality_score ?? 0), 0) / cleanData.length
    : 0

  // MOS count
  const mosCount = (forecasts.data ?? []).filter(f =>
    (f.model ?? '').includes('mos')
  ).length
  const mosPct = forecastCount > 0 ? Math.round(100 * mosCount / forecastCount) : 0

  // Source labels
  const srcData = sources.data ?? []
  const srcLabel = srcData.length > 0
    ? srcData.map(s => s.name || s.type || 'Unknown').join(', ')
    : '\u2014'

  // Build stats per stage card
  function stageStats(stage: StageCard): [string, string][] {
    switch (stage.key) {
      case 'data':
        return [
          ['Stations', String(stationCount)],
          ['Data Sources', srcLabel],
          ['Avg Quality', avgQuality > 0 ? `${Math.round(avgQuality * 100)}%` : '\u2014'],
        ]
      case 'forecasts':
        return [
          ['Forecasts', String(forecastCount)],
          ['ML Model Used', forecastCount > 0 ? `${mosPct}%` : '\u2014'],
        ]
      case 'advisories':
        return [
          ['Advisories', String(alertCount)],
          ['Delivered', String(deliveryCount)],
        ]
      default:
        return []
    }
  }

  return (
    <div className="space-y-6">
      {/* Welcome banner for first-time visitors */}
      <div style={{ paddingTop: '20px' }}>
        <WelcomeBanner />
      </div>

      {/* Hero */}
      <div>
        <h1 style={{
          margin: 0,
          fontWeight: 700,
          color: '#1a1a1a',
          fontFamily: 'DM Sans, sans-serif',
          letterSpacing: '-0.5px',
          lineHeight: 1.25,
          fontSize: '1.65rem',
        }}>
          AI Weather Forecasts &amp; Farming Advisories<br />
          <span style={{ color: '#999', fontWeight: 400 }}>
            for Smallholder Farmers in Southern India
          </span>
        </h1>
        <p style={{
          color: '#999',
          lineHeight: 1.6,
          margin: '6px 0 0',
          fontFamily: 'DM Sans, sans-serif',
          fontSize: '0.86rem',
        }}>
          This system collects real weather data from 20 IMD stations across Kerala and Tamil Nadu,
          generates machine-learning-corrected forecasts personalized to each farmer's GPS location,
          and delivers crop-specific advisories in Tamil and Malayalam via SMS.
        </p>
      </div>

      {/* 3 Stage Cards with arrows */}
      <div className="flex items-stretch gap-0" style={{ maxWidth: '100%' }}>
        {STAGES.map((stage, idx) => (
          <div key={stage.key} className="contents">
            <Link
              to={stage.href}
              className="flex-1 flex flex-col relative overflow-hidden no-underline"
              style={{
                background: '#fff',
                border: '1px solid #e0dcd5',
                borderRadius: '14px',
                padding: '22px 20px 16px',
                textDecoration: 'none',
                color: 'inherit',
                fontFamily: 'DM Sans, sans-serif',
                transition: 'all 0.25s cubic-bezier(0.25, 0.46, 0.45, 0.94)',
              }}
              onMouseEnter={e => {
                const el = e.currentTarget as HTMLElement
                el.style.borderColor = '#ccc8c0'
                el.style.boxShadow = '0 8px 28px rgba(0,0,0,0.06), 0 2px 8px rgba(0,0,0,0.03)'
                el.style.transform = 'translateY(-3px)'
              }}
              onMouseLeave={e => {
                const el = e.currentTarget as HTMLElement
                el.style.borderColor = '#e0dcd5'
                el.style.boxShadow = 'none'
                el.style.transform = 'translateY(0)'
              }}
            >
              {/* Top color border */}
              <div style={{
                position: 'absolute', top: 0, left: 0, right: 0, height: '3px',
                background: stage.color, borderRadius: '14px 14px 0 0',
              }} />

              {/* Icon + title */}
              <div className="flex items-center gap-2.5" style={{ marginBottom: '10px' }}>
                <div style={{
                  width: '38px', height: '38px', borderRadius: '10px',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: '1.1rem', background: `${stage.color}12`, flexShrink: 0,
                }}>
                  {stage.icon}
                </div>
                <div style={{
                  fontFamily: 'DM Sans, sans-serif', fontWeight: 600,
                  fontSize: '1.1rem', color: '#1a1a1a',
                }}>
                  {stage.title}
                </div>
              </div>

              {/* Description */}
              <div style={{
                color: '#888', fontSize: '0.78rem', lineHeight: 1.55,
                marginBottom: '14px', flex: 1,
              }}>
                {stage.desc}
              </div>

              {/* Stats */}
              <div style={{ borderTop: '1px solid #f0ede8', paddingTop: '10px' }}>
                {stageStats(stage).map(([label, val]) => (
                  <div key={label} className="flex justify-between" style={{ padding: '3px 0' }}>
                    <span style={{ color: '#999', fontSize: '0.76rem' }}>{label}</span>
                    <span style={{ color: '#1a1a1a', fontSize: '0.76rem', fontWeight: 600 }}>{val}</span>
                  </div>
                ))}
              </div>
            </Link>

            {/* Arrow between cards */}
            {idx < 2 && (
              <div className="flex items-center px-1.5">
                <ChevronRight size={20} color="#c8c0b4" strokeWidth={1.5} />
              </div>
            )}
          </div>
        ))}
      </div>

      {/* 4 Metric Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <MetricCard label="Pipeline Runs" value={`${okRuns}/${runList.length}`} />
        <MetricCard label="Avg Quality" value={avgQuality > 0 ? `${Math.round(avgQuality * 100)}%` : '0%'} />
        <MetricCard label="Advisories" value={alertCount} />
        <MetricCard label="Deliveries" value={deliveryCount} />
      </div>

      {/* Run History */}
      {runList.length > 0 && (
        <details className="group">
          <summary className="cursor-pointer text-sm font-medium text-warm-body hover:text-[#1a1a1a] select-none py-2">
            Run history
          </summary>
          <div style={{
            border: '1px solid #e0dcd5', borderRadius: '10px',
            overflow: 'hidden', background: '#fff', marginTop: '8px',
          }}>
            {runList.slice(0, 8).map((run, i) => {
              const s = run.status || '?'
              const runId = (run.run_id || run.id?.toString() || '').slice(0, 8)
              const started = (run.started_at || '').slice(0, 16)
              const color = STATUS_COLOR[s] || '#888'
              return (
                <div
                  key={run.id ?? i}
                  style={{
                    display: 'flex', alignItems: 'center', padding: '8px 14px',
                    borderBottom: i < Math.min(runList.length, 8) - 1 ? '1px solid #f0ede8' : 'none',
                    gap: '12px', fontSize: '0.8rem', fontFamily: 'DM Sans, sans-serif',
                  }}
                >
                  <span style={{
                    background: color, color: '#fff', padding: '2px 10px',
                    borderRadius: '5px', fontSize: '0.68rem', fontWeight: 700,
                    minWidth: '50px', textAlign: 'center',
                  }}>
                    {s}
                  </span>
                  <span style={{ color: '#aaa', fontFamily: 'monospace', fontSize: '0.75rem' }}>
                    {runId}
                  </span>
                  <span style={{ color: '#888' }}>{started}</span>
                  <span style={{ color: '#444', flex: 1 }}>
                    {run.error_detail?.slice(0, 80) || `${run.stations_processed ?? 0} stations, ${run.records_ingested ?? 0} records`}
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
