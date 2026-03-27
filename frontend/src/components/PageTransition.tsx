import { useEffect, useState, type ReactNode } from 'react'
import { useLocation } from 'react-router-dom'

export function PageTransition({ children }: { children: ReactNode }) {
  const location = useLocation()
  const [visible, setVisible] = useState(false)
  const [currentKey, setCurrentKey] = useState(location.pathname)

  useEffect(() => {
    setVisible(false)
    setCurrentKey(location.pathname)
    // Trigger animation on next frame
    requestAnimationFrame(() => {
      requestAnimationFrame(() => setVisible(true))
    })
  }, [location.pathname])

  return (
    <div
      key={currentKey}
      className={visible ? 'animate-slide-up' : 'opacity-0'}
    >
      {children}
    </div>
  )
}
