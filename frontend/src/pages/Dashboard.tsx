import { Link } from 'react-router-dom'
import { ChevronRight } from 'lucide-react'
import { MetricCard } from '../components/MetricCard'
import { DashboardSkeleton } from '../components/LoadingSpinner'
import { WelcomeBanner } from '../components/PageContext'
import { REGION } from '../regionConfig'
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
    desc: `Weather readings from stations across ${REGION.states.join(' and ')}, automatically cleaned and quality-checked`,
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
    desc: `Crop-specific farming advice in ${REGION.languageList}, generated weekly and delivered via SMS`,
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
    (f.model_used || f.model || '').includes('mos')
  ).length
  const mosPct = forecastCount > 0 ? Math.round(100 * mosCount / forecastCount) : 0

  // Source labels
  const srcData = sources.data ?? []
  const srcLabel = srcData.length > 0
    ? srcData.map(s => s.name || s.type || 'Unknown').join(', ')
    : '\u2014'

  // NWP source from forecasts
  const nwpModel = (forecasts.data ?? []).find(f => (f.model_used || f.model || '').includes('neuralgcm'))
    ? 'NeuralGCM' : (forecastCount > 0 ? 'Open-Meteo' : '\u2014')

  // Last run info
  const lastRun = runList[0]
  const lastRunLabel = lastRun?.started_at
    ? new Date(lastRun.started_at).toLocaleDateString(REGION.locale, { weekday: 'short', month: 'short', day: 'numeric' })
    : '\u2014'

  // Build stats per stage card
  function stageStats(stage: StageCard): [string, string][] {
    switch (stage.key) {
      case 'data':
        return [
          ['Stations', `${stationCount} (${REGION.states.join(' + ')})`],
          ['Avg Quality', avgQuality > 0 ? `${Math.round(avgQuality * 100)}%` : '\u2014'],
          ['Last Run', lastRunLabel],
        ]
      case 'forecasts':
        return [
          ['Weather Model', nwpModel],
          ['Forecast Days', forecastCount > 0 ? `${Math.round(forecastCount / Math.max(stationCount, 1))} per station` : '\u2014'],
          ['Avg Confidence', forecastCount > 0 ? `${Math.round((forecasts.data ?? []).reduce((s, f) => s + (f.confidence ?? 0), 0) / forecastCount * 100)}%` : '\u2014'],
        ]
      case 'advisories':
        return [
          ['Languages', alertCount > 0 ? REGION.languageMetric : '\u2014'],
          ['Advisories', `${alertCount} (${deliveryCount} delivered)`],
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
      <div data-tour="hero">
        <h1 className="font-sans font-bold text-[#1a1a1a] text-[1.65rem] leading-tight tracking-tight m-0">
          AI Weather Forecasts &amp; Farming Advisories<br />
          <span className="text-warm-muted font-normal">
            for Smallholder Farmers in {REGION.name}
          </span>
        </h1>
        <p className="text-warm-muted-light text-[0.86rem] leading-relaxed mt-1.5 font-sans">
          This system collects real weather data from {REGION.dataSource} stations across {REGION.states.join(' and ')},
          generates machine-learning-corrected forecasts personalized to each farmer's GPS location,
          and generates crop-specific advisories in {REGION.languageList} with simulated SMS delivery.
        </p>
      </div>

      {/* 3 Stage Cards with arrows */}
      <div data-tour="stage-cards" className="flex items-stretch gap-0 animate-stagger" style={{ maxWidth: '100%' }}>
        {STAGES.map((stage, idx) => (
          <div key={stage.key} className="contents">
            <Link
              to={stage.href}
              className="flex-1 flex flex-col stage-card no-underline"
            >
              {/* Top color border */}
              <div
                className="absolute top-0 left-0 right-0 h-[3px] rounded-t-[14px]"
                style={{ background: stage.color }}
              />

              {/* Icon + title */}
              <div className="flex items-center gap-2.5 mb-2.5">
                <div
                  className="w-[38px] h-[38px] rounded-[10px] flex items-center justify-center text-lg shrink-0"
                  style={{ background: `${stage.color}12` }}
                >
                  {stage.icon}
                </div>
                <div className="font-sans font-semibold text-lg text-[#1a1a1a]">
                  {stage.title}
                </div>
              </div>

              {/* Description */}
              <div className="text-warm-muted text-[0.78rem] leading-relaxed mb-3.5 flex-1">
                {stage.desc}
              </div>

              {/* Stats */}
              <div className="border-t border-warm-border/50 pt-2.5">
                {stageStats(stage).map(([label, val]) => (
                  <div key={label} className="flex justify-between py-0.5">
                    <span className="text-warm-muted-light text-[0.76rem]">{label}</span>
                    <span className="text-[#1a1a1a] text-[0.76rem] font-semibold">{val}</span>
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
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 animate-stagger">
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
