import { useCallback, useEffect, useMemo, useState } from 'react'
import { setAccessToken, subscribeToAccessToken } from '@/auth/tokenStore'
import { isSupabaseConfigured, supabase } from '@/auth/supabase'
import { AuthContext } from '@/auth/useAuth'
import {
  getCurrentUser,
  login as loginRequest,
  logout as logoutRequest,
  register as registerRequest,
} from '@/services/auth'

export function AuthProvider({ children }) {
  const [status, setStatus] = useState(
    isSupabaseConfigured ? 'loading' : 'unauthenticated',
  )
  const [user, setUser] = useState(null)

  useEffect(() => {
    if (!isSupabaseConfigured || !supabase) {
      return undefined
    }

    const { data } = supabase.auth.onAuthStateChange((event, session) => {
      setAccessToken(session?.access_token ?? null)
      if (event === 'SIGNED_OUT') {
        setUser(null)
        setStatus('unauthenticated')
      }
    })

    async function bootstrap() {
      try {
        const { data: sessionData, error } = await supabase.auth.getSession()
        if (error) throw error
        if (!sessionData.session) {
          setAccessToken(null)
          setUser(null)
          setStatus('unauthenticated')
          return
        }
        setAccessToken(sessionData.session.access_token)
        const currentUser = await getCurrentUser()
        setUser(currentUser)
        setStatus('authenticated')
      } catch {
        await supabase.auth.signOut()
        setAccessToken(null)
        setUser(null)
        setStatus('unauthenticated')
      }
    }

    void bootstrap()
    return () => data.subscription.unsubscribe()
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
    const account = await loginRequest(credentials)
    setUser(account)
    setStatus('authenticated')
    return account
  }, [])

  const register = useCallback(async (details) => {
    const registration = await registerRequest(details)
    if (!registration.requiresEmailConfirmation) {
      setUser(registration.user)
      setStatus('authenticated')
    }
    return registration
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
