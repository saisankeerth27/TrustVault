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

export const ACCESS_LEVEL_META = {
  OWNER: {
    label: 'Owner',
    shortLabel: 'Owner',
    description: 'Full control, including sharing and deletion.',
    tone: 'bg-primary/10 text-primary ring-primary/20',
  },
  EDIT: {
    label: 'Can edit',
    shortLabel: 'Edit',
    description: 'Can view, download, and update document metadata.',
    tone: 'bg-sky-50 text-sky-800 ring-sky-200',
  },
  READ: {
    label: 'Can view',
    shortLabel: 'View',
    description: 'Can view metadata and download the document.',
    tone: 'bg-emerald-50 text-emerald-800 ring-emerald-200',
  },
  ADMINISTRATOR: {
    label: 'Metadata only',
    shortLabel: 'Metadata',
    description: 'Administrator oversight without access to document content.',
    tone: 'bg-amber-50 text-amber-900 ring-amber-200',
  },
}

export function canUploadDocuments(user) {
  return Boolean(user?.id)
}

export function accessLevelOf(documentRecord) {
  return documentRecord?.access_level ?? null
}

export function canReadDocument(documentRecord) {
  return ['OWNER', 'EDIT', 'READ'].includes(accessLevelOf(documentRecord))
}

export function canEditDocument(documentRecord) {
  return ['OWNER', 'EDIT'].includes(accessLevelOf(documentRecord))
}

export function canDeleteDocument(documentRecord) {
  return accessLevelOf(documentRecord) === 'OWNER'
}

export function canManageDocumentPermissions(documentRecord) {
  return accessLevelOf(documentRecord) === 'OWNER'
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
