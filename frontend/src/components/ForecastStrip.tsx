import {
  Sun,
  Cloud,
  CloudRain,
  CloudDrizzle,
  CloudLightning,
  CloudSnow,
  CloudFog,
  type LucideIcon,
} from 'lucide-react'
import type { Forecast } from '../api/hooks'

const CONDITION_ICONS: Record<string, LucideIcon> = {
  clear: Sun,
  sunny: Sun,
  'partly cloudy': Cloud,
  cloudy: Cloud,
  overcast: Cloud,
  rain: CloudRain,
  'heavy rain': CloudRain,
  drizzle: CloudDrizzle,
  'light rain': CloudDrizzle,
  thunderstorm: CloudLightning,
  storm: CloudLightning,
  snow: CloudSnow,
  fog: CloudFog,
  mist: CloudFog,
  haze: CloudFog,
}

const CONDITION_COLORS: Record<string, string> = {
  clear: 'text-amber-400',
  sunny: 'text-amber-400',
  'partly cloudy': 'text-slate-400',
  cloudy: 'text-slate-500',
  overcast: 'text-slate-500',
  rain: 'text-blue-500',
  'heavy rain': 'text-blue-600',
  drizzle: 'text-blue-400',
  'light rain': 'text-blue-400',
  thunderstorm: 'text-purple-500',
  storm: 'text-purple-500',
  snow: 'text-cyan-400',
  fog: 'text-slate-400',
  mist: 'text-slate-400',
  haze: 'text-slate-400',
}

function getIcon(condition: string | undefined): LucideIcon {
  if (!condition) return Cloud
  const key = condition.toLowerCase()
  return CONDITION_ICONS[key] || Cloud
}

function getColor(condition: string | undefined): string {
  if (!condition) return 'text-slate-400'
  const key = condition.toLowerCase()
  return CONDITION_COLORS[key] || 'text-slate-400'
}

function formatDay(dateStr: string | undefined, day: number | undefined): string {
  if (dateStr) {
    try {
      const d = new Date(dateStr)
      return d.toLocaleDateString('en-IN', { weekday: 'short', month: 'short', day: 'numeric' })
    } catch {
      // fall through
    }
  }
  if (day !== undefined) return `Day ${day}`
  return '--'
}

interface Props {
  forecasts: Forecast[]
}

export function ForecastStrip({ forecasts }: Props) {
  if (!forecasts.length) {
    return (
      <div className="text-sm text-slate-500 py-6 text-center">
        No forecast data available
      </div>
    )
  }

  return (
    <div className="flex gap-2 overflow-x-auto pb-2 -mx-1 px-1">
      {forecasts.map((f, i) => {
        const Icon = getIcon(f.condition)
        const color = getColor(f.condition)

        return (
          <div
            key={f.id ?? i}
            className="flex flex-col items-center gap-1.5 min-w-[5.5rem] rounded-xl bg-slate-50 border border-slate-100 px-3 py-3 shrink-0"
          >
            <span className="text-xs font-medium text-slate-500">
              {formatDay(f.forecast_date, f.forecast_day)}
            </span>
            <Icon size={24} className={color} />
            <div className="flex items-baseline gap-1">
              {f.temp_max !== undefined && f.temp_max !== null && (
                <span className="text-sm font-semibold text-slate-800">
                  {Math.round(f.temp_max)}&deg;
                </span>
              )}
              {f.temp_min !== undefined && f.temp_min !== null && (
                <span className="text-xs text-slate-400">
                  {Math.round(f.temp_min)}&deg;
                </span>
              )}
            </div>
            {f.rainfall_mm !== undefined && f.rainfall_mm !== null && f.rainfall_mm > 0 && (
              <span className="text-xs text-blue-500 font-medium">
                {f.rainfall_mm.toFixed(1)}mm
              </span>
            )}
            {f.condition && (
              <span className="text-[10px] text-slate-400 capitalize text-center leading-tight">
                {f.condition}
              </span>
            )}
          </div>
        )
      })}
    </div>
  )
}
