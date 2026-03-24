import { useParams, Link } from 'react-router-dom'
import {
  ArrowLeft,
  MapPin,
  Thermometer,
  Droplets,
  CloudRain,
  Wind,
  ShieldCheck,
} from 'lucide-react'
import { useStationLatest, useForecasts } from '../api/hooks'
import { ForecastStrip } from '../components/ForecastStrip'
import { PageLoader } from '../components/LoadingSpinner'

function formatDate(dateStr: string | undefined): string {
  if (!dateStr) return '--'
  try {
    return new Date(dateStr).toLocaleString('en-IN', {
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

  // Filter forecasts for this station
  const stationForecasts = (forecasts.data || []).filter(
    (f) => f.station_id === id
  )

  if (latest.isLoading) return <PageLoader label="Loading station..." />

  if (latest.error || !station) {
    return (
      <div className="space-y-4">
        <Link
          to="/stations"
          className="inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-700"
        >
          <ArrowLeft size={16} />
          Back to stations
        </Link>
        <div className="card card-body text-center py-12">
          <p className="text-slate-500 text-sm">
            {latest.error ? 'Failed to load station data' : 'Station not found'}
          </p>
        </div>
      </div>
    )
  }

  const observations = [
    {
      label: 'Temperature',
      value: station.temperature,
      unit: '\u00B0C',
      icon: <Thermometer size={18} className="text-amber-500" />,
    },
    {
      label: 'Humidity',
      value: station.humidity,
      unit: '%',
      icon: <Droplets size={18} className="text-blue-500" />,
    },
    {
      label: 'Rainfall',
      value: station.rainfall_mm,
      unit: 'mm',
      icon: <CloudRain size={18} className="text-blue-600" />,
    },
    {
      label: 'Wind Speed',
      value: station.wind_speed,
      unit: 'km/h',
      icon: <Wind size={18} className="text-slate-500" />,
    },
    {
      label: 'Quality Score',
      value:
        station.quality_score !== undefined && station.quality_score !== null
          ? (station.quality_score * 100).toFixed(0)
          : undefined,
      unit: '%',
      icon: <ShieldCheck size={18} className="text-emerald-500" />,
    },
  ]

  return (
    <div className="space-y-6">
      {/* Back link */}
      <Link
        to="/stations"
        className="inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-700"
      >
        <ArrowLeft size={16} />
        Back to stations
      </Link>

      {/* Header */}
      <div className="card card-body">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          <div>
            <h1 className="text-2xl font-bold text-slate-900">
              {station.station_name || id}
            </h1>
            <div className="flex items-center gap-3 mt-1.5">
              {station.state && (
                <span className="text-sm text-slate-500">{station.state}</span>
              )}
              {station.latitude !== undefined && station.longitude !== undefined && (
                <span className="flex items-center gap-1 text-xs text-slate-400">
                  <MapPin size={12} />
                  {station.latitude.toFixed(4)}, {station.longitude.toFixed(4)}
                </span>
              )}
            </div>
          </div>
          <div className="text-right">
            {station.source && (
              <span className="badge-slate text-xs">{station.source}</span>
            )}
            {station.observed_at && (
              <p className="text-xs text-slate-400 mt-1">
                Last observed: {formatDate(station.observed_at)}
              </p>
            )}
          </div>
        </div>
      </div>

      {/* Latest observations */}
      <div>
        <h2 className="text-lg font-semibold text-slate-900 mb-3">
          Latest Observation
        </h2>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4">
          {observations.map(({ label, value, unit, icon }) => (
            <div key={label} className="card card-body">
              <div className="flex items-center gap-2 mb-2">
                {icon}
                <span className="text-xs font-medium text-slate-500 uppercase tracking-wider">
                  {label}
                </span>
              </div>
              <p className="text-2xl font-bold text-slate-900">
                {value !== undefined && value !== null ? (
                  <>
                    {typeof value === 'number' ? value.toFixed(1) : value}
                    <span className="text-sm font-normal text-slate-400 ml-0.5">
                      {unit}
                    </span>
                  </>
                ) : (
                  <span className="text-slate-300">--</span>
                )}
              </p>
            </div>
          ))}
        </div>
      </div>

      {/* Forecast strip */}
      <div>
        <h2 className="text-lg font-semibold text-slate-900 mb-3">
          Forecast
        </h2>
        <div className="card card-body">
          {forecasts.isLoading ? (
            <p className="text-sm text-slate-400">Loading forecasts...</p>
          ) : (
            <ForecastStrip forecasts={stationForecasts} />
          )}
        </div>
      </div>
    </div>
  )
}
