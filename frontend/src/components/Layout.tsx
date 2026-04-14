import { useState } from 'react'
import { Outlet } from 'react-router-dom'
import { Menu, CloudSun } from 'lucide-react'
import { Sidebar } from './Sidebar'
import { ChatWidget } from './ChatWidget'
import { PageTransition } from './PageTransition'

export function Layout() {
  const [sidebarOpen, setSidebarOpen] = useState(false)

  return (
    <div className="flex h-screen overflow-hidden bg-cream">
      <Sidebar open={sidebarOpen} onClose={() => setSidebarOpen(false)} />

      <div className="flex flex-col flex-1 min-w-0 overflow-hidden">
        <header className="flex items-center justify-between h-12 px-4 sm:px-6 bg-cream shrink-0">
          <button
            onClick={() => setSidebarOpen(true)}
            aria-label="Open navigation menu"
            className="p-2 -ml-2 rounded-md hover:bg-warm-header-bg text-warm-body lg:hidden"
          >
            <Menu size={20} />
          </button>
          <button
            onClick={() => window.dispatchEvent(new Event('relaunch-tour'))}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-sans font-medium text-warm-muted hover:text-[#1a1a1a] hover:bg-warm-header-bg transition-colors ml-auto"
            title="Take the guided tour"
          >
            <CloudSun size={14} />
            Tour
          </button>
        </header>

        <main className="flex-1 overflow-y-auto">
          <div className="px-5 sm:px-8 lg:px-10 pb-8">
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
