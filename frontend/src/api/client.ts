const API_BASE = import.meta.env.VITE_API_URL || 'https://jtlevine-weather-pipeline-api.hf.space'

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
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...((options.headers as Record<string, string>) || {}),
  }

  const response = await fetch(`${API_BASE}${url}`, {
    ...options,
    headers,
  })

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
