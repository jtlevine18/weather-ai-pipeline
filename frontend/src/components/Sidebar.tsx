import { NavLink, Link } from 'react-router-dom'
import {
  Home,
  Database,
  CloudSun,
  Wheat,
  Settings,
  X,
} from 'lucide-react'

const NAV_ITEMS = [
  { to: '/', label: 'Home', icon: Home },
  { to: '/stations', label: 'Stations', icon: Database },
  { to: '/forecasts', label: 'Forecasts', icon: CloudSun },
  { to: '/advisories', label: 'Advisories', icon: Wheat },
  { to: '/pipeline', label: 'System', icon: Settings },
]

interface Props {
  open: boolean
  onClose: () => void
}

export function Sidebar({ open, onClose }: Props) {
  return (
    <>
      {/* Backdrop for mobile */}
      {open && (
        <div
          className="fixed inset-0 z-40 bg-black/30 backdrop-blur-sm lg:hidden"
          onClick={onClose}
        />
      )}

      <aside
        className={`
          fixed top-0 left-0 z-50 h-full w-72
          flex flex-col transition-transform duration-200 ease-in-out
          lg:translate-x-0 lg:static lg:z-auto
          ${open ? 'translate-x-0' : '-translate-x-full'}
        `}
        style={{ background: 'linear-gradient(180deg, #1a1a1a 0%, #222018 100%)' }}
      >
        {/* Brand */}
        <div className="flex items-center justify-between h-16 px-5 border-b border-white/10">
          <Link to="/" className="flex items-center gap-2.5 no-underline">
            <div className="w-8 h-8 rounded-lg bg-gold flex items-center justify-center">
              <CloudSun size={18} className="text-white" />
            </div>
            <div>
              <h1 className="text-sm font-bold text-white leading-tight font-serif">Weather</h1>
              <p className="text-[10px] text-[#e0dcd5] font-sans font-medium uppercase tracking-wider">Pipeline</p>
            </div>
          </Link>
          <button
            onClick={onClose}
            className="lg:hidden p-1 rounded-md hover:bg-white/10 text-[#e0dcd5]"
          >
            <X size={20} />
          </button>
        </div>

        {/* Navigation */}
        <nav className="flex-1 px-3 py-4 space-y-0.5 overflow-y-auto">
          {NAV_ITEMS.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              onClick={onClose}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-sans font-medium transition-colors duration-100 ${
                  isActive
                    ? 'bg-gold/15 text-gold'
                    : 'text-[#e0dcd5] hover:bg-white/5 hover:text-white'
                }`
              }
            >
              <Icon size={18} />
              {label}
            </NavLink>
          ))}
        </nav>

        {/* Footer */}
        <div className="px-5 py-3 border-t border-white/10">
          <p className="text-[10px] text-[#e0dcd5]/60 font-sans uppercase tracking-wider">
            Kerala &middot; Tamil Nadu
          </p>
        </div>
      </aside>
    </>
  )
}
