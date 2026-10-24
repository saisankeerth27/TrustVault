import axios from 'axios'
import { getAccessToken, setAccessToken } from '@/auth/tokenStore'
import { supabase } from '@/auth/supabase'

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

if (!isApiConfigured && import.meta.env.DEV && import.meta.env.MODE !== 'test') {
  console.warn(
    '[TrustVault] VITE_API_BASE_URL is not set. Copy frontend/.env.example to frontend/.env to enable API requests.',
  )
}

let refreshPromise = null

export function refreshAccessToken() {
  if (!supabase) {
    return Promise.reject(new Error('Supabase Auth is not configured.'))
  }
  if (!refreshPromise) {
    refreshPromise = supabase.auth
      .refreshSession()
      .then(({ data, error }) => {
        if (error || !data.session) {
          throw error || new Error('The Supabase session has expired.')
        }
        setAccessToken(data.session.access_token)
        return data.session
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

function validationMessages(data) {
  const details = data?.error?.details
  if (!Array.isArray(details)) {
    return []
  }

  const messages = []
  for (const detail of details) {
    if (!detail || typeof detail !== 'object' || typeof detail.msg !== 'string') {
      continue
    }

    const message = detail.msg.trim()
    if (!message) {
      continue
    }

    const field = Array.isArray(detail.loc)
      ? detail.loc
          .filter(
            (part) =>
              typeof part === 'string' &&
              !['body', 'query', 'path', 'header', 'cookie'].includes(part),
          )
          .at(-1)
      : null
    const formatted = field ? `${field}: ${message}` : message

    if (!messages.includes(formatted)) {
      messages.push(formatted)
    }
    if (messages.length === 3) {
      break
    }
  }

  return messages
}

export function getApiErrorMessage(error) {
  if (axios.isAxiosError(error)) {
    const data = error.response?.data
    if (data?.error?.message) {
      const details = validationMessages(data)
      return details.length > 0
        ? `${data.error.message} ${details.join(' ')}`
        : data.error.message
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
