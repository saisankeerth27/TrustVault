const roleLabels = {
  ADMINISTRATOR: 'Administrator',
  USER: 'User',
}

export function formatRole(role) {
  return roleLabels[role] ?? role
}
