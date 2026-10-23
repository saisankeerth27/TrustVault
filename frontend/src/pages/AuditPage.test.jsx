import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AuthContext } from '@/auth/useAuth'
import { AuditPage } from '@/pages/AuditPage'
import { getAuditIntegrity, listAuditEvents } from '@/services/audit'

vi.mock('@/services/audit', () => ({
  getAuditIntegrity: vi.fn(),
  listAuditEvents: vi.fn(),
}))

const administrator = {
  id: '11111111-1111-4111-8111-111111111111',
  name: 'Avery Admin',
  email: 'avery@example.com',
  role: 'ADMINISTRATOR',
  status: 'ACTIVE',
}

const result = {
  items: [],
  total: 0,
  page: 1,
  page_size: 15,
  pages: 0,
  has_next: false,
  has_previous: false,
}

function renderAuditPage() {
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
        <AuditPage />
      </MemoryRouter>
    </AuthContext.Provider>,
  )
}

describe('AuditPage filters', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    listAuditEvents.mockResolvedValue(result)
    getAuditIntegrity.mockResolvedValue({
      status: 'CHAIN_VALID_CHECKPOINT_MISSING',
      verified_at: '2026-10-23T10:00:00Z',
      chain: {
        status: 'VALID',
        event_count: 0,
        last_chain_index: 0,
        last_event_hash: null,
        failure_chain_index: null,
        message: 'The audit hash chain is internally consistent.',
      },
      checkpoint: {
        status: 'UNCONFIGURED',
        last_chain_index: null,
        created_at: null,
        message: 'No external audit checkpoint signing is configured.',
      },
    })
  })

  it('applies dropdown filters without an Apply button', async () => {
    const interaction = userEvent.setup()
    renderAuditPage()

    await screen.findByText('No audit events yet')
    expect(screen.queryByRole('button', { name: /apply filters/i })).toBeNull()
    await interaction.selectOptions(screen.getByLabelText('Outcome'), 'DENIED')

    await waitFor(() => {
      expect(listAuditEvents).toHaveBeenLastCalledWith(
        { page: 1, page_size: 15, outcome: 'DENIED' },
        expect.any(AbortSignal),
      )
    })
  })

  it('debounces ID filters and applies them with selected filters', async () => {
    const interaction = userEvent.setup()
    renderAuditPage()

    await screen.findByText('No audit events yet')
    const actorId = '22222222-2222-4222-8222-222222222222'
    await interaction.type(screen.getByLabelText('Actor ID'), actorId)
    await interaction.selectOptions(screen.getByLabelText('Action'), 'LOGIN_SUCCESS')

    await waitFor(
      () => {
        expect(listAuditEvents).toHaveBeenLastCalledWith(
          {
            page: 1,
            page_size: 15,
            action: 'LOGIN_SUCCESS',
            actor_id: actorId,
          },
          expect.any(AbortSignal),
        )
      },
      { timeout: 1500 },
    )
  })

  it('shows document names in the table and technical identifiers only in metadata', async () => {
    const interaction = userEvent.setup()
    listAuditEvents.mockResolvedValueOnce({
      ...result,
      total: 1,
      pages: 1,
      items: [
        {
          id: 'event-uuid',
          chain_index: 8,
          occurred_at: '2026-10-23T10:00:00Z',
          actor_id: 'actor-uuid',
          actor_name: 'Morgan User',
          document_id: 'document-uuid',
          document_name: 'Quarterly report.pdf',
          target_user_id: 'target-uuid',
          resource_type: 'DOCUMENT',
          action: 'DOCUMENT_UPLOAD',
          outcome: 'SUCCESS',
          request_id: 'correlation-123',
          hash_schema: 'trustvault-audit-event-v2',
          details: { file_size: 2048 },
        },
      ],
    })
    renderAuditPage()

    expect(await screen.findByText('Quarterly report.pdf')).toBeInTheDocument()
    expect(screen.queryByText('document-uuid')).toBeNull()
    expect(screen.queryByText('correlation-123')).toBeNull()
    expect(screen.queryByRole('columnheader', { name: 'Request ID' })).toBeNull()
    await interaction.click(screen.getByRole('button', { name: /view metadata/i }))
    expect(screen.getAllByText('Document ID')).toHaveLength(2)
    expect(screen.getByText('Request ID / correlation ID')).toBeInTheDocument()
    expect(screen.getByText('document-uuid')).toBeInTheDocument()
    expect(screen.getByText('correlation-123')).toBeInTheDocument()
  })
})