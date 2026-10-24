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

  it('creates only normal-user metadata and waits for required email confirmation', async () => {
    supabase.auth.signUp.mockResolvedValue({
      data: { session: null },
      error: null,
    })
    await expect(
      register({
        name: 'New User',
        email: ' Person@Example.COM ',
        password: 'not-trimmed ',
      }),
    ).resolves.toEqual({ requiresEmailConfirmation: true, user: null })

    expect(supabase.auth.signUp).toHaveBeenCalledWith(
      expect.objectContaining({
        email: 'person@example.com',
        password: 'not-trimmed ',
        options: expect.objectContaining({
          data: { name: 'New User' },
          emailRedirectTo: expect.stringMatching(/\/login$/),
        }),
      }),
    )
    expect(apiClient.post).not.toHaveBeenCalled()
  })
})
