import { apiClient } from '@/services/api'

function filenameFromDisposition(disposition, fallback) {
  if (!disposition) {
    return fallback
  }

  const utf8Match = /filename\*=UTF-8''([^;]+)/i.exec(disposition)
  if (utf8Match?.[1]) {
    try {
      return decodeURIComponent(utf8Match[1])
    } catch {
      return fallback
    }
  }

  const basicMatch = /filename="?([^";]+)"?/i.exec(disposition)
  return basicMatch?.[1]?.trim() || fallback
}

export async function listDocuments(params, signal) {
  const { data } = await apiClient.get('/api/v1/documents', {
    params,
    signal,
  })
  return data
}

export async function listSharedDocuments(params, signal) {
  const { data } = await apiClient.get('/api/v1/documents/shared-with-me', {
    params,
    signal,
  })
  return data
}

export async function getDocument(documentId, signal) {
  const { data } = await apiClient.get(`/api/v1/documents/${documentId}`, {
    signal,
  })
  return data
}

export async function updateDocument(documentId, metadata) {
  const { data } = await apiClient.patch(`/api/v1/documents/${documentId}`, metadata)
  return data
}

export async function deleteDocument(documentId) {
  await apiClient.delete(`/api/v1/documents/${documentId}`)
}

export async function downloadDocument(documentId, fallbackName) {
  const response = await apiClient.get(`/api/v1/documents/${documentId}/download`, {
    responseType: 'blob',
    timeout: 60_000,
    headers: { Accept: 'application/octet-stream' },
  })

  return {
    blob: response.data,
    filename: filenameFromDisposition(
      response.headers['content-disposition'],
      fallbackName || 'document',
    ),
  }
}

export async function listDocumentVersions(documentId, signal) {
  const { data } = await apiClient.get(
    `/api/v1/documents/${documentId}/versions`,
    { signal },
  )
  return data
}

export async function downloadDocumentVersion(
  documentId,
  versionNumber,
  fallbackName,
  signal,
) {
  const response = await apiClient.get(
    `/api/v1/documents/${documentId}/versions/${versionNumber}/download`,
    {
      responseType: 'blob',
      timeout: 60_000,
      headers: { Accept: 'application/octet-stream' },
      signal,
    },
  )

  return {
    blob: response.data,
    filename: filenameFromDisposition(
      response.headers['content-disposition'],
      fallbackName || `document-version-${versionNumber}`,
    ),
  }
}

export async function deleteDocumentVersion(documentId, versionNumber) {
  const { data } = await apiClient.delete(
    `/api/v1/documents/${documentId}/versions/${versionNumber}`,
  )
  return data
}

export async function listDocumentActivity(documentId, signal) {
  const { data } = await apiClient.get(
    `/api/v1/documents/${documentId}/activity`,
    { signal },
  )
  return data
}

export async function previewDocument(documentId, signal) {
  const response = await apiClient.get(
    `/api/v1/documents/${documentId}/preview`,
    {
      responseType: 'blob',
      timeout: 60_000,
      signal,
    },
  )
  return {
    blob: response.data,
    contentType: response.headers['content-type'] || '',
  }
}

export async function createDocumentVersion(
  documentId,
  file,
  expectedVersionNumber,
  changeSummary,
  onProgress,
) {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('expected_version_number', String(expectedVersionNumber))

  const summary = changeSummary?.trim()
  if (summary) {
    formData.append('change_summary', summary)
  }

  const { data } = await apiClient.put(
    `/api/v1/documents/${documentId}/versions`,
    formData,
    {
      timeout: 60_000,
      onUploadProgress: (event) => {
        if (onProgress && event.total) {
          onProgress(Math.min(100, Math.round((event.loaded * 100) / event.total)))
        }
      },
    },
  )
  return data
}

export async function updateDocumentTextContent(
  documentId,
  content,
  expectedVersionNumber,
  changeSummary,
) {
  const { data } = await apiClient.put(
    `/api/v1/documents/${documentId}/content`,
    {
      content,
      expected_version_number: expectedVersionNumber,
      change_summary: changeSummary?.trim() || null,
    },
    { timeout: 60_000 },
  )
  return data
}

export async function uploadDocument(file, metadata, onProgress) {
  const formData = new FormData()
  formData.append('file', file)

  const category = metadata.category?.trim()
  const description = metadata.description?.trim()

  if (category) {
    formData.append('category', category)
  }
  if (description) {
    formData.append('description', description)
  }

  const { data } = await apiClient.post('/api/v1/documents/upload', formData, {
    timeout: 60_000,
    onUploadProgress: (event) => {
      if (onProgress && event.total) {
        onProgress(Math.min(100, Math.round((event.loaded * 100) / event.total)))
      }
    },
  })

  return data
}
