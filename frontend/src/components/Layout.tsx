import { useState } from 'react'
import { Outlet } from 'react-router-dom'
import { Menu } from 'lucide-react'
import { Sidebar } from './Sidebar'
import { ChatWidget } from './ChatWidget'
import { PageTransition } from './PageTransition'

export function Layout() {
  const [sidebarOpen, setSidebarOpen] = useState(false)

  return (
    <div className="flex h-screen overflow-hidden bg-paper">
      <Sidebar open={sidebarOpen} onClose={() => setSidebarOpen(false)} />

      <div className="flex flex-col flex-1 min-w-0 overflow-hidden">
        <header
          className="flex items-center h-12 px-4 sm:px-6 shrink-0"
          style={{ background: '#ffffff' }}
        >
          <button
            onClick={() => setSidebarOpen(true)}
            aria-label="Open navigation menu"
            className="p-2 -ml-2 lg:hidden"
            style={{ color: '#606373' }}
          >
            <Menu size={20} />
          </button>
        </header>

        <main className="flex-1 overflow-y-auto" style={{ background: '#ffffff' }}>
          <div className="px-6 sm:px-10 lg:px-14 pt-4 pb-16" style={{ maxWidth: '1180px' }}>
            <PageTransition>
              <Outlet />
            </PageTransition>
          </div>
        </main>
      </div>

      <ChatWidget />
    </div>
  )
}
