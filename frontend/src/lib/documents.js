export const MAX_UPLOAD_BYTES = 10 * 1024 * 1024

export const ALLOWED_EXTENSIONS = ['pdf', 'txt', 'docx', 'png', 'jpg', 'jpeg']

export const CATEGORY_OPTIONS = [
  'General',
  'Contracts',
  'Finance',
  'Human resources',
  'Legal',
  'Other',
]

export const SORT_OPTIONS = [
  { value: 'created_at:desc', label: 'Newest first' },
  { value: 'created_at:asc', label: 'Oldest first' },
  { value: 'name:asc', label: 'Name A-Z' },
  { value: 'name:desc', label: 'Name Z-A' },
  { value: 'file_size:desc', label: 'Largest first' },
  { value: 'file_size:asc', label: 'Smallest first' },
  { value: 'updated_at:desc', label: 'Recently updated' },
]

export function isFile(value) {
  return typeof File !== 'undefined' && value instanceof File
}

export function extensionOf(filename) {
  const parts = String(filename || '').toLowerCase().split('.')
  return parts.length > 1 ? parts.pop() : ''
}

export function formatBytes(bytes) {
  if (!Number.isFinite(bytes) || bytes < 0) {
    return 'Unknown size'
  }
  if (bytes < 1024) {
    return `${bytes} B`
  }
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`
  }
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export function formatDateTime(value) {
  if (!value) {
    return 'Not recorded'
  }
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? 'Not recorded' : parsed.toLocaleString()
}

export function formatDate(value) {
  if (!value) {
    return 'Not recorded'
  }
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime())
    ? 'Not recorded'
    : parsed.toLocaleDateString(undefined, {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
      })
}

export function isDocumentManager(user) {
  return user?.role === 'ADMINISTRATOR' || user?.role === 'DOCUMENT_OWNER'
}

export function canManageDocument(user, documentRecord) {
  return Boolean(
    user?.id &&
      documentRecord?.owner_id &&
      user.id === documentRecord.owner_id &&
      isDocumentManager(user),
  )
}

export function categoryChoices(currentCategory) {
  const choices = [...CATEGORY_OPTIONS]
  if (currentCategory && !choices.includes(currentCategory)) {
    choices.push(currentCategory)
  }
  return choices
}

export function saveBlob(blob, filename) {
  const objectUrl = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = objectUrl
  anchor.download = filename || 'document'
  anchor.rel = 'noopener'
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1_000)
}
