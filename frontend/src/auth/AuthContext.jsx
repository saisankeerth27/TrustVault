import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { setAccessToken, subscribeToAccessToken } from '@/auth/tokenStore'
import { AuthContext } from '@/auth/useAuth'
import { refreshAccessToken } from '@/services/api'
import {
  getCurrentUser,
  login as loginRequest,
  logout as logoutRequest,
  register as registerRequest,
} from '@/services/auth'

export function AuthProvider({ children }) {
  const [status, setStatus] = useState('loading')
  const [user, setUser] = useState(null)
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

  const login = useCallback(async (credentials) => {
    const session = await loginRequest(credentials)
    setAccessToken(session.access_token)
    setUser(session.user)
    setStatus('authenticated')
    return session.user
  }, [])

  const register = useCallback(async (details) => {
    const session = await registerRequest(details)
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
    () => ({ status, user, login, register, logout }),
    [status, user, login, register, logout],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
