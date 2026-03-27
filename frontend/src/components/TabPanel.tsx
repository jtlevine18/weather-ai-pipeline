import { useEffect, useState, type ReactNode } from 'react'

interface Props {
  active: boolean
  children: ReactNode
}

export function TabPanel({ active, children }: Props) {
  const [mounted, setMounted] = useState(false)

  useEffect(() => {
    if (active) {
      setMounted(false)
      requestAnimationFrame(() => {
        requestAnimationFrame(() => setMounted(true))
      })
    }
  }, [active])

  if (!active) return null

  return (
    <div className={mounted ? 'animate-tab-enter' : 'opacity-0'}>
      {children}
    </div>
  )
}
