import axios from 'axios'
import { getAccessToken, setAccessToken } from '@/auth/tokenStore'

const configuredBaseUrl = import.meta.env.VITE_API_BASE_URL?.trim() ?? ''

export const apiBaseUrl = configuredBaseUrl.replace(/\/+$/, '')
export const isApiConfigured = apiBaseUrl.length > 0

export const apiClient = axios.create({
  baseURL: apiBaseUrl || undefined,
  timeout: 10_000,
  withCredentials: true,
  headers: {
    Accept: 'application/json',
  },
})

const refreshClient = axios.create({
  baseURL: apiBaseUrl || undefined,
  timeout: 10_000,
  withCredentials: true,
  headers: {
    Accept: 'application/json',
  },
})

if (!isApiConfigured && import.meta.env.DEV) {
  console.warn(
    '[TrustVault] VITE_API_BASE_URL is not set. Copy frontend/.env.example to frontend/.env to enable API requests.',
  )
}

let refreshPromise = null

function withRefreshLock(task) {
  if (typeof navigator !== 'undefined' && navigator.locks) {
    return navigator.locks.request('trustvault-refresh', task)
  }
  return task()
}

export function refreshAccessToken() {
  if (!refreshPromise) {
    refreshPromise = withRefreshLock(() =>
      refreshClient.post('/api/v1/auth/refresh'),
    )
      .then(({ data }) => {
        setAccessToken(data.access_token)
        return data
      })
      .finally(() => {
        refreshPromise = null
      })
  }

  return refreshPromise
}

apiClient.interceptors.request.use((config) => {
  const token = getAccessToken()
  if (token) {
    config.headers.set('Authorization', `Bearer ${token}`)
  }
  return config
})

apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    if (!axios.isAxiosError(error) || error.response?.status !== 401) {
      throw error
    }

    const config = error.config
    const url = config?.url ?? ''

    if (!config || config._retry || url.includes('/api/v1/auth/')) {
      throw error
    }

    config._retry = true

    try {
      const session = await refreshAccessToken()
      config.headers.set('Authorization', `Bearer ${session.access_token}`)
      return apiClient(config)
    } catch (refreshError) {
      setAccessToken(null)
      throw refreshError
    }
  },
)

export function getApiErrorMessage(error) {
  if (axios.isAxiosError(error)) {
    const data = error.response?.data
    if (data?.error?.message) {
      return data.error.message
    }
    if (error.code === 'ECONNABORTED') {
      return 'The request timed out. Please try again.'
    }
    if (!error.response) {
      return 'Unable to reach the TrustVault API. Confirm the backend is running and VITE_API_BASE_URL is correct.'
    }
    return `The request failed with status ${error.response.status}.`
  }

  if (error instanceof Error) {
    return error.message
  }

  return 'An unexpected error occurred.'
}
