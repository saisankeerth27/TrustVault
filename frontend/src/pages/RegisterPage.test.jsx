import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { LoginPage } from '@/pages/LoginPage'
import { RegisterPage } from '@/pages/RegisterPage'

const register = vi.fn()
const { resendEmailConfirmation } = vi.hoisted(() => ({
  resendEmailConfirmation: vi.fn(),
}))

vi.mock('@/auth/useAuth', () => ({
  useAuth: () => ({
    status: 'unauthenticated',
    register,
  }),
}))

vi.mock('@/services/api', () => ({
  getApiErrorMessage: (error) => error.message,
}))

vi.mock('@/services/auth', () => ({
  resendEmailConfirmation,
}))

function renderRegistration() {
  return render(
    <MemoryRouter initialEntries={['/register']}>
      <Routes>
        <Route path="/register" element={<RegisterPage />} />
        <Route path="/login" element={<LoginPage />} />
        <Route path="/dashboard" element={<DashboardDestination />} />
      </Routes>
    </MemoryRouter>,
  )
}

function DashboardDestination() {
  const location = useLocation()
  return (
    <>
      <h1>Dashboard</h1>
      {location.state?.registrationMessage ? (
        <div role="status">{location.state.registrationMessage}</div>
      ) : null}
    </>
  )
}

describe('RegisterPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    resendEmailConfirmation.mockResolvedValue({
      message: 'If an account is awaiting confirmation, a new email will be sent.',
    })
  })

  it('redirects a successfully created account to Dashboard with a success message', async () => {
    register.mockResolvedValue({
      accountCreated: true,
      requiresEmailConfirmation: false,
    })
    renderRegistration()

    fireEvent.change(screen.getByLabelText('Full name'), {
      target: { value: 'New User' },
    })
    fireEvent.change(screen.getByLabelText('Email address'), {
      target: { value: 'new@example.com' },
    })
    fireEvent.change(screen.getByLabelText('Password'), {
      target: { value: 'a secure password 123' },
    })
    fireEvent.change(screen.getByLabelText('Confirm password'), {
      target: { value: 'a secure password 123' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Create account' }))

    expect(await screen.findByRole('heading', { name: 'Dashboard' })).toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent('Account created successfully.')
    expect(register).toHaveBeenCalledOnce()
    expect(register).toHaveBeenCalledWith({
      name: 'New User',
      email: 'new@example.com',
      password: 'a secure password 123',
    })
  })

  it('keeps a confirmation-required signup signed out and offers Login', async () => {
    register.mockResolvedValue({
      accountCreated: true,
      requiresEmailConfirmation: true,
    })
    renderRegistration()

    fireEvent.change(screen.getByLabelText('Full name'), {
      target: { value: 'New User' },
    })
    fireEvent.change(screen.getByLabelText('Email address'), {
      target: { value: 'new@example.com' },
    })
    fireEvent.change(screen.getByLabelText('Password'), {
      target: { value: 'a secure password 123' },
    })
    fireEvent.change(screen.getByLabelText('Confirm password'), {
      target: { value: 'a secure password 123' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Create account' }))

    expect(
      await screen.findByRole('status'),
    ).toHaveTextContent(
      'Your account has been created. Check your email for confirmation instructions, then sign in.',
    )
    expect(screen.getByRole('link', { name: 'Return to Login' })).toHaveAttribute(
      'href',
      '/login',
    )
    expect(screen.getByRole('heading', { name: 'Create account' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Dashboard' })).not.toBeInTheDocument()
    await waitFor(() => expect(register).toHaveBeenCalledOnce())
  })

  it('lets a confirmation-pending signup request another email without exposing account state', async () => {
    vi.useFakeTimers()
    register.mockResolvedValue({
      accountCreated: true,
      requiresEmailConfirmation: true,
    })
    try {
      renderRegistration()

      fireEvent.change(screen.getByLabelText('Full name'), {
        target: { value: 'New User' },
      })
      fireEvent.change(screen.getByLabelText('Email address'), {
        target: { value: 'New@Example.COM' },
      })
      fireEvent.change(screen.getByLabelText('Password'), {
        target: { value: 'a secure password 123' },
      })
      fireEvent.change(screen.getByLabelText('Confirm password'), {
        target: { value: 'a secure password 123' },
      })
      fireEvent.click(screen.getByRole('button', { name: 'Create account' }))
      await act(async () => {
        await Promise.resolve()
      })
      const resendButton = screen.getByRole('button', {
        name: 'Resend confirmation email in 60s',
      })
      expect(resendButton).toBeDisabled()

      await act(async () => {
        await vi.advanceTimersByTimeAsync(60_000)
      })
      fireEvent.click(screen.getByRole('button', { name: 'Resend confirmation email' }))
      await act(async () => {
        await Promise.resolve()
      })
      expect(resendEmailConfirmation).toHaveBeenCalledWith('new@example.com')
      expect(screen.getByRole('status')).toHaveTextContent(
        'If your account is awaiting confirmation, a new email has been requested.',
      )
    } finally {
      vi.useRealTimers()
    }
  })

  it('honours the server retry delay after a throttled registration request', async () => {
    register.mockRejectedValue({
      message: 'Too many registration attempts. Try again later.',
      response: { status: 429, headers: { 'retry-after': '42' } },
    })
    renderRegistration()

    fireEvent.change(screen.getByLabelText('Full name'), {
      target: { value: 'New User' },
    })
    fireEvent.change(screen.getByLabelText('Email address'), {
      target: { value: 'new@example.com' },
    })
    fireEvent.change(screen.getByLabelText('Password'), {
      target: { value: 'a secure password 123' },
    })
    fireEvent.change(screen.getByLabelText('Confirm password'), {
      target: { value: 'a secure password 123' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Create account' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Too many registration attempts. Try again later.',
    )
    expect(screen.getByRole('button', { name: 'Try again in 42s' })).toBeDisabled()
  })

  it('uses non-enumerating guidance when Supabase returns an ambiguous no-session result', async () => {
    register.mockResolvedValue({
      accountCreated: false,
      requiresEmailConfirmation: true,
    })
    renderRegistration()

    fireEvent.change(screen.getByLabelText('Full name'), {
      target: { value: 'New User' },
    })
    fireEvent.change(screen.getByLabelText('Email address'), {
      target: { value: 'new@example.com' },
    })
    fireEvent.change(screen.getByLabelText('Password'), {
      target: { value: 'a secure password 123' },
    })
    fireEvent.change(screen.getByLabelText('Confirm password'), {
      target: { value: 'a secure password 123' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Create account' }))

    expect(await screen.findByRole('status')).toHaveTextContent(
      'If an account exists for this email, check your inbox for confirmation instructions.',
    )
    expect(screen.getByRole('link', { name: 'Forgot password?' })).toHaveAttribute(
      'href',
      '/recover-password',
    )
  })
})
