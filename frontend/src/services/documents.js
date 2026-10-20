import { apiClient } from '@/services/api'

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
