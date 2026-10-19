import axios from 'axios'
import type { ApiErrorEnvelope } from '@/types/api'

const configuredBaseUrl = import.meta.env.VITE_API_BASE_URL?.trim() ?? ''

export const apiBaseUrl = configuredBaseUrl.replace(/\/+$/, '')
export const isApiConfigured = apiBaseUrl.length > 0

export const apiClient = axios.create({
  baseURL: apiBaseUrl || undefined,
  timeout: 10_000,
  headers: {
    Accept: 'application/json',
  },
})

if (!isApiConfigured && import.meta.env.DEV) {
  console.warn(
    '[TrustVault] VITE_API_BASE_URL is not set. Copy frontend/.env.example to frontend/.env to enable API requests.',
  )
}

export function getApiErrorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const data = error.response?.data as ApiErrorEnvelope | undefined
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
