import { Loader2 } from 'lucide-react'

interface Props {
  size?: number
  className?: string
  label?: string
}

export function LoadingSpinner({ size = 24, className = '', label }: Props) {
  return (
    <div className={`flex flex-col items-center justify-center gap-3 py-12 ${className}`}>
      <Loader2 size={size} className="animate-spin text-warm-muted" />
      {label && <p className="text-sm text-warm-body">{label}</p>}
    </div>
  )
}

export function PageLoader({ label = 'Loading...' }: { label?: string }) {
  return (
    <div className="flex items-center justify-center min-h-[60vh]">
      <LoadingSpinner size={32} label={label} />
    </div>
  )
}

export function InlineLoader() {
  return <Loader2 size={16} className="animate-spin text-warm-muted inline-block" />
}

/* ── Skeleton Loaders ── */

function SkeletonPulse({ className = '' }: { className?: string }) {
  return <div className={`animate-pulse bg-warm-header-bg rounded ${className}`} />
}

export function DashboardSkeleton() {
  return (
    <div className="space-y-6 pt-7">
      {/* Hero skeleton */}
      <div className="space-y-2">
        <SkeletonPulse className="h-8 w-3/4" />
        <SkeletonPulse className="h-4 w-full max-w-lg" />
      </div>
      {/* 3 stage cards */}
      <div className="flex gap-4">
        {[0, 1, 2].map(i => (
          <div key={i} className="flex-1 card p-5 space-y-3">
            <SkeletonPulse className="h-10 w-10 rounded-lg" />
            <SkeletonPulse className="h-5 w-24" />
            <SkeletonPulse className="h-3 w-full" />
            <SkeletonPulse className="h-3 w-3/4" />
            <div className="border-t border-warm-border pt-3 space-y-2">
              <SkeletonPulse className="h-3 w-full" />
              <SkeletonPulse className="h-3 w-full" />
            </div>
          </div>
        ))}
      </div>
      {/* 4 metric cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {[0, 1, 2, 3].map(i => (
          <div key={i} className="metric-card space-y-2">
            <SkeletonPulse className="h-3 w-20" />
            <SkeletonPulse className="h-7 w-16" />
          </div>
        ))}
      </div>
    </div>
  )
}

export function TableSkeleton({ rows = 6 }: { rows?: number }) {
  return (
    <div className="space-y-6 pt-7">
      <div className="space-y-2">
        <SkeletonPulse className="h-8 w-48" />
        <SkeletonPulse className="h-4 w-96 max-w-full" />
      </div>
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {[0, 1, 2, 3].map(i => (
          <div key={i} className="metric-card space-y-2">
            <SkeletonPulse className="h-3 w-20" />
            <SkeletonPulse className="h-7 w-16" />
          </div>
        ))}
      </div>
      <div className="table-container">
        <div className="p-4 space-y-3">
          <div className="flex gap-4">
            {[0, 1, 2, 3, 4].map(i => (
              <SkeletonPulse key={i} className="h-4 flex-1" />
            ))}
          </div>
          {Array.from({ length: rows }).map((_, i) => (
            <div key={i} className="flex gap-4">
              {[0, 1, 2, 3, 4].map(j => (
                <SkeletonPulse key={j} className="h-4 flex-1" />
              ))}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

export function DetailSkeleton() {
  return (
    <div className="space-y-6 pt-4">
      <SkeletonPulse className="h-4 w-20" />
      <div className="space-y-2">
        <SkeletonPulse className="h-8 w-48" />
        <SkeletonPulse className="h-4 w-64" />
      </div>
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
        {[0, 1, 2, 3, 4].map(i => (
          <div key={i} className="card p-4 space-y-2">
            <SkeletonPulse className="h-3 w-16" />
            <SkeletonPulse className="h-7 w-20" />
          </div>
        ))}
      </div>
    </div>
  )
}
