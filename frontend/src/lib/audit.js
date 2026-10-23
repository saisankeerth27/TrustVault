export const AUDIT_ACTION_OPTIONS = [
  { value: 'USER_REGISTERED', label: 'User registered' },
  { value: 'USER_STATUS_CHANGED', label: 'User status changed' },
  { value: 'USER_ROLE_CHANGED', label: 'User role changed' },
  { value: 'LOGIN_SUCCESS', label: 'Login succeeded' },
  { value: 'LOGIN_FAILURE', label: 'Login failed' },
  { value: 'LOGOUT', label: 'Logout' },
  { value: 'DOCUMENT_UPLOAD', label: 'Document uploaded' },
  { value: 'DOCUMENT_METADATA_UPDATE', label: 'Document metadata updated' },
  { value: 'DOCUMENT_DOWNLOAD', label: 'Document downloaded' },
  { value: 'DOCUMENT_VERSION_CREATED', label: 'Document version created' },
  { value: 'DOCUMENT_VERSION_DELETE', label: 'Document version deleted' },
  { value: 'DOCUMENT_VERSION_DOWNLOAD', label: 'Document version downloaded' },
  { value: 'DOCUMENT_PREVIEW', label: 'Document previewed' },
  { value: 'DOCUMENT_DELETE', label: 'Document deleted' },
  { value: 'PERMISSION_GRANT', label: 'Permission granted' },
  { value: 'PERMISSION_UPDATE', label: 'Permission updated' },
  { value: 'PERMISSION_REVOKE', label: 'Permission revoked' },
  { value: 'DOCUMENT_ACCESS_DENIED', label: 'Document access denied' },
  { value: 'DOCUMENT_UPLOAD_DENIED', label: 'Document upload denied' },
  { value: 'DOCUMENT_DOWNLOAD_DENIED', label: 'Document download denied' },
  { value: 'DOCUMENT_EDIT_DENIED', label: 'Document edit denied' },
  { value: 'DOCUMENT_DELETE_DENIED', label: 'Document delete denied' },
  { value: 'PERMISSION_CHANGE_DENIED', label: 'Permission change denied' },
  { value: 'AUDIT_ACCESS_DENIED', label: 'Audit access denied' },
]

const ACTION_LABELS = Object.fromEntries(
  AUDIT_ACTION_OPTIONS.map((option) => [option.value, option.label]),
)

export const OUTCOME_META = {
  SUCCESS: {
    label: 'Success',
    tone: 'bg-emerald-50 text-emerald-800 ring-emerald-200',
  },
  DENIED: {
    label: 'Denied',
    tone: 'bg-amber-50 text-amber-900 ring-amber-200',
  },
  FAILURE: {
    label: 'Failure',
    tone: 'bg-red-50 text-red-800 ring-red-200',
  },
}

export const INTEGRITY_META = {
  VERIFIED: {
    label: 'Verified',
    tone: 'bg-emerald-50 text-emerald-800 ring-emerald-200',
    description: 'The hash chain and signed checkpoint both match the stored audit history.',
  },
  CHAIN_VALID_CHECKPOINT_STALE: {
    label: 'Checkpoint stale',
    tone: 'bg-amber-50 text-amber-900 ring-amber-200',
    description:
      'The hash chain is consistent, but the signed checkpoint does not yet cover the latest events.',
  },
  CHAIN_VALID_CHECKPOINT_MISSING: {
    label: 'Checkpoint missing',
    tone: 'bg-amber-50 text-amber-900 ring-amber-200',
    description:
      'The hash chain is consistent, but no usable signed checkpoint is configured or available.',
  },
  INVALID: {
    label: 'Integrity failure',
    tone: 'bg-red-50 text-red-800 ring-red-200',
    description: 'The audit chain or checkpoint failed verification. Investigate immediately.',
  },
}

