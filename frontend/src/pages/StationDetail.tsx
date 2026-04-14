import { useParams, Link } from 'react-router-dom'
import { ArrowLeft, MapPin } from 'lucide-react'
import { REGION } from '../regionConfig'
import { useStationLatest, useForecasts } from '../api/hooks'
import { ForecastStrip } from '../components/ForecastStrip'
import { DetailSkeleton } from '../components/LoadingSpinner'
import { AreaChart, Area, ResponsiveContainer, Tooltip } from 'recharts'

function formatDate(dateStr: string | undefined): string {
  if (!dateStr) return '—'
  try {
    return new Date(dateStr).toLocaleString(REGION.locale, {
      dateStyle: 'medium',
      timeStyle: 'short',
    })
  } catch {
    return dateStr
  }
}

export default function StationDetail() {
  const { id } = useParams<{ id: string }>()
  const latest = useStationLatest(id || '')
  const forecasts = useForecasts(7)

  const station = latest.data

  const stationForecasts = (forecasts.data || []).filter(
    (f) => f.station_id === id,
  )

  if (latest.isLoading) return <DetailSkeleton />

  if (latest.error || !station) {
    return (
      <div className="space-y-6">
        <Link
          to="/stations"
          className="inline-flex items-center gap-1.5"
          style={{
            color: '#606373',
            fontSize: '13px',
            textDecoration: 'none',
            fontFamily: '"Space Grotesk", system-ui, sans-serif',
          }}
        >
          <ArrowLeft size={14} />
          Back to stations
        </Link>
        <p style={{ color: '#8d909e', fontSize: '13px' }}>
          {latest.error ? 'Failed to load station data' : 'Station not found'}
        </p>
      </div>
    )
  }

  const observations = [
    { label: 'Temperature', value: station.temperature, unit: '°C' },
    { label: 'Humidity', value: station.humidity, unit: '%' },
    { label: 'Rainfall', value: station.rainfall_mm, unit: 'mm' },
    { label: 'Wind speed', value: station.wind_speed, unit: 'km/h' },
    {
      label: 'Quality score',
      value:
        station.quality_score !== undefined && station.quality_score !== null
          ? (station.quality_score * 100).toFixed(0)
          : undefined,
      unit: '%',
    },
  ]

  return (
    <div className="space-y-10">
      {/* Back link */}
      <Link
        to="/stations"
        className="inline-flex items-center gap-1.5"
        style={{
          color: '#606373',
          fontSize: '13px',
          textDecoration: 'none',
          fontFamily: '"Space Grotesk", system-ui, sans-serif',
        }}
      >
        <ArrowLeft size={14} />
        Back to stations
      </Link>

      {/* Header */}
      <div>
        <h1 className="page-title">
          {station.station_name || id}
        </h1>
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '20px',
            marginTop: '12px',
            fontSize: '13px',
            color: '#606373',
            flexWrap: 'wrap',
          }}
        >
          {station.latitude !== undefined && station.longitude !== undefined && (
            <span className="inline-flex items-center gap-1.5">
              <MapPin size={12} />
              <span style={{ fontVariantNumeric: 'tabular-nums' }}>
                {station.latitude.toFixed(4)}, {station.longitude.toFixed(4)}
              </span>
            </span>
          )}
          {station.source && <span>{station.source}</span>}
          {station.observed_at && (
            <span>Last observed: {formatDate(station.observed_at)}</span>
          )}
        </div>
      </div>

      {/* Latest observations */}
      <div>
        <div className="section-header">Latest observation</div>
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(5, 1fr)',
            gap: '32px',
          }}
        >
          {observations.map(({ label, value, unit }) => (
            <div key={label}>
              <div className="metric-number">
                {value !== undefined && value !== null ? (
                  <>
                    {typeof value === 'number' ? value.toFixed(1) : value}
                    <span
                      style={{
                        fontSize: '18px',
                        color: '#8d909e',
                        marginLeft: '4px',
                      }}
                    >
                      {unit}
                    </span>
                  </>
                ) : (
                  <span style={{ color: '#c4bfb6' }}>—</span>
                )}
              </div>
              <div className="metric-label">{label}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Forecast strip */}
      <div>
        <div className="section-header">Forecast</div>
        {forecasts.isLoading ? (
          <p style={{ color: '#8d909e', fontSize: '13px' }}>Loading forecasts…</p>
        ) : (
          <ForecastStrip forecasts={stationForecasts} />
        )}
      </div>

      {/* Temperature trend */}
      {stationForecasts.length > 0 && (
        <div>
          <div className="section-header">Temperature trend</div>
          <div
            style={{
              borderTop: '1px solid #e8e5e1',
              borderBottom: '1px solid #e8e5e1',
              padding: '24px 8px',
            }}
          >
            <ResponsiveContainer width="100%" height={140}>
              <AreaChart
                data={stationForecasts.map((f, i) => ({
                  day:
                    f.forecast_day !== undefined && f.forecast_day !== null
                      ? f.forecast_day === 0
                        ? 'Today'
                        : `Day ${f.forecast_day + 1}`
                      : `Day ${i + 1}`,
                  temp: f.temp_max ?? (f as any).temperature ?? 0,
                }))}
                margin={{ top: 4, right: 4, left: 4, bottom: 4 }}
              >
                <defs>
                  <linearGradient id="tempGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#2d5b7d" stopOpacity={0.15} />
                    <stop offset="100%" stopColor="#2d5b7d" stopOpacity={0.02} />
                  </linearGradient>
                </defs>
                <Tooltip
                  contentStyle={{
                    backgroundColor: '#fcfaf7',
                    border: '1px solid #e8e5e1',
                    borderRadius: '2px',
                    fontFamily: '"Space Grotesk", system-ui, sans-serif',
                    fontSize: '12px',
                  }}
                  formatter={(value: number) => [`${value.toFixed(1)}°C`, 'Temp']}
                />
                <Area
                  type="monotone"
                  dataKey="temp"
                  stroke="#2d5b7d"
                  fill="url(#tempGrad)"
                  fillOpacity={1}
                  strokeWidth={1.5}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}
    </div>
  )
}
