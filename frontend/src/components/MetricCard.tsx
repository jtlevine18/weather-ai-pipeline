import type { ReactNode } from 'react'

interface Props {
  label: string
  value: string | number | undefined | null
  icon?: ReactNode
  subtitle?: string
  className?: string
}

export function MetricCard({ label, value, subtitle, className = '' }: Props) {
  return (
    <div className={`metric-card ${className}`}>
      <div className="metric-label">{label}</div>
      <div className="metric-value">
        {value !== null && value !== undefined ? value : '--'}
      </div>
      {subtitle && (
        <p className="text-xs text-warm-muted mt-1">{subtitle}</p>
      )}
    </div>
  )
}
