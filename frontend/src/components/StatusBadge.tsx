interface Props {
  status: string | undefined | null
  className?: string
}

const STATUS_STYLES: Record<string, string> = {
  success: 'badge-green',
  completed: 'badge-green',
  healthy: 'badge-green',
  active: 'badge-green',
  delivered: 'badge-green',
  ok: 'badge-green',
  running: 'badge-blue',
  pending: 'badge-blue',
  info: 'badge-blue',
  processing: 'badge-blue',
  warning: 'badge-amber',
  degraded: 'badge-amber',
  partial: 'badge-amber',
  failed: 'badge-red',
  error: 'badge-red',
  critical: 'badge-red',
  inactive: 'badge-red',
  offline: 'badge-slate',
  unknown: 'badge-slate',
}

export function StatusBadge({ status, className = '' }: Props) {
  const normalized = (status || 'unknown').toLowerCase()
  const style = STATUS_STYLES[normalized] || 'badge-slate'

  return (
    <span className={`${style} ${className}`}>
      {status || 'Unknown'}
    </span>
  )
}
