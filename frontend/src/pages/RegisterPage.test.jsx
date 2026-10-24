import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { LoginPage } from '@/pages/LoginPage'
import { RegisterPage } from '@/pages/RegisterPage'

const register = vi.fn()

vi.mock('@/auth/useAuth', () => ({
  useAuth: () => ({
    status: 'unauthenticated',
    register,
  }),
}))

vi.mock('@/services/api', () => ({
  getApiErrorMessage: (error) => error.message,
}))

function renderRegistration() {
  return render(
    <MemoryRouter initialEntries={['/register']}>
      <Routes>
        <Route path="/register" element={<RegisterPage />} />
        <Route path="/login" element={<LoginPage />} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('RegisterPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('redirects a successfully created account to Login exactly once', async () => {
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

    expect(await screen.findByRole('heading', { name: 'Sign in' })).toBeInTheDocument()
    expect(
      screen.getByRole('status'),
    ).toHaveTextContent('Account created successfully. Please log in.')
    expect(register).toHaveBeenCalledOnce()
    expect(register).toHaveBeenCalledWith({
      name: 'New User',
      email: 'new@example.com',
      password: 'a secure password 123',
    })
  })

  it('does not claim success or navigate when Supabase still requires confirmation', async () => {
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
    ).toHaveTextContent('Supabase still requires email confirmation.')
    expect(screen.getByRole('heading', { name: 'Create account' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Sign in' })).not.toBeInTheDocument()
    await waitFor(() => expect(register).toHaveBeenCalledOnce())
  })
})
