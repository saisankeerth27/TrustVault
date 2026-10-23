import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import { AuthContext } from '@/auth/useAuth'
import { LoginPage } from '@/pages/LoginPage'

function renderLoginPage() {
  return render(
    <AuthContext.Provider
      value={{
        status: 'unauthenticated',
        user: null,
        login: vi.fn(),
        register: vi.fn(),
        logout: vi.fn(),
      }}
    >
      <MemoryRouter>
        <LoginPage />
      </MemoryRouter>
    </AuthContext.Provider>,
  )
}

describe('LoginPage copy and branding', () => {
  it('renders the required heading and supporting description', () => {
    renderLoginPage()

    expect(
      screen.getByRole('heading', { level: 1, name: 'Your Documents. Your Control.' }),
    ).toBeInTheDocument()
    expect(
      screen.getByText(
        'Securely manage your documents, share access with trusted people, and stay in control of who can view or edit your files.',
      ),
    ).toBeInTheDocument()
  })

  it('renders the four project-specific feature highlights', () => {
    renderLoginPage()

    expect(screen.getByText('Secure Document Sharing')).toBeInTheDocument()
    expect(screen.getByText('Controlled Read and Edit Access')).toBeInTheDocument()
    expect(screen.getByText('Document Version History')).toBeInTheDocument()
    expect(screen.getByText('Activity and Access Tracking')).toBeInTheDocument()
  })
})
