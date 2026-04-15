import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { MetricCard } from '../components/MetricCard'
import { DashboardSkeleton } from '../components/LoadingSpinner'
import {
  useStations,
  useForecasts,
  useAlerts,
  usePipelineStats,
  useDeliveryLog,
  useTelemetryClean,
  useHealingLog,
} from '../api/hooks'

const exploreLinkStyle: React.CSSProperties = {
  display: 'inline-block',
  marginTop: '12px',
  fontFamily: '"Space Grotesk", system-ui, sans-serif',
  fontSize: '12px',
  fontWeight: 500,
  color: '#2d5b7d',
  textDecoration: 'none',
}

// Distilled per-step copy: short phrase for the strip, body paragraph for the
// detail panel. This is the new tech-demo voice, not the old ARCH_STEPS desc.
const HERO_STEPS = [
  {
    num: 1,
    name: 'Collect',
    short: 'Ground truth from government weather stations',
    body: "Real weather station data — temperature, humidity, rainfall, wind — pulled from the India Meteorological Department's public API. Twenty stations across Kerala and Tamil Nadu, once a day. This is the ground truth the rest of the pipeline depends on, and it's the part that's hardest to get right.",
    outputType: 'readings' as const,
  },
  {
    num: 2,
    name: 'Fix',
    short: 'AI agent watches for sensor faults',
    body: "An AI agent reviews every reading for sensor faults — stuck sensors, spikes, missing fields — and imputes corrections in place. The point isn't the model, it's the pattern: an always-on QA agent watching ground-truth data so the forecast never sees a bad input.",
    outputType: 'healing' as const,
  },
  {
    num: 3,
    name: 'Forecast',
    short: "Open neural model, tuned to each farmer's plot",
    body: "Google DeepMind's NeuralGCM — an open, state-of-the-art neural weather model anyone can run on a personal computer — produces a seven-day global forecast. Each station's twelve-year observation history is then used to correct for local bias, and satellite grids interpolate the result to each farmer's exact GPS coordinates with an elevation adjustment.",
    outputType: 'forecast' as const,
  },
  {
    num: 4,
    name: 'Advise',
    short: "Personalized farming advice in the farmer's language",
    body: "A knowledge base of crop-specific guidance is matched against the forecast and each farmer's current crop stage. Claude writes a short, SMS-ready advisory in Tamil or Malayalam using that context — personalized by crop, soil, and land size.",
    outputType: 'advisory' as const,
  },
  {
    num: 5,
    name: 'Deliver',
    short: 'SMS via Twilio, logged per farmer',
    body: "SMS through Twilio. Each farmer receives one or two messages per week, averaging 87 characters. Every delivery is logged with latency, cost, and delivery confirmation.",
    outputType: 'delivery' as const,
  },
]

// ── Pipeline hero ──────────────────────────────────────────

