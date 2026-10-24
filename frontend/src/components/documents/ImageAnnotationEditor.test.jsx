import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ImageAnnotationEditor } from '@/components/documents/ImageAnnotationEditor'
import { createDocumentVersion } from '@/services/documents'

vi.mock('@/services/documents', () => ({
  createDocumentVersion: vi.fn(),
}))

const documentRecord = {
  id: '44444444-4444-4444-8444-444444444444',
  name: 'diagram.png',
  mime_type: 'image/png',
}

const currentVersion = {
  version_number: 1,
  original_filename: 'diagram.png',
}

const context = {
  arc: vi.fn(),
  beginPath: vi.fn(),
  clearRect: vi.fn(),
  drawImage: vi.fn(),
  ellipse: vi.fn(),
  fill: vi.fn(),
  fillText: vi.fn(),
  lineTo: vi.fn(),
  moveTo: vi.fn(),
  restore: vi.fn(),
  save: vi.fn(),
  stroke: vi.fn(),
  strokeRect: vi.fn(),
}

function renderEditor(overrides = {}) {
  const props = {
    blob: new Blob(['image'], { type: 'image/png' }),
    documentRecord,
    currentVersion,
    onSaved: vi.fn(),
    onConflict: vi.fn(),
    onCancel: vi.fn(),
    ...overrides,
  }
  render(<ImageAnnotationEditor {...props} />)
  return props
}

async function waitForCanvas() {
  const canvas = await screen.findByRole('img', {
    name: /Editable image: diagram.png/,
  })
  await waitFor(() =>
    expect(screen.queryByText(/Loading image for editing/)).toBeNull(),
  )
  return canvas
}

function drawStroke(canvas) {
  fireEvent.pointerDown(canvas, { clientX: 20, clientY: 20, pointerId: 1 })
  fireEvent.pointerMove(canvas, { clientX: 140, clientY: 100, pointerId: 1 })
  fireEvent.pointerUp(canvas, { clientX: 140, clientY: 100, pointerId: 1 })
}

describe('ImageAnnotationEditor', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.stubGlobal(
      'Image',
      class MockImage {
        constructor() {
          this.naturalWidth = 800
          this.naturalHeight = 600
          this.width = 800
          this.height = 600
        }

        set src(value) {
          this._src = value
          Promise.resolve().then(() => this.onload?.())
        }

        get src() {
          return this._src
        }
      },
    )
    vi.stubGlobal('PointerEvent', MouseEvent)
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(context)
    vi.spyOn(HTMLCanvasElement.prototype, 'getBoundingClientRect').mockReturnValue({
      width: 800,
      height: 600,
      top: 0,
      left: 0,
      right: 800,
      bottom: 600,
      x: 0,
      y: 0,
    })
    vi.spyOn(HTMLCanvasElement.prototype, 'toBlob').mockImplementation(
      (callback) => callback(new Blob(['flattened'], { type: 'image/png' })),
    )
    vi.spyOn(HTMLCanvasElement.prototype, 'toDataURL').mockReturnValue(
      'data:image/png;base64,preview',
    )
    URL.createObjectURL = vi.fn(() => 'blob:image')
    URL.revokeObjectURL = vi.fn()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('draws an annotation and saves a flattened image as a new version', async () => {
    const result = {
      document: { ...documentRecord, file_size: 80 },
      version: { version_number: 2, original_filename: 'diagram.png' },
    }
    createDocumentVersion.mockResolvedValue(result)
    const props = renderEditor()

    const canvas = await waitForCanvas()
    const saveButton = screen.getByRole('button', { name: 'Save new version' })
    expect(saveButton).toBeDisabled()

    drawStroke(canvas)
    await waitFor(() => expect(saveButton).toBeEnabled())
    fireEvent.click(saveButton)

    await waitFor(() => expect(createDocumentVersion).toHaveBeenCalledTimes(1))
    expect(createDocumentVersion).toHaveBeenCalledWith(
      documentRecord.id,
      expect.any(File),
      1,
      '',
    )
    const savedFile = createDocumentVersion.mock.calls[0][1]
    expect(savedFile.name).toBe('diagram.png')
    expect(savedFile.type).toBe('image/png')
    expect(props.onSaved).toHaveBeenCalledWith(result)
  })

  it('supports undo and redo for annotations', async () => {
    const props = renderEditor()
    const canvas = await waitForCanvas()
    const saveButton = screen.getByRole('button', { name: 'Save new version' })
    const undo = screen.getByRole('button', { name: 'Undo' })
    const redo = screen.getByRole('button', { name: 'Redo' })
    expect(undo).toBeDisabled()
    expect(redo).toBeDisabled()

    drawStroke(canvas)
    await waitFor(() => expect(saveButton).toBeEnabled())

    fireEvent.click(undo)
    await waitFor(() => expect(saveButton).toBeDisabled())
    expect(redo).toBeEnabled()

    fireEvent.click(redo)
    await waitFor(() => expect(saveButton).toBeEnabled())
    expect(createDocumentVersion).not.toHaveBeenCalled()
    expect(props.onCancel).not.toHaveBeenCalled()
  })

  it('places text annotations and previews the flattened result', async () => {
    const interaction = userEvent.setup()
    const props = renderEditor()
    const canvas = await waitForCanvas()

    fireEvent.click(screen.getByRole('button', { name: 'Text' }))
    await interaction.type(screen.getByLabelText('Text to place'), 'Approved')
    fireEvent.pointerDown(canvas, { clientX: 120, clientY: 140, pointerId: 1 })
    fireEvent.pointerUp(canvas, { clientX: 120, clientY: 140, pointerId: 1 })

    const saveButton = screen.getByRole('button', { name: 'Save new version' })
    await waitFor(() => expect(saveButton).toBeEnabled())
    expect(context.fillText).toHaveBeenCalledWith('Approved', 120, 140)

    fireEvent.click(screen.getByRole('button', { name: 'Preview image' }))
    expect(
      screen.getByRole('dialog', { name: 'Image preview' }),
    ).toBeInTheDocument()
    expect(
      screen.getByAltText('Preview of the edited image'),
    ).toHaveAttribute('src', 'data:image/png;base64,preview')

    fireEvent.click(screen.getByRole('button', { name: 'Back to editing' }))
    expect(screen.queryByRole('dialog', { name: 'Image preview' })).toBeNull()
    expect(props.onSaved).not.toHaveBeenCalled()
  })

  it('cancels without saving', async () => {
    const props = renderEditor()
    const canvas = await waitForCanvas()
    drawStroke(canvas)

    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(props.onCancel).toHaveBeenCalledTimes(1)
    expect(createDocumentVersion).not.toHaveBeenCalled()
  })
})
