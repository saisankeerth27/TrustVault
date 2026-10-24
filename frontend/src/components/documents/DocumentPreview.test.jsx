import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { DocumentPreview } from '@/components/documents/DocumentPreview'
import { previewDocument } from '@/services/documents'
import { previewKindOf } from '@/lib/documents'
import { renderAsync } from 'docx-preview'

vi.mock('docx-preview', () => ({
  renderAsync: vi.fn(async (blob, container) => {
    container.innerHTML = ''
    for (let index = 1; index <= 10; index += 1) {
      const page = document.createElement('section')
      page.className = 'docx'
      page.textContent = `Page ${index}`
      container.appendChild(page)
    }
  }),
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

  it('renders DOCX content as paginated pages from the preview response', async () => {
    expect(previewKindOf(docxDocument)).toBe('docx')

    render(<DocumentPreview documentRecord={docxDocument} />)

    expect(await screen.findByText('Page 1 of 10')).toBeInTheDocument()
    expect(screen.getByText('report.docx')).toBeInTheDocument()
    expect(renderAsync).toHaveBeenCalledWith(
      expect.any(Blob),
      expect.any(HTMLElement),
      undefined,
      expect.objectContaining({
        breakPages: true,
        ignoreLastRenderedPageBreak: false,
      }),
    )
    expect(previewDocument).toHaveBeenCalledWith(
      docxDocument.id,
      expect.any(AbortSignal),
    )
  })
})