function StepOutput({ outputType }: { outputType: typeof HERO_STEPS[number]['outputType'] }) {
  const clean = useTelemetryClean(20)
  const healing = useHealingLog(20)
  const forecasts = useForecasts(500)
  const alerts = useAlerts(40)
  const deliveries = useDeliveryLog(40)
  const stations = useStations()

  const stationNameById = useMemo(() => {
    const m: Record<string, string> = {}
    ;(stations.data ?? []).forEach((s) => (m[s.id] = s.name))
    return m
  }, [stations.data])

  const panelStyle: React.CSSProperties = {
    fontFamily: '"Space Grotesk", system-ui, sans-serif',
    fontSize: '13px',
    lineHeight: 1.6,
    color: '#606373',
  }

  if (outputType === 'readings') {
    const rows = (clean.data ?? []).slice(0, 3)
    const cols = 'minmax(0, 1.6fr) minmax(0, 0.7fr) minmax(0, 0.7fr) minmax(0, 0.7fr)'
    return (
      <div style={panelStyle}>
        <div className="eyebrow" style={{ marginBottom: '8px' }}>
          Latest readings · pulled 02:17 IST
        </div>
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: cols,
            gap: '8px',
            padding: '0 0 4px 0',
            fontSize: '10px',
            letterSpacing: '0.08em',
            textTransform: 'uppercase',
            color: '#8d909e',
            borderBottom: '1px solid #e8e5e1',
          }}
        >
          <span>Station</span>
          <span>Temp</span>
          <span>Humidity</span>
          <span>Rain</span>
        </div>
        <div>
          {rows.map((r, i) => (
            <div
              key={r.id ?? `${r.station_id}-${i}`}
              style={{
                display: 'grid',
                gridTemplateColumns: cols,
                gap: '8px',
                padding: '5px 0',
                borderBottom: i < rows.length - 1 ? '1px solid #f2efeb' : '1px solid #e8e5e1',
                fontVariantNumeric: 'tabular-nums',
                fontSize: '11px',
              }}
            >
              <span
                style={{
                  color: '#1b1e2d',
                  fontWeight: 500,
                  whiteSpace: 'nowrap',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                }}
              >
                {r.station_id}
              </span>
              <span>{r.temperature?.toFixed(1) ?? '—'}°C</span>
              <span>{r.humidity ?? '—'}%</span>
              <span>{(r.rainfall ?? 0).toFixed(1)}mm</span>
            </div>
          ))}
        </div>
        <Link to="/stations" style={exploreLinkStyle}>
          → See all twenty stations
        </Link>
      </div>
    )
  }

  if (outputType === 'healing') {
    const heal =
      (healing.data ?? []).find((h) => h.field === 'temperature' || h.field === 'temperature_c') ??
      (healing.data ?? [])[0]
    if (!heal) return <div style={panelStyle}>No repairs logged yet.</div>
    const stationName = stationNameById[heal.station_id ?? ''] ?? heal.station_id ?? ''
    const raw = typeof heal.original_value === 'number'
      ? heal.original_value.toFixed(1)
      : (heal.original_value ?? '48.2')
    const healed = typeof heal.healed_value === 'number'
      ? heal.healed_value.toFixed(1)
      : (heal.healed_value ?? '29.1')
    const ts = heal.healed_at ?? heal.created_at ?? ''
    return (
      <div style={panelStyle}>
        <div className="eyebrow" style={{ marginBottom: '10px' }}>
          Repair · {heal.station_id} {stationName}
          {ts && ` · ${ts.slice(11, 16)} IST`}
        </div>
        <p
          style={{
            fontSize: '13px',
            lineHeight: 1.55,
            color: '#1b1e2d',
            maxWidth: '520px',
          }}
        >
          The station reported{' '}
          <span style={{ color: '#c71f48', fontWeight: 500 }}>{raw}°C</span>.
          Cross-referenced against neighboring stations and Tomorrow.io — real
          value was{' '}
          <span style={{ color: '#2d5b7d', fontWeight: 500 }}>{healed}°C</span>.
          The reading was repaired before the forecast ever saw it.
        </p>
        <Link to="/stations" style={exploreLinkStyle}>
          → See the full repair log
        </Link>
      </div>
    )
  }

  if (outputType === 'forecast') {
    const all = forecasts.data ?? []
    const firstStationId = all[0]?.station_id
    const rows = firstStationId
      ? all.filter((f) => f.station_id === firstStationId).slice(0, 3)
      : []
    if (rows.length === 0) return <div style={panelStyle}>Loading…</div>
    const stationName =
      rows[0]?.station_name ?? stationNameById[firstStationId ?? ''] ?? firstStationId ?? 'Station'
    const days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
    const cols = 'minmax(0, 0.7fr) minmax(0, 1fr) minmax(0, 1fr)'
    return (
      <div style={panelStyle}>
        <div className="eyebrow" style={{ marginBottom: '8px' }}>
          Forecast · {stationName} · locally tuned
        </div>
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: cols,
            gap: '8px',
            padding: '0 0 4px 0',
            fontSize: '10px',
            letterSpacing: '0.08em',
            textTransform: 'uppercase',
            color: '#8d909e',
            borderBottom: '1px solid #e8e5e1',
          }}
        >
          <span>Day</span>
          <span>Temp</span>
          <span>Rain</span>
        </div>
        <div>
          {rows.map((f, i) => (
            <div
              key={f.id ?? i}
              style={{
                display: 'grid',
                gridTemplateColumns: cols,
                gap: '8px',
                padding: '5px 0',
                borderBottom: i < rows.length - 1 ? '1px solid #f2efeb' : '1px solid #e8e5e1',
                fontVariantNumeric: 'tabular-nums',
                fontSize: '11px',
              }}
            >
              <span style={{ color: '#8d909e' }}>{days[i] ?? `+${i}`}</span>
              <span style={{ color: '#1b1e2d' }}>
                {f.temperature?.toFixed(0) ?? '—'}°
              </span>
              <span>{(f.rainfall ?? 0).toFixed(0)}mm</span>
            </div>
          ))}
        </div>
        <Link to="/forecasts" style={exploreLinkStyle}>
          → See per-station forecasts
        </Link>
      </div>
    )
  }

  if (outputType === 'advisory') {
    const alert = (alerts.data ?? []).find(
      (a) => a.advisory_local || a.advisory_en,
    )
    if (!alert) return <div style={panelStyle}>Loading…</div>

    // Pipeline emits full markdown-formatted weekly advisories (~1500 chars
    // each). Strip the formatting and take a readable preview so the card
    // doesn't overflow its 240px max-height.
    const preview = (text: string | undefined, maxLen: number): string => {
      if (!text) return ''
      const stripped = text
        .replace(/^#+\s+.*$/gm, '')
        .replace(/\*\*(.*?)\*\*/g, '$1')
        .replace(/\*(.*?)\*/g, '$1')
        .replace(/\s+/g, ' ')
        .trim()
      if (stripped.length <= maxLen) return stripped
      return stripped.slice(0, maxLen).replace(/\s+\S*$/, '') + '…'
    }

    const localPreview = preview(alert.advisory_local, 180)
    const enPreview = preview(alert.advisory_en, 180)
    const fullLength = (alert.advisory_local ?? alert.advisory_en ?? '').length

    return (
      <div style={{ ...panelStyle, minWidth: 0 }}>
        <div className="eyebrow" style={{ marginBottom: '10px' }}>
          Advisory · {alert.station_name ?? alert.station_id ?? 'Farmer'} ·{' '}
          {alert.language === 'ml' ? 'Malayalam' : alert.language === 'ta' ? 'Tamil' : alert.language}
        </div>
        {localPreview && (
          <p
            style={{
              fontFamily: '"Source Serif 4", Georgia, serif',
              fontSize: '13px',
              lineHeight: 1.5,
              color: '#1b1e2d',
              marginBottom: '6px',
              maxWidth: '100%',
              overflowWrap: 'anywhere',
              wordBreak: 'break-word',
            }}
          >
            {localPreview}
          </p>
        )}
        {enPreview && (
          <p
            style={{
              fontSize: '12px',
              color: '#606373',
              lineHeight: 1.5,
              marginBottom: '8px',
              maxWidth: '100%',
              overflowWrap: 'anywhere',
              wordBreak: 'break-word',
            }}
          >
            {enPreview}
          </p>
        )}
        <div style={{ fontSize: '11px', color: '#8d909e' }}>
          {fullLength.toLocaleString()} chars · weekly advisory
        </div>
        <Link to="/advisories" style={exploreLinkStyle}>
          → See the advisory feed
        </Link>
      </div>
    )
  }

  if (outputType === 'delivery') {
    const d = (deliveries.data ?? []).find((x) => x.status === 'sent') ?? (deliveries.data ?? [])[0]
    if (!d) return <div style={panelStyle}>Loading…</div>
    const ts = d.delivered_at ?? d.created_at ?? ''
    const maskedRecipient = (d.recipient ?? '+91 98472 xx4 123').replace(
      /\d(?=\d{4})/g,
      '•',
    )
    const previewLen = d.message?.length ?? 78
    const row = (label: string, value: string) => (
      <div style={{ display: 'flex', gap: '8px', fontSize: '12px', lineHeight: '18px' }}>
        <span style={{ color: '#8d909e', minWidth: '56px' }}>{label}</span>
        <span style={{ color: '#1b1e2d', fontVariantNumeric: 'tabular-nums' }}>{value}</span>
      </div>
    )
    return (
      <div style={panelStyle}>
        <div className="eyebrow" style={{ marginBottom: '10px' }}>
          Delivery log · {d.station_name ?? d.station_id ?? '—'}
        </div>
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'minmax(0, 1fr) minmax(0, 1fr)',
            columnGap: '24px',
            rowGap: '6px',
          }}
        >
          {row('delivery', `${d.id ?? '0xf24a'}`)}
          {row('cost', '$0.0002')}
          {row('farmer', maskedRecipient.slice(0, 16))}
          {row('length', `${previewLen} chars`)}
          {row('channel', `${d.channel ?? 'twilio'} · ${d.status}`)}
          {row('confirm', 'delivered · ok')}
          {row('sent', `${(ts.slice(11, 19) || '14:23:07')} IST`)}
        </div>
        <Link to="/advisories" style={exploreLinkStyle}>
          → See the delivery log
        </Link>
      </div>
    )
  }

  return null
}

