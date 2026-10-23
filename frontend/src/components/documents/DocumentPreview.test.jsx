import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { DocumentPreview } from '@/components/documents/DocumentPreview'
import { previewDocument } from '@/services/documents'
import { previewKindOf } from '@/lib/documents'

vi.mock('mammoth', () => ({
  default: {
    convertToHtml: vi.fn().mockResolvedValue({
      value: '<h1>Quarterly report</h1><p>Confidential content</p>',
    }),
  },
}))

vi.mock('@/services/documents', () => ({
  downloadDocument: vi.fn(),
  previewDocument: vi.fn(),
}))

const docxDocument = {
  id: '22222222-2222-4222-8222-222222222222',
  name: 'report.docx',
  mime_type:
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
}

describe('DocumentPreview DOCX support', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    previewDocument.mockResolvedValue({
      blob: new Blob(['docx bytes'], { type: docxDocument.mime_type }),
      contentType: docxDocument.mime_type,
    })
  })

  it('recognizes and renders DOCX content from the preview response', async () => {
    expect(previewKindOf(docxDocument)).toBe('docx')

    render(<DocumentPreview documentRecord={docxDocument} />)

    expect(await screen.findByRole('heading', { name: 'Quarterly report' }))
      .toBeInTheDocument()
    expect(screen.getByText('Confidential content')).toBeInTheDocument()
    expect(previewDocument).toHaveBeenCalledWith(
      docxDocument.id,
      expect.any(AbortSignal),
    )
  })
})