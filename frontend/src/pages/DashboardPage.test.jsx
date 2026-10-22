import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AuthContext } from '@/auth/useAuth'
import { DashboardPage } from '@/pages/DashboardPage'
import { listDocuments, listSharedDocuments } from '@/services/documents'

vi.mock('@/services/documents', () => ({
  listDocuments: vi.fn(),
  listSharedDocuments: vi.fn(),
}))

const user = {
  id: '11111111-1111-4111-8111-111111111111',
  name: 'Morgan Owner',
  email: 'morgan@example.com',
  role: 'USER',
  status: 'ACTIVE',
  created_at: '2026-10-21T12:00:00Z',
}

const recentDocument = {
  id: '22222222-2222-4222-8222-222222222222',
  owner_id: user.id,
  owner_name: user.name,
  name: 'Quarterly report',
  category: 'Finance',
  description: null,
  mime_type: 'application/pdf',
  file_size: 2048,
  checksum: 'a'.repeat(64),
  access_level: 'OWNER',
  created_at: '2026-10-20T12:00:00Z',
  updated_at: '2026-10-21T12:00:00Z',
}

function summary(items, total) {
  return {
    items,
    total,
    page: 1,
    page_size: 4,
    pages: total > 0 ? 1 : 0,
    has_next: false,
    has_previous: false,
  }
}

function renderDashboard() {
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
      <MemoryRouter>
        <DashboardPage />
      </MemoryRouter>
    </AuthContext.Provider>,
  )
}

describe('DashboardPage', () => {
  beforeEach(() => {
    vi.resetAllMocks()

    listDocuments.mockImplementation((params) => {
      if (params.owner_id) {
        return Promise.resolve(summary([], 2))
      }
      return Promise.resolve(summary([recentDocument], 5))
    })
    listSharedDocuments.mockResolvedValue(summary([], 1))
  })

  it('renders counts and recent documents from the authenticated API', async () => {
    renderDashboard()

    expect(await screen.findByText('Quarterly report')).toBeInTheDocument()

    const summaryRegion = screen.getByRole('region', { name: 'Document summary' })
    expect(within(summaryRegion).getByText('Accessible documents')).toBeInTheDocument()
    expect(within(summaryRegion).getByText('5')).toBeInTheDocument()
    expect(within(summaryRegion).getByText('Shared with me')).toBeInTheDocument()
    expect(within(summaryRegion).getByText('1')).toBeInTheDocument()
    expect(within(summaryRegion).getByText('Owned by me')).toBeInTheDocument()
    expect(within(summaryRegion).getByText('2')).toBeInTheDocument()
    expect(listDocuments).toHaveBeenCalledWith(
      expect.objectContaining({ owner_id: user.id }),
      expect.any(AbortSignal),
    )
  })

  it('surfaces API failures and retries without a page reload', async () => {
    const interaction = userEvent.setup()
    listDocuments.mockRejectedValue(new Error('Document service unavailable'))

    renderDashboard()

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Document service unavailable',
    )

    listDocuments.mockImplementation((params) => {
      if (params.owner_id) {
        return Promise.resolve(summary([], 2))
      }
      return Promise.resolve(summary([recentDocument], 5))
    })

    await interaction.click(screen.getByRole('button', { name: 'Retry' }))

    expect(await screen.findByText('Quarterly report')).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
})
