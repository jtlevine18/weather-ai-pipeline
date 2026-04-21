import { REGION } from '../regionConfig'
import type { Forecast } from '../api/hooks'
import { ProbabilityChip } from './ProbabilityChip'

function formatDay(dateStr: string | undefined, day: number | undefined): string {
  if (dateStr) {
    try {
      const d = new Date(dateStr)
      return d.toLocaleDateString(REGION.locale, {
        weekday: 'short',
        month: 'short',
        day: 'numeric',
      })
    } catch {
      // fall through
    }
  }
  if (day !== undefined) return `Day ${day}`
  return '—'
}

interface Props {
  forecasts: Forecast[]
}

export function ForecastStrip({ forecasts }: Props) {
  if (!forecasts.length) {
    return (
      <p style={{ fontSize: '13px', color: '#8d909e', padding: '16px 0' }}>
        No forecast data available
      </p>
    )
  }

  return (
    <div
      className="overflow-x-auto"
      style={{
        display: 'grid',
        gridTemplateColumns: `repeat(${forecasts.length}, minmax(120px, 1fr))`,
        gap: '0',
        borderTop: '1px solid #e8e5e1',
        borderBottom: '1px solid #e8e5e1',
      }}
    >
      {forecasts.map((f, i) => (
        <div
          key={f.id ?? i}
          style={{
            padding: '20px 12px',
            borderRight:
              i < forecasts.length - 1 ? '1px solid #f2efeb' : 'none',
            textAlign: 'left',
          }}
        >
          <div
            className="eyebrow"
            style={{ fontSize: '11px', textTransform: 'none' }}
          >
            {formatDay(f.valid_for_ts, f.forecast_day)}
          </div>
          <div
            style={{
              fontFamily: '"Source Serif 4", Georgia, serif',
              fontSize: '24px',
              lineHeight: '30px',
              color: '#1b1e2d',
              marginTop: '10px',
              fontVariantNumeric: 'tabular-nums',
            }}
          >
            {f.temp_max !== undefined && f.temp_max !== null
              ? `${Math.round(f.temp_max)}°`
              : '—'}
            {f.temp_min !== undefined && f.temp_min !== null && (
              <span
                style={{
                  fontSize: '14px',
                  color: '#8d909e',
                  marginLeft: '6px',
                }}
              >
                {Math.round(f.temp_min)}°
              </span>
            )}
          </div>
          {f.rainfall !== undefined &&
            f.rainfall !== null &&
            f.rainfall > 0 && (
              <div
                style={{
                  fontSize: '12px',
                  color: '#2d5b7d',
                  marginTop: '4px',
                  fontVariantNumeric: 'tabular-nums',
                }}
              >
                {f.rainfall.toFixed(1)} mm
              </div>
            )}
          {f.condition && (
            <div
              style={{
                fontSize: '12px',
                color: '#606373',
                marginTop: '4px',
                textTransform: 'capitalize',
              }}
            >
              {f.condition}
            </div>
          )}
          <ProbabilityChip
            rain_prob_5mm={f.rain_prob_5mm}
            rainfall={f.rainfall}
            rain_p50={f.rain_p50}
          />
        </div>
      ))}
    </div>
  )
}
