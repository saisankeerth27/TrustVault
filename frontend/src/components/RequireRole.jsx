import { Navigate, Outlet } from 'react-router-dom'
import { useAuth } from '@/auth/useAuth'
import { AuthLoadingScreen } from '@/components/AuthLoadingScreen'
import { ForbiddenState } from '@/components/ForbiddenState'
import { formatRole } from '@/lib/roles'

export function RequireRole({ role }) {
  const { status, user } = useAuth()

  if (status === 'loading') {
    return <AuthLoadingScreen />
  }

  if (status === 'unauthenticated' || !user) {
    return <Navigate to="/login" replace />
  }

  if (user.role !== role) {
    return <ForbiddenState requiredRole={formatRole(role)} />
  }

  return <Outlet />
}
