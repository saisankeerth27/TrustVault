import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { PdfAnnotationEditor } from '@/components/documents/PdfAnnotationEditor'
import { createDocumentVersion } from '@/services/documents'
import { getDocument, TextLayer } from 'pdfjs-dist'
import { PDFDocument } from 'pdf-lib'

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

vi.mock('pdf-lib', () => ({
  PDFDocument: { load: vi.fn() },
  StandardFonts: { Helvetica: 'Helvetica' },
  rgb: vi.fn((red, green, blue) => ({ red, green, blue })),
}))

vi.mock('@/services/documents', () => ({
  createDocumentVersion: vi.fn(),
}))

function fakePdfPage() {
  return {
    getViewport: () => ({
      width: 600,
      height: 800,
      convertToPdfPoint: (x, y) => [x, y],
    }),
    streamTextContent: () => ({}),
    render: () => ({ promise: Promise.resolve(), cancel: vi.fn() }),
  }
}

describe('PdfAnnotationEditor', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({})
    getDocument.mockReturnValue({
      promise: Promise.resolve({
        numPages: 1,
        getPage: vi.fn().mockResolvedValue(fakePdfPage()),
      }),
      destroy: vi.fn(),
    })
    PDFDocument.load.mockResolvedValue({
      embedFont: vi.fn().mockResolvedValue('font'),
      getPages: () => [
        {
          drawRectangle: vi.fn(),
          drawText: vi.fn(),
          drawLine: vi.fn(),
        },
      ],
      save: vi.fn().mockResolvedValue(new Uint8Array([1, 2, 3])),
    })
    createDocumentVersion.mockResolvedValue({
      document: { id: 'document-1' },
      version: { version_number: 2 },
    })
  })

  it('supports PDF text selection and moving text annotations before saving a new version', async () => {
    const onSaved = vi.fn()
    render(
      <PdfAnnotationEditor
        blob={new Blob(['pdf'])}
        filename="report.pdf"
        documentRecord={{ id: 'document-1', name: 'report.pdf' }}
        currentVersion={{ version_number: 1 }}
        onSaved={onSaved}
        onConflict={vi.fn()}
        onCancel={vi.fn()}
      />,
    )

    await screen.findByText('Edit PDF — Annotations')
    await waitFor(() => expect(TextLayer).toHaveBeenCalled())
    fireEvent.click(screen.getByRole('button', { name: 'Select / move' }))

    const canvas = screen.getByRole('img', { name: /PDF page 1 of 1/ })
    Object.defineProperty(canvas, 'clientWidth', { configurable: true, value: 600 })
    Object.defineProperty(canvas, 'clientHeight', { configurable: true, value: 800 })
    fireEvent.mouseDown(canvas, { button: 0, clientX: 100, clientY: 100 })
    expect(
      screen.getByLabelText('Selectable text on PDF page 1'),
    ).toHaveStyle({ pointerEvents: 'auto' })

    fireEvent.click(screen.getByRole('button', { name: 'Text note' }))
    fireEvent.mouseDown(canvas, { button: 0, clientX: 100, clientY: 100 })
    fireEvent.change(screen.getByLabelText('Annotation text'), {
      target: { value: 'Move this note' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Add' }))

    const annotation = screen.getByRole('group', {
      name: 'Text note annotation on page 1: Move this note',
    })
    fireEvent.pointerDown(annotation, {
      button: 0,
      pointerId: 1,
      clientX: 100,
      clientY: 100,
    })
    fireEvent.pointerMove(annotation, {
      pointerId: 1,
      clientX: 140,
      clientY: 130,
    })
    fireEvent.pointerUp(annotation, { pointerId: 1, clientX: 140, clientY: 130 })

    await waitFor(() => expect(annotation.style.left).toBe('140px'))
    fireEvent.click(
      screen.getByRole('button', {
        name: 'Save annotated PDF as new version',
      }),
    )

    await waitFor(() => expect(createDocumentVersion).toHaveBeenCalledOnce())
    expect(createDocumentVersion).toHaveBeenCalledWith(
      'document-1',
      expect.any(File),
      1,
      expect.any(String),
      expect.any(Function),
    )
    expect(onSaved).toHaveBeenCalledWith({
      document: { id: 'document-1' },
      version: { version_number: 2 },
    })
  })
})
