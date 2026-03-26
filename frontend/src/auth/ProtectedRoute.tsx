import type { ReactNode } from 'react'

export function ProtectedRoute({ children }: { children: ReactNode }) {
  // Auth disabled for portfolio demo — all pages are public
  return <>{children}</>
}
