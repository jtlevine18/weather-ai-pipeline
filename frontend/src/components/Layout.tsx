import { useState } from 'react'
import { Outlet } from 'react-router-dom'
import { Menu, LogOut } from 'lucide-react'
import { Sidebar } from './Sidebar'
import { ChatWidget } from './ChatWidget'
import { useAuth } from '../auth/AuthContext'

export function Layout() {
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const { logout } = useAuth()

  return (
    <div className="flex h-screen overflow-hidden bg-cream">
      <Sidebar open={sidebarOpen} onClose={() => setSidebarOpen(false)} />

      <div className="flex flex-col flex-1 min-w-0 overflow-hidden">
        {/* Minimal top bar — mobile menu + sign out, no white bar on desktop */}
        <header className="flex items-center justify-between h-12 px-4 sm:px-6 bg-cream shrink-0">
          <button
            onClick={() => setSidebarOpen(true)}
            className="lg:hidden p-2 -ml-2 rounded-md hover:bg-warm-header-bg text-warm-body"
          >
            <Menu size={20} />
          </button>

          <div className="hidden lg:block" />

          <button
            onClick={logout}
            className="flex items-center gap-2 text-xs font-sans text-warm-muted hover:text-[#1a1a1a] transition-colors px-3 py-1.5 rounded-lg hover:bg-warm-header-bg"
          >
            <LogOut size={14} />
            <span className="hidden sm:inline">Sign out</span>
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