export const CHECKPOINT_META = {
  VALID: { label: 'Valid', tone: 'text-emerald-700' },
  STALE: { label: 'Stale', tone: 'text-amber-700' },
  MISSING: { label: 'Missing', tone: 'text-amber-700' },
  UNCONFIGURED: { label: 'Not configured', tone: 'text-muted-foreground' },
  UNAVAILABLE: { label: 'Unavailable', tone: 'text-muted-foreground' },
  INVALID: { label: 'Invalid', tone: 'text-red-700' },
}

export function formatAuditAction(value) {
  return ACTION_LABELS[value] ?? value
}

export function outcomeMeta(value) {
  return (
    OUTCOME_META[value] ?? {
      label: value || 'Unknown',
      tone: 'bg-muted text-muted-foreground ring-border',
    }
  )
}

export function integrityMeta(value) {
  return (
    INTEGRITY_META[value] ?? {
      label: value || 'Unknown',
      tone: 'bg-muted text-muted-foreground ring-border',
      description: 'The integrity status could not be interpreted.',
    }
  )
}

export function checkpointMeta(value) {
  return CHECKPOINT_META[value] ?? { label: value || 'Unknown', tone: 'text-muted-foreground' }
}

const AUDIT_FIELD_LABELS = {
  actor_id: 'Actor ID',
  access_level: 'Access level',
  actor_name: 'Actor',
  change_summary: 'Change summary',
  changed_fields: 'Changed fields',
  client_ip: 'Client IP',
  current_version_number: 'Resulting current version',
  file_size: 'File size',
  hash_schema: 'Hash schema',
  document_id: 'Document ID',
  event_id: 'Audit event ID',
  chain_index: 'Audit sequence',
  request_id: 'Request ID / correlation ID',
  mime_type: 'MIME type',
  previous_current_version_number: 'Previous current version',
  previous_permission: 'Previous permission',
  previous_version_number: 'Previous version',
  reason: 'Reason',
  recipient_id: 'Recipient ID',
  resource_type: 'Resource type',
  role: 'Role',
  rolled_back_to_version_number: 'Rolled back to version',
  rollback: 'Rollback',
  source: 'Source',
  status: 'Status',
  storage_deleted: 'Storage object deleted',
  target_user_id: 'Target user ID',
  user_agent: 'User agent',
  version_number: 'Version',
  was_current: 'Was current version',
}

function auditScalarText(value) {
  if (value === null || value === undefined) {
    return 'Not recorded'
  }
  return String(value).replaceAll('_', ' ').toLowerCase()
}

export function auditFieldLabel(key) {
  return (
    AUDIT_FIELD_LABELS[key] ||
    String(key)
      .replaceAll('_', ' ')
      .replace(/\b\w/g, (character) => character.toUpperCase())
  )
}

export function auditEventSummary(details) {
  if (!details || typeof details !== 'object') {
    return []
  }

  const parts = []
  const versionNumber = details.version_number
  const previousVersion = details.previous_version_number

  if (Number.isInteger(versionNumber)) {
    parts.push(
      Number.isInteger(previousVersion)
        ? `Version ${versionNumber} replaced version ${previousVersion}`
        : `Version ${versionNumber}`,
    )
  }
  if (
    details.rollback &&
    Number.isInteger(details.rolled_back_to_version_number)
  ) {
    parts.push(`Rolled back to version ${details.rolled_back_to_version_number}`)
  }
  if (Array.isArray(details.changed_fields) && details.changed_fields.length > 0) {
    parts.push(`Changed ${details.changed_fields.join(', ')}`)
  }
  if (details.permission) {
    parts.push(`Permission: ${auditScalarText(details.permission)}`)
  }
  if (details.reason) {
    parts.push(`Reason: ${auditScalarText(details.reason)}`)
  }
  if (details.source) {
    parts.push(`Source: ${auditScalarText(details.source)}`)
  }
  if (details.change_summary) {
    parts.push(details.change_summary)
  }

  return parts
}
