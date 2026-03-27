import { useState, useEffect } from 'react'
import { ChevronDown, ChevronUp } from 'lucide-react'

interface Props {
  id: string
  children: string
}

export function PageContext({ id, children }: Props) {
  const storageKey = `page_context_${id}`
  const [collapsed, setCollapsed] = useState(() => {
    try { return localStorage.getItem(storageKey) === 'collapsed' } catch { return false }
  })

  useEffect(() => {
    try { localStorage.setItem(storageKey, collapsed ? 'collapsed' : 'expanded') } catch {}
  }, [collapsed, storageKey])

  return (
    <div
      className="border-l-2 border-gold pl-4 py-2 mb-6"
      style={{ marginTop: '-4px' }}
    >
      {collapsed ? (
        <button
          onClick={() => setCollapsed(false)}
          className="flex items-center gap-1.5 text-xs font-sans font-medium text-warm-muted hover:text-warm-body transition-colors"
        >
          <ChevronDown size={14} />
          Show context
        </button>
      ) : (
        <>
          <p className="text-sm font-sans text-warm-body leading-relaxed m-0">
            {children}
          </p>
          <button
            onClick={() => setCollapsed(true)}
            className="flex items-center gap-1 text-xs font-sans font-medium text-warm-muted hover:text-warm-body transition-colors mt-1.5"
          >
            <ChevronUp size={14} />
            Less
          </button>
        </>
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
            This dashboard shows a live AI system processing real weather data from 20 Indian
            meteorological stations. Explore the three stages below to see how raw observations
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
