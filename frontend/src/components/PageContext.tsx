import { useState } from 'react'
import { Info } from 'lucide-react'

interface Props {
  id: string
  children: string
}

export function PageContext({ id: _id, children }: Props) {
  const [visible, setVisible] = useState(false)

  return (
    <div className="relative inline-block mb-4" style={{ marginTop: '-4px' }}>
      <button
        onMouseEnter={() => setVisible(true)}
        onMouseLeave={() => setVisible(false)}
        onClick={() => setVisible(v => !v)}
        className="flex items-center gap-1.5 text-xs font-sans font-medium text-warm-muted hover:text-warm-body transition-colors"
        aria-label="About this page"
      >
        <Info size={14} />
        <span>About this page</span>
      </button>
      {visible && (
        <div
          className="absolute left-0 top-full mt-2 z-20 card border-l-[3px] border-l-gold p-3 shadow-lg animate-fade-in"
          style={{ width: '420px', maxWidth: 'calc(100vw - 80px)' }}
          onMouseEnter={() => setVisible(true)}
          onMouseLeave={() => setVisible(false)}
        >
          <p className="text-sm font-sans text-warm-body leading-relaxed m-0">
            {children}
          </p>
        </div>
      )}
    </div>
  )
}

export function WelcomeBanner() {
  const [dismissed, setDismissed] = useState(() => {
    try { return localStorage.getItem('weather_welcome_dismissed') === '1' } catch { return false }
  })

  if (dismissed) return null

  return (
    <div className="card border-l-[3px] border-l-gold p-4 mb-6 animate-slide-up">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-sm font-sans font-semibold text-[#1a1a1a] m-0 mb-1">
            Welcome to the AI Weather Pipeline
          </p>
          <p className="text-xs font-sans text-warm-body leading-relaxed m-0">
            This dashboard shows an AI weather pipeline that processes real data from 20 Indian
            meteorological stations every week. Explore the three stages below to see how raw observations
            become ML-corrected forecasts and bilingual farming advisories.
          </p>
        </div>
        <button
          onClick={() => {
            setDismissed(true)
            try { localStorage.setItem('weather_welcome_dismissed', '1') } catch {}
          }}
          className="text-xs font-sans font-semibold text-gold hover:text-gold-hover transition-colors whitespace-nowrap shrink-0 mt-0.5"
        >
          Got it
        </button>
      </div>
    </div>
  )
}
