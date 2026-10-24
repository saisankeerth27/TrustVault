import { beforeEach, describe, expect, it, vi } from 'vitest'
import { login, register } from '@/services/auth'
import { supabase } from '@/auth/supabase'
import { apiClient } from '@/services/api'

vi.mock('@/auth/supabase', () => ({
  isSupabaseConfigured: true,
  supabase: {
    auth: {
      signInWithPassword: vi.fn(),
      signUp: vi.fn(),
      signOut: vi.fn(),
    },
  },
}))

vi.mock('@/services/api', () => ({
  apiClient: { post: vi.fn() },
}))

describe('Supabase-backed application authentication', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    supabase.auth.signInWithPassword.mockResolvedValue({
      data: { session: { access_token: 'session-token' } },
      error: null,
    })
    supabase.auth.signUp.mockResolvedValue({
      data: { session: { access_token: 'session-token' } },
      error: null,
    })
    apiClient.post.mockResolvedValue({
      data: { id: 'user-1', role: 'USER', status: 'ACTIVE' },
    })
  })

  it('authenticates with Supabase, then loads the database-authoritative account', async () => {
    await expect(
      login({ email: ' Person@Example.COM ', password: 'not-trimmed ' }),
    ).resolves.toEqual({ id: 'user-1', role: 'USER', status: 'ACTIVE' })

    expect(supabase.auth.signInWithPassword).toHaveBeenCalledWith({
      email: 'person@example.com',
      password: 'not-trimmed ',
    })
    expect(apiClient.post).toHaveBeenCalledWith('/api/v1/auth/session')
  })

  it('creates normal-user metadata without confirmation redirect and returns to signed-out state', async () => {
    supabase.auth.signOut.mockResolvedValue({ error: null })
    await expect(
      register({
        name: 'New User',
        email: ' Person@Example.COM ',
        password: 'not-trimmed ',
      }),
    ).resolves.toEqual({
      accountCreated: true,
      requiresEmailConfirmation: false,
    })

    expect(supabase.auth.signUp).toHaveBeenCalledWith({
      email: 'person@example.com',
      password: 'not-trimmed ',
      options: { data: { name: 'New User' } },
    })
    expect(apiClient.post).toHaveBeenCalledWith('/api/v1/auth/session')
    expect(supabase.auth.signOut).toHaveBeenCalledWith({ scope: 'local' })
  })

  it('does not create a TrustVault profile or treat confirmation as completed when no session is returned', async () => {
    supabase.auth.signUp.mockResolvedValue({
      data: { session: null, user: { id: 'provider-user' } },
      error: null,
    })
    await expect(
      register({
        name: 'New User',
        email: ' Person@Example.COM ',
        password: 'not-trimmed ',
      }),
    ).resolves.toEqual({
      accountCreated: true,
      requiresEmailConfirmation: true,
    })

    expect(supabase.auth.signUp).toHaveBeenCalledWith(
      {
        email: 'person@example.com',
        password: 'not-trimmed ',
        options: { data: { name: 'New User' } },
      },
    )
    expect(apiClient.post).not.toHaveBeenCalled()
    expect(supabase.auth.signOut).not.toHaveBeenCalled()
  })
})
