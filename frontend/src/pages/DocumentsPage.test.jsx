import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AuthContext } from '@/auth/useAuth'
import { DocumentsPage } from '@/pages/DocumentsPage'
import { listDocuments } from '@/services/documents'

vi.mock('@/services/documents', () => ({
  listDocuments: vi.fn(),
}))

const ownerId = '11111111-1111-4111-8111-111111111111'
const user = {
  id: ownerId,
  name: 'Avery Owner',
  email: 'avery@example.com',
  role: 'USER',
  status: 'ACTIVE',
}

function pageResult(page) {
  const start = (page - 1) * 5
  return {
    items: Array.from({ length: page === 1 ? 5 : 1 }, (_, index) => ({
      id: `document-${start + index + 1}`,
      name: `Document ${start + index + 1}.pdf`,
      owner_id: ownerId,
      owner_name: user.name,
      category: 'General',
      mime_type: 'application/pdf',
      file_size: 100,
      access_level: 'OWNER',
      updated_at: '2026-10-23T10:00:00Z',
    })),
    total: 6,
    page,
    page_size: 5,
    pages: 2,
    has_next: page === 1,
    has_previous: page > 1,
  }
}

function renderDocumentsPage(role = 'USER') {
  return render(
    <AuthContext.Provider
      value={{
        status: 'authenticated',
        user: { ...user, role },
        login: vi.fn(),
        register: vi.fn(),
        logout: vi.fn(),
      }}
    >
      <MemoryRouter>
        <DocumentsPage />
      </MemoryRouter>
    </AuthContext.Provider>,
  )
}

describe('DocumentsPage pagination', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    listDocuments.mockImplementation(({ page }) => Promise.resolve(pageResult(page)))
  })

  it('requests five documents per page and paginates without exposing owner UUIDs', async () => {
    const interaction = userEvent.setup()
    const { container } = renderDocumentsPage()

    expect(await screen.findByText('Document 1.pdf')).toBeInTheDocument()
    expect(screen.getByText('Document 5.pdf')).toBeInTheDocument()
    expect(screen.queryByText('Document 6.pdf')).toBeNull()
    expect(container.textContent).not.toContain(ownerId)
    expect(screen.queryByLabelText('Owner account ID')).toBeNull()
    expect(listDocuments).toHaveBeenCalledWith(
      expect.objectContaining({ page: 1, page_size: 5 }),
      expect.any(AbortSignal),
    )

    await interaction.click(screen.getByRole('button', { name: /next/i }))
    await waitFor(() => {
      expect(listDocuments).toHaveBeenLastCalledWith(
        expect.objectContaining({ page: 2, page_size: 5 }),
        expect.any(AbortSignal),
      )
    })
    expect(await screen.findByText('Document 6.pdf')).toBeInTheDocument()
    expect(screen.getByText('Page 2 of 2')).toBeInTheDocument()
  })

  it('does not display owner account ID filter for administrators', async () => {
    renderDocumentsPage('ADMINISTRATOR')

    expect(screen.queryByLabelText('Owner account ID')).toBeNull()
    expect(listDocuments).toHaveBeenCalledWith(
      expect.objectContaining({ page: 1, page_size: 5 }),
      expect.any(AbortSignal),
    )
  })
})