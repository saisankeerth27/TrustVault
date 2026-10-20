import { apiClient } from '@/services/api'

export async function listDocumentPermissions(documentId, signal) {
  const { data } = await apiClient.get(`/api/v1/documents/${documentId}/permissions`, {
    signal,
  })
  return data
}

export async function grantDocumentPermission(documentId, { email, permission }) {
  const { data } = await apiClient.post(`/api/v1/documents/${documentId}/permissions`, {
    email,
    permission,
  })
  return data
}

export async function updateDocumentPermission(documentId, permissionId, permission) {
  const { data } = await apiClient.patch(
    `/api/v1/documents/${documentId}/permissions/${permissionId}`,
    { permission },
  )
  return data
}

export async function revokeDocumentPermission(documentId, permissionId) {
  await apiClient.delete(`/api/v1/documents/${documentId}/permissions/${permissionId}`)
}