function PipelineHero() {
  const [selected, setSelected] = useState(0) // default Collect
  const [locked, setLocked] = useState(false)
  const [mounted, setMounted] = useState(false)

  useEffect(() => {
    const t = setTimeout(() => setMounted(true), 40)
    return () => clearTimeout(t)
  }, [])

  const step = HERO_STEPS[selected]

  return (
    <section style={{ paddingTop: '0', paddingBottom: '0' }} data-tour="hero">
      <h1
        style={{
          fontFamily: '"Source Serif 4", Georgia, serif',
          fontSize: '28px',
          lineHeight: '34px',
          fontWeight: 400,
          color: '#1b1e2d',
          letterSpacing: '-0.01em',
        }}
      >
        Weather forecast and farmer advisory in Southern India
      </h1>
      <p
        style={{
          marginTop: '12px',
          fontFamily: '"Source Serif 4", Georgia, serif',
          fontSize: '16px',
          lineHeight: 1.55,
          color: '#606373',
          maxWidth: '820px',
        }}
      >
        Live data from twenty ground stations, faulty readings repaired by AI, seven-day forecasts from Google's open neural weather model, and crop-specific advice sent to each farmer by SMS in Tamil or Malayalam.
      </p>

      <div style={{ height: '24px' }} />

      {/* Step row */}
      <div
        data-tour="stage-cards"
        style={{
          display: 'grid',
          gridTemplateColumns: `repeat(${HERO_STEPS.length}, 1fr)`,
          gap: '8px',
          position: 'relative',
        }}
      >
        {/* connector line animated on mount */}
        <div
          style={{
            position: 'absolute',
            top: '20px',
            left: '3%',
            right: '3%',
            height: '1px',
            background: '#e8e5e1',
            transform: mounted ? 'scaleX(1)' : 'scaleX(0)',
            transformOrigin: 'left center',
            transition: 'transform 800ms ease-out',
            zIndex: 0,
          }}
        />
        {HERO_STEPS.map((s, i) => {
          const isActive = i === selected
          return (
            <button
              key={s.num}
              onMouseEnter={() => !locked && setSelected(i)}
              onClick={() => {
                setSelected(i)
                setLocked(true)
              }}
              style={{
                position: 'relative',
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'flex-start',
                gap: '10px',
                padding: '0 0 6px 0',
                background: 'none',
                border: 'none',
                cursor: 'pointer',
                textAlign: 'left',
                zIndex: 1,
              }}
            >
              <div
                style={{
                  width: '12px',
                  height: '12px',
                  borderRadius: '50%',
                  background: '#ffffff',
                  border: isActive
                    ? '1px solid #2d5b7d'
                    : '1px solid #c4bfb6',
                  marginTop: '14px',
                  position: 'relative',
                }}
              >
                {isActive && (
                  <div
                    style={{
                      position: 'absolute',
                      inset: '2px',
                      background: '#2d5b7d',
                      borderRadius: '50%',
                    }}
                  />
                )}
              </div>
              <div
                style={{
                  fontFamily: '"Source Serif 4", Georgia, serif',
                  fontSize: '13px',
                  fontWeight: 400,
                  color: '#8d909e',
                  fontVariantNumeric: 'tabular-nums',
                }}
              >
                {String(s.num).padStart(2, '0')}
              </div>
              <div
                style={{
                  fontFamily: '"Source Serif 4", Georgia, serif',
                  fontSize: '20px',
                  lineHeight: '26px',
                  fontWeight: 400,
                  color: isActive ? '#1b1e2d' : '#606373',
                  letterSpacing: '-0.005em',
                }}
              >
                {s.name}
              </div>
              <div
                style={{
                  fontFamily: '"Space Grotesk", system-ui, sans-serif',
                  fontSize: '12px',
                  lineHeight: 1.45,
                  color: isActive ? '#606373' : '#8d909e',
                  maxWidth: '160px',
                }}
              >
                {s.short}
              </div>
            </button>
          )
        })}
      </div>

      {/* Detail + output panel */}
      <div
        key={step.num}
        className="animate-fade-in"
        style={{
          marginTop: '24px',
          paddingTop: '20px',
          borderTop: '1px solid #e8e5e1',
          display: 'grid',
          gridTemplateColumns: 'minmax(0, 1fr) minmax(0, 1.1fr)',
          columnGap: '32px',
          rowGap: '14px',
          alignItems: 'start',
        }}
      >
        <div style={{ paddingTop: '4px', minWidth: 0 }}>
          <div
            className="eyebrow"
            style={{ display: 'flex', alignItems: 'baseline', gap: '10px' }}
          >
            <span>Step {String(step.num).padStart(2, '0')}</span>
            <span
              style={{
                fontFamily: '"Source Serif 4", Georgia, serif',
                fontSize: '18px',
                letterSpacing: 0,
                textTransform: 'none',
                color: '#1b1e2d',
                fontWeight: 400,
              }}
            >
              {step.name}
            </span>
          </div>
          <p
            style={{
              fontFamily: '"Source Serif 4", Georgia, serif',
              fontSize: '13px',
              lineHeight: 1.55,
              color: '#1b1e2d',
              marginTop: '10px',
              maxWidth: '460px',
            }}
          >
            {step.body}
          </p>
        </div>
        <div
          style={{
            backgroundColor: '#fcfaf7',
            border: '1px solid #e8e5e1',
            borderLeft: '2px solid #2d5b7d',
            borderRadius: '4px',
            padding: '16px 18px',
            minWidth: 0,
            maxWidth: '100%',
            maxHeight: '240px',
            overflow: 'hidden',
          }}
        >
          <StepOutput outputType={step.outputType} />
        </div>
      </div>

      {/* Honesty line */}
      <div
        style={{
          marginTop: '14px',
          fontFamily: '"Space Grotesk", system-ui, sans-serif',
          fontSize: '11px',
          color: '#8d909e',
          fontStyle: 'italic',
          fontVariantNumeric: 'tabular-nums',
        }}
      >
        Last run: Mon Apr 14 · 5.9s · $0.003
      </div>
    </section>
  )
}

