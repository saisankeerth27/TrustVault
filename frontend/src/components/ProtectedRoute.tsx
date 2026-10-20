import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { AuthLoadingScreen } from '@/components/AuthLoadingScreen'
import { useAuth } from '@/auth/useAuth'

export function ProtectedRoute() {
  const { status } = useAuth()
  const location = useLocation()

  if (status === 'loading') {
    return <AuthLoadingScreen />
  }

  if (status === 'unauthenticated') {
    return (
      <Navigate
        to="/login"
        replace
        state={{ from: `${location.pathname}${location.search}` }}
      />
    )
  }

  return <Outlet />
}
