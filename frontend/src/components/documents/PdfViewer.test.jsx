import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { PdfViewer } from '@/components/documents/PdfViewer'
import { getDocument, TextLayer } from 'pdfjs-dist'

vi.mock('pdfjs-dist', () => ({
  GlobalWorkerOptions: { workerSrc: '' },
  TextLayer: vi.fn().mockImplementation(() => ({
    render: vi.fn().mockResolvedValue(undefined),
  })),
  getDocument: vi.fn(),
}))

vi.mock('pdfjs-dist/build/pdf.worker.min.mjs?url', () => ({
  default: 'pdf.worker.mjs',
}))

function makeDocument(pageCount) {
  return {
    numPages: pageCount,
    getPage: vi.fn(async () => ({
      getViewport: () => ({ width: 600, height: 800 }),
      streamTextContent: () => ({}),
      render: () => ({ promise: Promise.resolve(), cancel: vi.fn() }),
    })),
  }
}

describe('PdfViewer', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({})
    getDocument.mockReturnValue({
      promise: Promise.resolve(makeDocument(3)),
      destroy: vi.fn(),
    })
  })

  it('starts at 90% zoom and keeps manual zoom and page navigation working', async () => {
    render(<PdfViewer blob={new Blob(['pdf'])} filename="report.pdf" />)

    expect(await screen.findByText('Page 1 of 3')).toBeInTheDocument()
    await waitFor(() => expect(TextLayer).toHaveBeenCalled())
    expect(
      screen.getByLabelText('Selectable text on PDF page 1'),
    ).toBeInTheDocument()
    expect(screen.getByText('90%')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Zoom in' }))
    expect(screen.getByText('110%')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Zoom out' }))
    expect(screen.getByText('90%')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Next page' }))
    await waitFor(() => expect(screen.getByText('Page 2 of 3')).toBeInTheDocument())

    fireEvent.click(screen.getByRole('button', { name: 'Previous page' }))
    await waitFor(() => expect(screen.getByText('Page 1 of 3')).toBeInTheDocument())
  })
})
