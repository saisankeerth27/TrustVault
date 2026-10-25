import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AuthContext } from '@/auth/useAuth'
import { AdminPage } from '@/pages/AdminPage'
import {
  deleteAdminUser,
  getAdminSummary,
  listAdminUsers,
  updateAdminUserStatus,
} from '@/services/admin'

vi.mock('@/services/admin', () => ({
  deleteAdminUser: vi.fn(),
  getAdminSummary: vi.fn(),
  listAdminUsers: vi.fn(),
  updateAdminUserStatus: vi.fn(),
  updateAdminUserRole: vi.fn(),
}))

const administrator = {
  id: '11111111-1111-4111-8111-111111111111',
  name: 'Avery Admin',
  email: 'avery@example.com',
  role: 'ADMINISTRATOR',
  status: 'ACTIVE',
  created_at: '2026-10-20T12:00:00Z',
}

const account = {
  id: '22222222-2222-4222-8222-222222222222',
  name: 'Morgan User',
  email: 'morgan@example.com',
  role: 'USER',
  status: 'ACTIVE',
  document_count: 3,
  last_login_at: '2026-10-21T12:00:00Z',
  created_at: '2026-10-20T12:00:00Z',
}

const summary = {
  total_users: 2,
  active_users: 2,
  disabled_users: 0,
  administrators: 1,
  normal_users: 1,
  active_documents: 3,
  deleted_documents: 0,
  active_grants: 1,
}

function renderAdminPage() {
  return render(
    <AuthContext.Provider
      value={{
        status: 'authenticated',
        user: administrator,
        login: vi.fn(),
        register: vi.fn(),
        logout: vi.fn(),
      }}
    >
      <MemoryRouter>
        <AdminPage />
      </MemoryRouter>
    </AuthContext.Provider>,
  )
}

describe('AdminPage', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    getAdminSummary.mockResolvedValue(summary)
    listAdminUsers.mockResolvedValue({
      items: [administrator, account],
      total: 2,
      page: 1,
      page_size: 25,
      pages: 1,
      has_next: false,
      has_previous: false,
    })
    updateAdminUserStatus.mockResolvedValue({
      user: { ...account, status: 'DISABLED' },
    })
  })

  it('renders account oversight and protects the current account', async () => {
    renderAdminPage()

    expect(await screen.findByText('Morgan User')).toBeInTheDocument()

    const summaryRegion = screen.getByRole('region', { name: 'System summary' })
    expect(within(summaryRegion).getByText('2')).toBeInTheDocument()
    expect(within(summaryRegion).getByText('Active documents')).toBeInTheDocument()

    const disableButtons = screen.getAllByRole('button', { name: 'Disable' })
    expect(disableButtons).toHaveLength(2)
    expect(disableButtons[0]).toBeDisabled()
    expect(disableButtons[1]).toBeEnabled()

    const deleteButtons = screen.getAllByRole('button', { name: 'Delete' })
    expect(deleteButtons).toHaveLength(2)
    expect(deleteButtons[0]).toBeDisabled()
    expect(deleteButtons[1]).toBeEnabled()
    expect(screen.getByLabelText('Role for Avery Admin')).toBeDisabled()
    expect(screen.getByLabelText('Role for Morgan User')).toBeEnabled()
    expect(screen.getByText(account.email)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: `Copy account ID for ${account.id}` })).toBeInTheDocument()
    expect(screen.getAllByText('Last login').length).toBeGreaterThan(0)
    expect(screen.getByText('Document oversight')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Review document metadata' })).toHaveAttribute(
      'href',
      '/documents',
    )
    expect(screen.getByRole('link', { name: 'Open audit trail' })).toHaveAttribute(
      'href',
      '/admin/audit',
    )
  })

  it('copies an account ID and confirms the action', async () => {
    const interaction = userEvent.setup()
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText },
    })
    renderAdminPage()

    await screen.findByText('Morgan User')
    await interaction.click(
      screen.getByRole('button', { name: `Copy account ID for ${account.id}` }),
    )
    expect(writeText).toHaveBeenCalledWith(account.id)
    expect(await screen.findByRole('status')).toHaveTextContent('Copied')
  })

  it('disables an account through the admin API', async () => {
    const interaction = userEvent.setup()
    renderAdminPage()

    await screen.findByText('Morgan User')
    await interaction.click(screen.getAllByRole('button', { name: 'Disable' })[1])

    expect(updateAdminUserStatus).toHaveBeenCalledWith(account.id, 'DISABLED')
    expect(await screen.findByRole('status')).toHaveTextContent(
      'Session revocation and the audit record were applied',
    )
  })

  it('deletes an account through the admin API after confirmation', async () => {
    const interaction = userEvent.setup()
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    deleteAdminUser.mockResolvedValue({})
    renderAdminPage()

    await screen.findByText('Morgan User')
    await interaction.click(screen.getAllByRole('button', { name: 'Delete' })[1])

    expect(window.confirm).toHaveBeenCalled()
    expect(deleteAdminUser).toHaveBeenCalledWith(account.id)
    expect(await screen.findByRole('status')).toHaveTextContent('permanently deleted')
  })

  it('auto-applies search with debounce and without an Apply button', async () => {
    const interaction = userEvent.setup()
    renderAdminPage()

    await screen.findByText('Morgan User')
    expect(screen.queryByRole('button', { name: 'Apply' })).toBeNull()

    const searchInput = screen.getByLabelText('Search')
    await interaction.type(searchInput, 'Morgan')

    await waitFor(
      () => {
        expect(listAdminUsers).toHaveBeenLastCalledWith(
          expect.objectContaining({ q: 'Morgan', page: 1 }),
          expect.any(AbortSignal),
        )
      },
      { timeout: 1500 },
    )
  })

  it('immediately applies dropdown filters and resets with Clear button', async () => {
    const interaction = userEvent.setup()
    renderAdminPage()

    await screen.findByText('Morgan User')
    const statusSelect = screen.getByLabelText('Status')
    await interaction.selectOptions(statusSelect, 'DISABLED')

    await waitFor(() => {
      expect(listAdminUsers).toHaveBeenLastCalledWith(
        expect.objectContaining({ status: 'DISABLED', page: 1 }),
        expect.any(AbortSignal),
      )
    })

    const clearButton = await screen.findByRole('button', { name: /clear/i })
    await interaction.click(clearButton)

    await waitFor(() => {
      expect(listAdminUsers).toHaveBeenLastCalledWith(
        expect.objectContaining({ page: 1, page_size: 25 }),
        expect.any(AbortSignal),
      )
    })
  })
})
