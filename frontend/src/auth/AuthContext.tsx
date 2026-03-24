import {
  createContext,
  useContext,
  useState,
  useCallback,
  useMemo,
  type ReactNode,
} from 'react'
import { useNavigate } from 'react-router-dom'
import { loginRequest, setToken, clearToken, getToken } from '../api/client'

interface AuthContextValue {
  isAuthenticated: boolean
  login: (username: string, password: string) => Promise<void>
  logout: () => void
  isLoading: boolean
  error: string | null
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const navigate = useNavigate()
  const [isAuthenticated, setIsAuthenticated] = useState(() => !!getToken())
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const login = useCallback(
    async (username: string, password: string) => {
      setIsLoading(true)
      setError(null)
      try {
        const data = await loginRequest(username, password)
        setToken(data.access_token)
        setIsAuthenticated(true)
        navigate('/', { replace: true })
      } catch (err: any) {
        setError(err?.message || 'Login failed')
        throw err
      } finally {
        setIsLoading(false)
      }
    },
    [navigate]
  )

  const logout = useCallback(() => {
    clearToken()
    setIsAuthenticated(false)
    navigate('/login', { replace: true })
  }, [navigate])

  const value = useMemo(
    () => ({ isAuthenticated, login, logout, isLoading, error }),
    [isAuthenticated, login, logout, isLoading, error]
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
