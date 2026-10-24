import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { AuditEventDetails } from '@/components/AuditEventDetails'
import { auditEventSummary, auditFieldLabel } from '@/lib/audit'

const details = {
  actor_name: 'Avery Admin',
  changed_fields: ['name', 'description'],
  change_summary: '<img src=x onerror=alert(1)>',
  file_size: 2048,
  mime_type: 'application/pdf',
  previous_version_number: 1,
  resource_type: 'DOCUMENT',
  source: 'UPLOAD',
  version_number: 2,
  metadata: {
    recipient_id: '11111111-1111-4111-8111-111111111111',
  },
}

describe('AuditEventDetails', () => {
  it('renders structured, readable event metadata without HTML injection', async () => {
    const interaction = userEvent.setup()
    const { container } = render(<AuditEventDetails details={details} />)

    await interaction.click(screen.getByText('View metadata'))

    expect(
      screen.getByText('Version 2 replaced version 1'),
    ).toBeInTheDocument()
    expect(screen.getByText('Version')).toBeInTheDocument()
    expect(screen.getByText('File size')).toBeInTheDocument()
    expect(screen.getByText('2.0 KB (2,048 bytes)')).toBeInTheDocument()
    expect(screen.getByText('Changed fields')).toBeInTheDocument()
    expect(screen.getByText('Changed name, description')).toBeInTheDocument()
    expect(screen.getByText('description')).toBeInTheDocument()
    expect(screen.getByText('Recipient ID')).toBeInTheDocument()
    expect(
      screen.getByText('11111111-1111-4111-8111-111111111111'),
    ).toBeInTheDocument()
    expect(
      screen.getAllByText('<img src=x onerror=alert(1)>').length,
    ).toBeGreaterThan(0)
    expect(container.querySelector('img')).toBeNull()
    expect(screen.getByText('Raw JSON')).toBeInTheDocument()
  })

  it('formats labels and summaries for compact audit rows', () => {
    expect(auditFieldLabel('previous_version_number')).toBe('Previous version')
    expect(auditFieldLabel('unmapped_field')).toBe('Unmapped Field')
    expect(
      auditEventSummary({
        permission: 'READ',
        reason: 'insufficient_access',
        changed_fields: ['category'],
      }),
    ).toEqual([
      'Changed category',
      'Permission: read',
      'Reason: insufficient access',
    ])
  })

  it('shows a single actor user ID instead of duplicate actor IDs', async () => {
    const interaction = userEvent.setup()
    render(
      <AuditEventDetails
        event={{
          id: 'event-123',
          actor_id: 'actor-uuid',
          details: { actor_user_id: 'actor-uuid' },
        }}
      />,
    )

    await interaction.click(screen.getByText('View metadata'))
    expect(screen.getByText('Actor user ID')).toBeInTheDocument()
    expect(screen.queryByText('Actor ID')).not.toBeInTheDocument()
    expect(screen.getAllByText('actor-uuid')).toHaveLength(1)
  })

  it('shows dedicated event IDs and request ID in details, not as table fields', async () => {
    const interaction = userEvent.setup()
    render(
      <AuditEventDetails
        event={{
          id: 'event-123',
          chain_index: 17,
          actor_id: 'actor-uuid',
          target_user_id: 'target-uuid',
          document_id: 'document-uuid',
          request_id: 'correlation-token-123',
          details: {},
        }}
      />,
    )

    await interaction.click(screen.getByText('View metadata'))
    expect(screen.getByText('Audit event ID')).toBeInTheDocument()
    expect(screen.getByText('Audit sequence')).toBeInTheDocument()
    expect(screen.getByText('Actor user ID')).toBeInTheDocument()
    expect(screen.getByText('actor-uuid')).toBeInTheDocument()
    expect(screen.getByText('Document ID')).toBeInTheDocument()
    expect(screen.getByText('Request ID / correlation ID')).toBeInTheDocument()
    expect(screen.getByText('document-uuid')).toBeInTheDocument()
    expect(screen.getByText('correlation-token-123')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Copy Document ID' })).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: 'Copy Request ID / correlation ID' }),
    ).toBeInTheDocument()
  })
})
