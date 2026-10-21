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
  it('provides the validated upload form to document managers', () => {
    renderUploadPage('DOCUMENT_OWNER')

    expect(
      screen.getByRole('heading', { level: 1, name: 'Upload a document' }),
    ).toBeInTheDocument()
    expect(screen.getByLabelText('Document file')).toBeInTheDocument()
    expect(screen.getByLabelText('Category')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Upload document' })).toBeInTheDocument()
  })

  it('denies the upload route to viewers', () => {
    renderUploadPage('VIEWER')

    expect(screen.getByRole('heading', { name: 'Access denied' })).toBeInTheDocument()
    expect(screen.queryByLabelText('Document file')).not.toBeInTheDocument()
  })
})
