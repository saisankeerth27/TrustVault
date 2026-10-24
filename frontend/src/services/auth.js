import { apiClient } from '@/services/api'
import { setAccessToken } from '@/auth/tokenStore'
import { isSupabaseConfigured, supabase } from '@/auth/supabase'

export async function register(details) {
  requireSupabase()
  const { data, error } = await supabase.auth.signUp({
    email: details.email.trim().toLowerCase(),
    password: details.password,
    options: {
      data: { name: details.name },
      emailRedirectTo: `${window.location.origin}/login`,
    },
  })
  if (error) {
    throw new Error('Unable to create the account. Check the details or try again later.')
  }
  if (!data.session) {
    return { requiresEmailConfirmation: true, user: null }
  }
  return syncSupabaseSession(data.session)
}

export async function login(credentials) {
  requireSupabase()
  const { data, error } = await supabase.auth.signInWithPassword({
    email: credentials.email.trim().toLowerCase(),
    password: credentials.password,
  })
  if (error || !data.session) {
    throw new Error('Invalid email or password.')
  }
  return syncSupabaseSession(data.session)
}

export async function logout() {
  if (!supabase) {
    setAccessToken(null)
    return
  }
  const { error } = await supabase.auth.signOut()
  setAccessToken(null)
  if (error) {
    throw new Error('Unable to end the Supabase session.')
  }
}

export async function getCurrentUser() {
  const { data } = await apiClient.post('/api/v1/auth/session')
  return data
}

async function syncSupabaseSession(session) {
  setAccessToken(session.access_token)
  try {
    const { data } = await apiClient.post('/api/v1/auth/session')
    return data
  } catch (error) {
    setAccessToken(null)
    await supabase.auth.signOut()
    throw error
  }
}

function requireSupabase() {
  if (!isSupabaseConfigured || !supabase) {
    throw new Error(
      'Supabase Auth is not configured. Set the public Supabase project URL and key.',
    )
  }
}

export async function requestPasswordRecovery(email) {
  const { data } = await apiClient.post('/api/v1/auth/recovery/request', { email })
  return data
}

export async function verifyPasswordRecovery(email, token) {
  const { data } = await apiClient.post('/api/v1/auth/recovery/verify', {
    email,
    token,
  })
  return data
}

export async function updatePasswordRecovery(password) {
  const { data } = await apiClient.post(
    '/api/v1/auth/recovery/update-password',
    { password },
  )
  return data
}
