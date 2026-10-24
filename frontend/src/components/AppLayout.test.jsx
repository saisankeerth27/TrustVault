import { render, screen, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import { AuthContext } from '@/auth/useAuth'
import { AppLayout } from '@/components/AppLayout'

const noop = vi.fn()

function renderLayout(role) {
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
        login: noop,
        register: noop,
        logout: noop,
      }}
    >
      <MemoryRouter initialEntries={['/dashboard']}>
        <Routes>
          <Route element={<AppLayout />}>
            <Route path="/dashboard" element={<h1>Dashboard content</h1>} />
          </Route>
        </Routes>
      </MemoryRouter>
    </AuthContext.Provider>,
  )
}

describe('AppLayout', () => {
  it('shows workspace and administrator navigation to administrators', () => {
    renderLayout('ADMINISTRATOR')

    expect(screen.getByRole('heading', { name: 'Dashboard content' })).toBeInTheDocument()
    expect(screen.getAllByRole('link', { name: 'Audit trail' }).length).toBeGreaterThan(0)
    expect(screen.getAllByRole('link', { name: 'System oversight' }).length).toBeGreaterThan(0)
    expect(screen.getAllByRole('link', { name: 'Upload document' }).length).toBeGreaterThan(0)
    expect(screen.getAllByRole('link', { name: 'Shared with me' }).length).toBeGreaterThan(0)
  })

  it('shows upload but hides administrator navigation from normal users', () => {
    renderLayout('USER')

    expect(screen.getAllByRole('link', { name: 'Upload document' }).length).toBeGreaterThan(0)
    expect(screen.queryByRole('link', { name: 'Audit trail' })).not.toBeInTheDocument()
    expect(screen.getAllByRole('link', { name: 'Documents' }).length).toBeGreaterThan(0)
  })

  it('keeps the footer limited to the TrustVault name', () => {
    renderLayout('USER')

    const footer = screen.getByRole('contentinfo')
    expect(within(footer).getByText('TrustVault')).toBeInTheDocument()
    expect(within(footer).queryByText(/tamper-evident document sharing/)).toBeNull()
    expect(within(footer).queryByText(/signed checkpoints/)).toBeNull()
  })
})
