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
    fireEvent.click(screen.getByRole('button', { name: 'Send OTP' }))

    expect(
      await screen.findByRole('heading', { name: 'Verify Your Email' }),
    ).toBeInTheDocument()
    expect(requestPasswordRecovery).toHaveBeenCalledWith('person@example.com')
    expect(
      screen.getByText(
        'If an account exists for this email address, a verification code will be sent.',
      ),
    ).toBeInTheDocument()

    const codeInputs = Array.from({ length: 6 }, (_, index) =>
      screen.getByLabelText(`Verification code digit ${index + 1}`),
    )
    expect(screen.getByRole('button', { name: 'Verify OTP' })).toBeDisabled()
    fireEvent.change(codeInputs[0], { target: { value: '12a345678' } })
    expect(codeInputs.map((input) => input.value)).toEqual([
      '1',
      '2',
      '3',
      '4',
      '5',
      '6',
    ])
    expect(screen.getByRole('button', { name: 'Verify OTP' })).toBeEnabled()
    fireEvent.click(screen.getByRole('button', { name: 'Verify OTP' }))
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

  it('rejects invalid email and prevents incomplete OTP verification', async () => {
    render(
      <MemoryRouter>
        <PasswordRecoveryPage />
      </MemoryRouter>,
    )
    fireEvent.change(screen.getByLabelText('Email Address'), {
      target: { value: 'not-an-email' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Send OTP' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Enter a valid email address.',
    )
    expect(requestPasswordRecovery).not.toHaveBeenCalled()

    fireEvent.change(screen.getByLabelText('Email Address'), {
      target: { value: 'person@example.com' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Send OTP' }))
    await screen.findByRole('heading', { name: 'Verify Your Email' })
    fireEvent.change(screen.getByLabelText('Verification code digit 1'), {
      target: { value: '1' },
    })
    expect(screen.getByRole('button', { name: 'Verify OTP' })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: 'Verify OTP' }))
    expect(verifyPasswordRecovery).not.toHaveBeenCalled()
  })

  it('honours the server retry delay when Supabase throttles a code request', async () => {
    requestPasswordRecovery.mockRejectedValue(
      Object.assign(new Error('Too many requests. Try again later.'), {
        response: { status: 429, headers: { 'retry-after': '42' } },
      }),
    )
    render(
      <MemoryRouter>
        <PasswordRecoveryPage />
      </MemoryRouter>,
    )

    fireEvent.change(screen.getByLabelText('Email Address'), {
      target: { value: 'person@example.com' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Send OTP' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Too many requests. Try again later.',
    )
    expect(screen.getByRole('button', { name: 'Try again in 42s' })).toBeDisabled()
  })

  it('distributes pasted OTP digits and supports keyboard navigation and deletion', async () => {
    render(
      <MemoryRouter initialEntries={['/recover-password']}>
        <PasswordRecoveryPage />
      </MemoryRouter>,
    )

    fireEvent.change(screen.getByLabelText('Email Address'), {
      target: { value: 'person@example.com' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Send OTP' }))
    const firstDigit = await screen.findByLabelText('Verification code digit 1')
    const secondDigit = screen.getByLabelText('Verification code digit 2')
    const thirdDigit = screen.getByLabelText('Verification code digit 3')
    const fourthDigit = screen.getByLabelText('Verification code digit 4')
    const fifthDigit = screen.getByLabelText('Verification code digit 5')
    const sixthDigit = screen.getByLabelText('Verification code digit 6')

    firstDigit.focus()
    fireEvent.keyDown(firstDigit, { key: 'ArrowRight' })
    expect(secondDigit).toHaveFocus()
    fireEvent.keyDown(secondDigit, { key: 'ArrowLeft' })
    expect(firstDigit).toHaveFocus()
    fireEvent.paste(firstDigit, {
      clipboardData: { getData: () => '12a345678' },
    })
    expect([firstDigit, secondDigit, thirdDigit, fourthDigit, fifthDigit, sixthDigit].map(
      (input) => input.value,
    )).toEqual(['1', '2', '3', '4', '5', '6'])
    expect(sixthDigit).toHaveFocus()

    fireEvent.change(sixthDigit, { target: { value: '' } })
    fireEvent.keyDown(sixthDigit, { key: 'Backspace' })
    expect(fifthDigit).toHaveFocus()
    expect(fifthDigit).toHaveValue('')
  })
})
