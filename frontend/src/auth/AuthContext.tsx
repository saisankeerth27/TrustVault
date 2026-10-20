import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { setAccessToken, subscribeToAccessToken } from '@/auth/tokenStore'
import { AuthContext, type AuthStatus } from '@/auth/useAuth'
import { refreshAccessToken } from '@/services/api'
import {
  getCurrentUser,
  login as loginRequest,
  logout as logoutRequest,
} from '@/services/auth'
import type { LoginRequest, User } from '@/types/auth'

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>('loading')
  const [user, setUser] = useState<User | null>(null)
  const bootstrapStarted = useRef(false)

  useEffect(() => {
    if (bootstrapStarted.current) {
      return
    }
    bootstrapStarted.current = true

    async function bootstrap() {
      try {
        await refreshAccessToken()
        const currentUser = await getCurrentUser()
        setUser(currentUser)
        setStatus('authenticated')
      } catch {
        setAccessToken(null)
        setUser(null)
        setStatus('unauthenticated')
      }
    }

    void bootstrap()
  }, [])

  useEffect(
    () =>
      subscribeToAccessToken((token) => {
        if (token === null) {
          setUser(null)
          setStatus((current) => (current === 'loading' ? current : 'unauthenticated'))
        }
      }),
    [],
  )

  const login = useCallback(async (credentials: LoginRequest) => {
    const session = await loginRequest(credentials)
    setAccessToken(session.access_token)
    setUser(session.user)
    setStatus('authenticated')
    return session.user
  }, [])

  const logout = useCallback(async () => {
    try {
      await logoutRequest()
    } finally {
      setAccessToken(null)
      setUser(null)
      setStatus('unauthenticated')
    }
  }, [])

  const value = useMemo(
    () => ({ status, user, login, logout }),
    [status, user, login, logout],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
