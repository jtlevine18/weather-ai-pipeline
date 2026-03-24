const TOKEN_KEY = 'weather_jwt'

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function setToken(token: string) {
  localStorage.setItem(TOKEN_KEY, token)
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY)
}

export class ApiError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

export async function apiFetch<T>(
  url: string,
  options: RequestInit = {}
): Promise<T> {
  const token = getToken()

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...((options.headers as Record<string, string>) || {}),
  }

  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }

  const response = await fetch(url, {
    ...options,
    headers,
  })

  if (response.status === 401) {
    clearToken()
    window.location.href = '/login'
    throw new ApiError('Unauthorized', 401)
  }

  if (!response.ok) {
    const body = await response.text().catch(() => '')
    throw new ApiError(
      body || `Request failed with status ${response.status}`,
      response.status
    )
  }

  if (response.status === 204) {
    return undefined as T
  }

  return response.json()
}

export async function loginRequest(
  username: string,
  password: string
): Promise<{ access_token: string; token_type: string }> {
  const body = new URLSearchParams({ username, password })

  const response = await fetch('/auth/token', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body,
  })

  if (!response.ok) {
    const err = await response.text().catch(() => '')
    throw new ApiError(err || 'Login failed', response.status)
  }

  return response.json()
}
