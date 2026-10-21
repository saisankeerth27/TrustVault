import { apiClient } from '@/services/api'

export async function register(details) {
  const { data } = await apiClient.post('/api/v1/auth/register', details)
  return data
}

export async function login(credentials) {
  const { data } = await apiClient.post('/api/v1/auth/login', credentials)
  return data
}

export async function logout() {
  await apiClient.post('/api/v1/auth/logout')
}

export async function getCurrentUser() {
  const { data } = await apiClient.get('/api/v1/auth/me')
  return data
}
