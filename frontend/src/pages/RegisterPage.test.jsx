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
        <Route path="/verify-account" element={<VerifyDestination />} />
        <Route path="/dashboard" element={<DashboardDestination />} />
      </Routes>
    </MemoryRouter>,
  )
}

function VerifyDestination() {
  const location = useLocation()
  return (
    <>
      <h1>Verify Account</h1>
      <div data-testid="verify-email">{location.state?.email}</div>
      <div data-testid="account-created">{String(location.state?.accountCreated)}</div>
    </>
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

  it('navigates to /verify-account when confirmation is required', async () => {
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

    expect(await screen.findByRole('heading', { name: 'Verify Account' })).toBeInTheDocument()
    expect(screen.getByTestId('verify-email')).toHaveTextContent('new@example.com')
    expect(screen.getByTestId('account-created')).toHaveTextContent('true')
    expect(register).toHaveBeenCalledOnce()
  })

  it('navigates to /verify-account with accountCreated false when ambiguous no-session result is returned', async () => {
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

    expect(await screen.findByRole('heading', { name: 'Verify Account' })).toBeInTheDocument()
    expect(screen.getByTestId('verify-email')).toHaveTextContent('new@example.com')
    expect(screen.getByTestId('account-created')).toHaveTextContent('false')
  })

  it('displays an error alert when registration fails', async () => {
    register.mockRejectedValue({
      message: 'Too many registration attempts. Try again later.',
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
  })
})
