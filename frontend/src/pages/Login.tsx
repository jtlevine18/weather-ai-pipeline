import { useState, type FormEvent } from 'react'
import { Navigate } from 'react-router-dom'
import { CloudSun, Eye, EyeOff } from 'lucide-react'
import { useAuth } from '../auth/AuthContext'
import { InlineLoader } from '../components/LoadingSpinner'

export default function Login() {
  const { login, isAuthenticated, isLoading, error } = useAuth()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)

  if (isAuthenticated) return <Navigate to="/" replace />

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!username.trim() || !password.trim()) return
    try {
      await login(username.trim(), password)
    } catch {
      // error is set in context
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-cream px-4">
      <div className="w-full max-w-sm">
        {/* Brand */}
        <div className="flex flex-col items-center mb-8">
          <div className="w-14 h-14 rounded-2xl bg-gold flex items-center justify-center shadow-lg mb-4"
               style={{ boxShadow: '0 8px 24px rgba(212,160,25,0.25)' }}>
            <CloudSun size={28} className="text-white" />
          </div>
          <h1 className="text-xl font-bold font-serif" style={{ color: '#1a1a1a' }}>
            Weather Pipeline
          </h1>
          <p className="text-sm mt-1" style={{ color: '#888' }}>
            Sign in to your dashboard
          </p>
        </div>

        {/* Login form */}
        <form onSubmit={handleSubmit} className="card card-body space-y-5">
          {error && (
            <div style={{
              background: 'rgba(230,57,70,0.08)', border: '1px solid rgba(230,57,70,0.3)',
              borderRadius: '8px', padding: '10px 14px', fontSize: '0.85rem', color: '#e63946',
            }}>
              {error.includes('401') || error.includes('Unauthorized')
                ? 'Invalid username or password'
                : error}
            </div>
          )}

          <div>
            <label htmlFor="username" className="block text-sm font-medium mb-1.5" style={{ color: '#555' }}>
              Username
            </label>
            <input
              id="username"
              type="text"
              autoComplete="username"
              className="input"
              placeholder="Enter username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              disabled={isLoading}
              autoFocus
            />
          </div>

          <div>
            <label htmlFor="password" className="block text-sm font-medium mb-1.5" style={{ color: '#555' }}>
              Password
            </label>
            <div className="relative">
              <input
                id="password"
                type={showPassword ? 'text' : 'password'}
                autoComplete="current-password"
                className="input pr-10"
                placeholder="Enter password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                disabled={isLoading}
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute right-3 top-1/2 -translate-y-1/2"
                style={{ color: '#888' }}
                tabIndex={-1}
              >
                {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </div>
          </div>

          <button
            type="submit"
            disabled={isLoading || !username.trim() || !password.trim()}
            className="btn-primary w-full"
          >
            {isLoading ? (
              <>
                <InlineLoader /> Signing in...
              </>
            ) : (
              'Sign in'
            )}
          </button>
        </form>

        <p className="text-center text-xs mt-6" style={{ color: '#999' }}>
          Agricultural Weather Forecasting System
        </p>
      </div>
    </div>
  )
}
