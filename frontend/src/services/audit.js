import { apiClient } from '@/services/api'

export async function listAuditEvents(params, signal) {
  const { data } = await apiClient.get('/api/v1/admin/audit-events', {
    params,
    signal,
  })
  return data
}

export async function getAuditIntegrity(signal) {
  const { data } = await apiClient.get('/api/v1/admin/audit-integrity', {
    signal,
  })
  return data
}
