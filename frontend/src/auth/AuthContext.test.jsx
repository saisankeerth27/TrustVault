import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AuthProvider } from '@/auth/AuthContext'
import { useAuth } from '@/auth/useAuth'

const mocks = vi.hoisted(() => ({
  getSession: vi.fn(),
  onAuthStateChange: vi.fn(),
  register: vi.fn(),
}))

vi.mock('@/auth/supabase', () => ({
  isSupabaseConfigured: true,
  supabase: {
    auth: {
      getSession: mocks.getSession,
      onAuthStateChange: mocks.onAuthStateChange,
      signOut: vi.fn(),
    },
  },
}))

vi.mock('@/auth/tokenStore', () => ({
  setAccessToken: vi.fn(),
  subscribeToAccessToken: vi.fn(() => () => {}),
}))

vi.mock('@/services/auth', () => ({
  getCurrentUser: vi.fn(),
  login: vi.fn(),
  logout: vi.fn(),
  register: mocks.register,
}))

function AuthState() {
  const { status, register } = useAuth()
  return (
    <>
      <p>{status}</p>
      <button
        type="button"
        onClick={() => {
          void register({ name: 'New User' })
        }}
      >
        Register
      </button>
    </>
  )
}

describe('AuthProvider registration state', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.getSession.mockResolvedValue({
      data: { session: null },
      error: null,
    })
    mocks.onAuthStateChange.mockReturnValue({
      data: { subscription: { unsubscribe: vi.fn() } },
    })
  })

  it('enters the authenticated state only after a signup session is profile-synced', async () => {
    mocks.register.mockResolvedValue({
      accountCreated: true,
      requiresEmailConfirmation: false,
      user: { id: 'user-1', role: 'USER' },
    })
    render(
      <AuthProvider>
        <AuthState />
      </AuthProvider>,
    )

    expect(await screen.findByText('unauthenticated')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Register' }))

    expect(await screen.findByText('authenticated')).toBeInTheDocument()
  })

  it('stays unauthenticated when signup requires email confirmation', async () => {
    mocks.register.mockResolvedValue({
      accountCreated: true,
      requiresEmailConfirmation: true,
    })
    render(
      <AuthProvider>
        <AuthState />
      </AuthProvider>,
    )

    expect(await screen.findByText('unauthenticated')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Register' }))

    expect(await screen.findByText('unauthenticated')).toBeInTheDocument()
  })
})
