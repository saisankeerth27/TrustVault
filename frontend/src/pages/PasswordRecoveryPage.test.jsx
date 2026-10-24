import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { LoginPage } from '@/pages/LoginPage'
import { PasswordRecoveryPage } from '@/pages/PasswordRecoveryPage'
import {
  requestPasswordRecovery,
  updatePasswordRecovery,
  verifyPasswordRecovery,
} from '@/services/auth'

vi.mock('@/services/auth', () => ({
  requestPasswordRecovery: vi.fn(),
  updatePasswordRecovery: vi.fn(),
  verifyPasswordRecovery: vi.fn(),
}))

vi.mock('@/auth/useAuth', () => ({
  useAuth: () => ({
    status: 'unauthenticated',
    login: vi.fn(),
  }),
}))

describe('PasswordRecoveryPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    requestPasswordRecovery.mockResolvedValue({
      message:
        'If an account exists for this email address, a verification code will be sent.',
    })
    verifyPasswordRecovery.mockResolvedValue({})
    updatePasswordRecovery.mockResolvedValue({})
  })

  it('requests a generic code, verifies six digits, and updates matching passwords', async () => {
    render(
      <MemoryRouter initialEntries={['/recover-password']}>
        <Routes>
          <Route path="/recover-password" element={<PasswordRecoveryPage />} />
          <Route path="/login" element={<LoginPage />} />
        </Routes>
      </MemoryRouter>,
    )

    fireEvent.change(screen.getByLabelText('Email Address'), {
      target: { value: '  Person@Example.COM ' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Send Verification Code' }))

    expect(
      await screen.findByRole('heading', { name: 'Verify Your Email' }),
    ).toBeInTheDocument()
    expect(requestPasswordRecovery).toHaveBeenCalledWith('person@example.com')
    expect(
      screen.getByText(
        'If an account exists for this email address, a verification code will be sent.',
      ),
    ).toBeInTheDocument()

    const codeInput = screen.getByLabelText('Six-digit verification code')
    fireEvent.change(codeInput, { target: { value: '12a345678' } })
    expect(codeInput).toHaveValue('123456')
    fireEvent.click(screen.getByRole('button', { name: 'Verify Code' }))
    expect(
      await screen.findByRole('heading', { name: 'Create a New Password' }),
    ).toBeInTheDocument()
    expect(verifyPasswordRecovery).toHaveBeenCalledWith(
      'person@example.com',
      '123456',
    )

    fireEvent.change(screen.getByLabelText('New Password'), {
      target: { value: 'New secure password 123!' },
    })
    fireEvent.change(screen.getByLabelText('Confirm New Password'), {
      target: { value: 'Different secure password' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Update Password' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Passwords do not match.',
    )
    expect(updatePasswordRecovery).not.toHaveBeenCalled()

    fireEvent.change(screen.getByLabelText('Confirm New Password'), {
      target: { value: 'New secure password 123!' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Update Password' }))
    await waitFor(() => expect(updatePasswordRecovery).toHaveBeenCalledOnce())
    expect(updatePasswordRecovery).toHaveBeenCalledWith('New secure password 123!')
    expect(
      await screen.findByRole('heading', { name: 'Sign in' }),
    ).toBeInTheDocument()
  })

  it('rejects invalid email and invalid code without contacting Supabase', async () => {
    render(
      <MemoryRouter>
        <PasswordRecoveryPage />
      </MemoryRouter>,
    )
    fireEvent.change(screen.getByLabelText('Email Address'), {
      target: { value: 'not-an-email' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Send Verification Code' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Enter a valid email address.',
    )
    expect(requestPasswordRecovery).not.toHaveBeenCalled()

    fireEvent.change(screen.getByLabelText('Email Address'), {
      target: { value: 'person@example.com' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Send Verification Code' }))
    await screen.findByRole('heading', { name: 'Verify Your Email' })
    fireEvent.change(screen.getByLabelText('Six-digit verification code'), {
      target: { value: '123' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Verify Code' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Enter the six-digit verification code.',
    )
    expect(verifyPasswordRecovery).not.toHaveBeenCalled()
  })
})
