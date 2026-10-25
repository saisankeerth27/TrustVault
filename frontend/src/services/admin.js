import { apiClient } from '@/services/api'

export async function getAdminSummary(signal) {
  const { data } = await apiClient.get('/api/v1/admin/summary', { signal })
  return data
}

export async function listAdminUsers(params, signal) {
  const { data } = await apiClient.get('/api/v1/admin/users', {
    params,
    signal,
  })
  return data
}

export async function updateAdminUserStatus(userId, status) {
  const { data } = await apiClient.patch(
    `/api/v1/admin/users/${userId}/status`,
    { status },
  )
  return data
}

export async function updateAdminUserRole(userId, role) {
  const { data } = await apiClient.patch(
    `/api/v1/admin/users/${userId}/role`,
    { role },
  )
  return data
}

export async function deleteAdminUser(userId) {
  const { data } = await apiClient.delete(`/api/v1/admin/users/${userId}`)
  return data
}

export async function listAdminDocumentPermissions(documentId, signal) {
  const { data } = await apiClient.get(
    `/api/v1/admin/documents/${documentId}/permissions`,
    { signal },
  )
  return data
}
