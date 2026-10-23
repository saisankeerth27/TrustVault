import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import { AuthContext } from '@/auth/useAuth'
import { UploadPage } from '@/pages/UploadPage'

function renderUploadPage(role) {
  const user = {
    id: '11111111-1111-4111-8111-111111111111',
    name: 'Test User',
    email: 'test@example.com',
    role,
    status: 'ACTIVE',
    created_at: '2026-10-21T12:00:00Z',
  }

  return render(
    <AuthContext.Provider
      value={{
        status: 'authenticated',
        user,
        login: vi.fn(),
        register: vi.fn(),
        logout: vi.fn(),
      }}
    >
      <MemoryRouter initialEntries={['/upload']}>
        <Routes>
          <Route path="/upload" element={<UploadPage />} />
        </Routes>
      </MemoryRouter>
    </AuthContext.Provider>,
  )
}

describe('UploadPage', () => {
  it('provides the validated upload form to normal users', () => {
    renderUploadPage('USER')

    expect(
      screen.getByRole('heading', { level: 1, name: /upload a document/i }),
    ).toBeInTheDocument()
    expect(
      screen.getByText(/Upload your document securely and manage who can access it/i),
    ).toBeInTheDocument()
    expect(screen.getByLabelText('Document file')).toBeInTheDocument()
    expect(screen.getByLabelText('Category')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Upload document' })).toBeInTheDocument()
  })

  it('does not display Private by default helper text or redundant validation copy', () => {
    renderUploadPage('USER')

    expect(screen.queryByText(/Private by default/i)).toBeNull()
    expect(screen.queryByText(/The backend validates the file again/i)).toBeNull()
    expect(screen.queryByText(/SHA-256 checksum/i)).toBeNull()
  })
})
