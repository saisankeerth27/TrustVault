import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { DocumentActivityHistory } from '@/components/documents/DocumentActivityHistory'
import { listDocumentActivity } from '@/services/documents'

vi.mock('@/services/documents', () => ({
  listDocumentActivity: vi.fn(),
}))

function makeEvent(id, action) {
  return {
    id,
    chain_index: Number(id),
    occurred_at: '2026-10-23T12:00:00Z',
    actor_id: 'actor-1',
    actor_name: 'Avery Editor',
    document_id: 'document-1',
    document_name: 'notes.txt',
    action,
    outcome: 'SUCCESS',
    hash_schema: 'trustvault-audit-event-v2',
    request_id: null,
    details: { resource_type: 'DOCUMENT', access_level: 'EDIT' },
  }
}

function payload(items, overrides = {}) {
  return {
    items,
    total: items.length,
    page: 1,
    page_size: 5,
    pages: 1,
    has_next: false,
    has_previous: false,
    ...overrides,
  }
}

describe('DocumentActivityHistory', () => {
  beforeEach(() => {
    vi.resetAllMocks()
  })

  it('requests five events per page and paginates without duplicates', async () => {
    const interaction = userEvent.setup()
    const firstPage = [
      makeEvent('6', 'DOCUMENT_METADATA_UPDATE'),
      makeEvent('5', 'DOCUMENT_PREVIEW'),
      makeEvent('4', 'DOCUMENT_DOWNLOAD'),
      makeEvent('3', 'PERMISSION_GRANT'),
      makeEvent('2', 'DOCUMENT_VERSION_CREATED'),
    ]
    const secondPage = [makeEvent('1', 'DOCUMENT_UPLOAD')]
    listDocumentActivity.mockImplementation((_documentId, params) => {
      if (params.page === 2) {
        return Promise.resolve(
          payload(secondPage, {
            total: 6,
            page: 2,
            pages: 2,
            has_previous: true,
          }),
        )
      }
      return Promise.resolve(
        payload(firstPage, {
          total: 6,
          page: 1,
          pages: 2,
          has_next: true,
        }),
      )
    })

    render(<DocumentActivityHistory documentId="document-1" />)

    expect(await screen.findByText('Document metadata updated')).toBeInTheDocument()
    expect(screen.getByText('Showing 1-5 of 6 activity events')).toBeInTheDocument()
    expect(listDocumentActivity).toHaveBeenCalledWith(
      'document-1',
      { page: 1, page_size: 5 },
      expect.any(AbortSignal),
    )

    await interaction.click(
      screen.getByRole('button', { name: 'activity events page 2' }),
    )

    await waitFor(() =>
      expect(listDocumentActivity).toHaveBeenLastCalledWith(
        'document-1',
        { page: 2, page_size: 5 },
        expect.any(AbortSignal),
      ),
    )
    expect(await screen.findByText('Document uploaded')).toBeInTheDocument()
    expect(screen.getByText('Showing 6-6 of 6 activity events')).toBeInTheDocument()
  })

  it('reloads when the parent reports a document change', async () => {
    listDocumentActivity.mockResolvedValue(
      payload([makeEvent('1', 'DOCUMENT_UPLOAD')]),
    )
    const { rerender } = render(
      <DocumentActivityHistory documentId="document-1" refreshKey={0} />,
    )

    expect(await screen.findByText('Document uploaded')).toBeInTheDocument()
    expect(listDocumentActivity).toHaveBeenCalledTimes(1)

    rerender(
      <DocumentActivityHistory documentId="document-1" refreshKey={1} />,
    )

    await waitFor(() => expect(listDocumentActivity).toHaveBeenCalledTimes(2))
  })
})