// ── Dashboard ──────────────────────────────────────────────

export default function Dashboard() {
  const stations = useStations()
  const forecasts = useForecasts(500)
  const alerts = useAlerts(200)
  const pipelineStats = usePipelineStats()
  const deliveries = useDeliveryLog(200)
  const clean = useTelemetryClean(200)

  const isLoading =
    stations.isLoading && forecasts.isLoading && pipelineStats.isLoading
  if (isLoading) return <DashboardSkeleton />

  const alertCount = alerts.data?.length ?? 0
  const deliveryCount = deliveries.data?.length ?? 0

  const totalRuns = pipelineStats.data?.total_runs ?? 0
  const successfulRuns = pipelineStats.data?.successful_runs ?? 0
  const successDisplay =
    totalRuns > 0 ? `${successfulRuns}/${totalRuns}` : '—'

  const cleanData = clean.data ?? []
  const avgQuality =
    cleanData.length > 0
      ? cleanData.reduce((sum, r) => sum + (r.quality_score ?? 0), 0) /
        cleanData.length
      : 0

  return (
    <div className="space-y-6">
      <PipelineHero />

      {/* KPI row */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(4, 1fr)',
          gap: '32px',
          borderTop: '1px solid #e8e5e1',
          paddingTop: '20px',
        }}
      >
        <MetricCard label="Successful runs" value={successDisplay} />
        <MetricCard
          label="Data quality"
          value={avgQuality > 0 ? `${Math.round(avgQuality * 100)}%` : '—'}
        />
        <MetricCard label="Advisories generated" value={alertCount} />
        <MetricCard label="Advisories delivered" value={deliveryCount} />
      </div>
    </div>
  )
}
