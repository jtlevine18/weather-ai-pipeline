import { Loader2 } from 'lucide-react'

interface Props {
  size?: number
  className?: string
  label?: string
}

export function LoadingSpinner({ size = 24, className = '', label }: Props) {
  return (
    <div className={`flex flex-col items-center justify-center gap-3 py-12 ${className}`}>
      <Loader2 size={size} className="animate-spin text-slate-400" />
      {label && <p className="text-sm text-slate-500">{label}</p>}
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
  return <Loader2 size={16} className="animate-spin text-slate-400 inline-block" />
}
