import { useState } from 'react'
import { Outlet } from 'react-router-dom'
import { Menu } from 'lucide-react'
import { Sidebar } from './Sidebar'
import { ChatWidget } from './ChatWidget'

export function Layout() {
  const [sidebarOpen, setSidebarOpen] = useState(false)

  return (
    <div className="flex h-screen overflow-hidden bg-cream">
      <Sidebar open={sidebarOpen} onClose={() => setSidebarOpen(false)} />

      <div className="flex flex-col flex-1 min-w-0 overflow-hidden">
        <header className="flex items-center h-12 px-4 sm:px-6 bg-cream shrink-0 lg:hidden">
          <button
            onClick={() => setSidebarOpen(true)}
            className="p-2 -ml-2 rounded-md hover:bg-warm-header-bg text-warm-body"
          >
            <Menu size={20} />
          </button>
        </header>

        {/* Main content — fills available width */}
        <main className="flex-1 overflow-y-auto">
          <div className="px-5 sm:px-8 lg:px-10 pb-8 animate-fade-in">
            <Outlet />
          </div>
        </main>
      </div>

      {/* Floating chat widget */}
      <ChatWidget />
    </div>
  )
}
