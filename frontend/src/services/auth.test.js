import { beforeEach, describe, expect, it, vi } from 'vitest'
import { login, register } from '@/services/auth'
import { supabase } from '@/auth/supabase'
import { apiClient } from '@/services/api'

vi.mock('@/auth/supabase', () => ({
  isSupabaseConfigured: true,
  supabase: {
    auth: {
      setSession: vi.fn(),
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
    supabase.auth.setSession.mockResolvedValue({
      data: { session: { access_token: 'session-token' } },
      error: null,
    })
    apiClient.post.mockResolvedValue({
      data: {
        account_created: true,
        requires_email_confirmation: false,
        session: {
          access_token: 'provider-access-token',
          refresh_token: 'provider-refresh-token',
        },
        user: { id: 'user-1', role: 'USER', status: 'ACTIVE' },
      },
    })
  })

  it('authenticates through the backend and persists the Supabase session', async () => {
    await expect(
      login({ email: ' Person@Example.COM ', password: 'not-trimmed ' }),
    ).resolves.toEqual({ id: 'user-1', role: 'USER', status: 'ACTIVE' })

    expect(apiClient.post).toHaveBeenCalledWith('/api/v1/auth/supabase/login', {
      email: 'person@example.com',
      password: 'not-trimmed ',
    })
    expect(supabase.auth.setSession).toHaveBeenCalledWith({
      access_token: 'provider-access-token',
      refresh_token: 'provider-refresh-token',
    })
  })

  it('creates a normal-user profile and returns the authenticated session', async () => {
    await expect(
      register({
        name: 'New User',
        email: ' Person@Example.COM ',
        password: 'not-trimmed ',
      }),
    ).resolves.toEqual({
      accountCreated: true,
      requiresEmailConfirmation: false,
      user: { id: 'user-1', role: 'USER', status: 'ACTIVE' },
    })

    expect(apiClient.post).toHaveBeenCalledWith('/api/v1/auth/supabase/register', {
      name: 'New User',
      email: 'person@example.com',
      password: 'not-trimmed ',
    })
    expect(supabase.auth.setSession).toHaveBeenCalledWith({
      access_token: 'provider-access-token',
      refresh_token: 'provider-refresh-token',
    })
    expect(supabase.auth.signOut).not.toHaveBeenCalled()
  })

  it('keeps confirmation-required signups signed out and does not create a profile early', async () => {
    apiClient.post.mockResolvedValue({
      data: {
        session: null,
        account_created: true,
        requires_email_confirmation: true,
      },
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

    expect(apiClient.post).toHaveBeenCalledWith('/api/v1/auth/supabase/register', {
      name: 'New User',
      email: 'person@example.com',
      password: 'not-trimmed ',
    })
    expect(supabase.auth.setSession).not.toHaveBeenCalled()
    expect(supabase.auth.signOut).not.toHaveBeenCalled()
  })

  it('does not claim a duplicate account was created when Supabase obfuscates the signup response', async () => {
    apiClient.post.mockResolvedValue({
      data: {
        session: null,
        account_created: false,
        requires_email_confirmation: true,
      },
    })

    await expect(
      register({
        name: 'New User',
        email: ' Person@Example.COM ',
        password: 'not-trimmed ',
      }),
    ).resolves.toEqual({
      accountCreated: false,
      requiresEmailConfirmation: true,
    })

    expect(supabase.auth.setSession).not.toHaveBeenCalled()
  })
})
