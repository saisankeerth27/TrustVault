const roleLabels = {
  ADMINISTRATOR: 'Administrator',
  DOCUMENT_OWNER: 'Document owner',
  VIEWER: 'Viewer',
}

export function formatRole(role) {
  return roleLabels[role] ?? role
}
