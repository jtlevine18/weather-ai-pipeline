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
  { to: '/stations', label: 'Data', icon: Database },
  { to: '/forecasts', label: 'Forecasts', icon: CloudSun },
  { to: '/advisories', label: 'Advisories', icon: Wheat },
  { to: '/pipeline', label: 'How it works', icon: Settings },
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
          className="fixed inset-0 z-40 lg:hidden"
          style={{ background: 'rgba(27, 30, 45, 0.4)' }}
          onClick={onClose}
        />
      )}

      <aside
        className={`
          fixed top-0 left-0 z-50 h-full w-60
          flex flex-col transition-transform duration-200 ease-in-out
          lg:translate-x-0 lg:static lg:z-auto
          ${open ? 'translate-x-0' : '-translate-x-full'}
        `}
        style={{ background: '#1b1e2d' }}
      >
        {/* Brand */}
        <div
          className="flex items-center justify-between h-16 px-5"
          style={{ borderBottom: '1px solid rgba(255,255,255,0.06)' }}
        >
          <Link to="/" className="flex items-baseline gap-2 no-underline">
            <span
              style={{
                fontFamily: '"Source Serif 4", Georgia, serif',
                fontSize: '18px',
                fontWeight: 400,
                color: '#fcfaf7',
                letterSpacing: '-0.005em',
              }}
            >
              Weather AI
            </span>
          </Link>
          <button
            onClick={onClose}
            aria-label="Close navigation menu"
            className="lg:hidden p-1"
            style={{ color: '#8d909e', background: 'none', border: 'none' }}
          >
            <X size={18} />
          </button>
        </div>

        {/* Navigation */}
        <nav className="flex-1 py-4 overflow-y-auto">
          {NAV_ITEMS.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              onClick={onClose}
              className="sidebar-link"
            >
              <Icon size={16} style={{ flexShrink: 0 }} />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>

        {/* Footer disclaimer */}
        <div
          style={{
            padding: '12px 20px 16px',
            borderTop: '1px solid rgba(255,255,255,0.06)',
            fontFamily: '"Space Grotesk", system-ui, sans-serif',
            fontSize: '10px',
            lineHeight: 1.5,
            color: '#8d909e',
            letterSpacing: '0.02em',
          }}
        >
          Farmer personas are simulated
        </div>

      </aside>

      <style>{`
        .sidebar-link {
          display: flex;
          align-items: center;
          gap: 12px;
          padding: 10px 20px;
          font-family: "Space Grotesk", system-ui, sans-serif;
          font-size: 13px;
          font-weight: 500;
          color: #8d909e;
          border-left: 2px solid transparent;
          text-decoration: none;
          transition: color 0.15s ease, border-color 0.15s ease;
        }
        .sidebar-link:hover {
          color: #fcfaf7;
        }
        .sidebar-link.active {
          color: #fcfaf7;
          border-left-color: #2d5b7d;
        }
      `}</style>
    </>
  )
}
