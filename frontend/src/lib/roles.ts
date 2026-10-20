import type { UserRole } from '@/types/auth'

const roleLabels: Record<UserRole, string> = {
  ADMINISTRATOR: 'Administrator',
  DOCUMENT_OWNER: 'Document owner',
  VIEWER: 'Viewer',
}

export function formatRole(role: UserRole): string {
  return roleLabels[role]
}
