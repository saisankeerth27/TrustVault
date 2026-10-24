import { apiClient } from '@/services/api'
import { setAccessToken } from '@/auth/tokenStore'
import { isSupabaseConfigured, supabase } from '@/auth/supabase'

export async function register(details) {
  requireSupabase()
  const { data } = await apiClient.post('/api/v1/auth/supabase/register', {
    name: details.name,
    email: details.email.trim().toLowerCase(),
    password: details.password,
  })
  if (!data.session) {
    return {
      accountCreated: Boolean(data.account_created),
      requiresEmailConfirmation: true,
    }
  }

  await persistSupabaseSession(data.session)
  return {
    accountCreated: Boolean(data.account_created),
    requiresEmailConfirmation: Boolean(data.requires_email_confirmation),
    user: data.user,
  }
}

export async function login(credentials) {
  requireSupabase()
  const { data } = await apiClient.post('/api/v1/auth/supabase/login', {
    email: credentials.email.trim().toLowerCase(),
    password: credentials.password,
  })
  await persistSupabaseSession(data.session)
  return data.user
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

async function persistSupabaseSession(session) {
  if (
    !session ||
    typeof session.access_token !== 'string' ||
    typeof session.refresh_token !== 'string'
  ) {
    throw new Error('The authentication service returned an invalid session.')
  }
  const { data, error } = await supabase.auth.setSession({
    access_token: session.access_token,
    refresh_token: session.refresh_token,
  })
  if (error || !data.session) {
    setAccessToken(null)
    throw new Error('Authentication succeeded, but the session could not be saved. Try again.')
  }
  setAccessToken(data.session.access_token)
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
