import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { DocumentDocxEditor } from '@/components/documents/DocumentDocxEditor'
import { buildDocxBlob, extractDocxHtml } from '@/lib/docx'
import { createDocumentVersion } from '@/services/documents'

vi.mock('@/lib/docx', () => ({
  DOCX_MIME:
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  buildDocxBlob: vi.fn(),
  extractDocxHtml: vi.fn(),
}))

vi.mock('@/services/documents', () => ({
  createDocumentVersion: vi.fn(),
}))

const documentRecord = {
  id: '33333333-3333-4333-8333-333333333333',
  name: 'report.docx',
  mime_type:
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
}

const currentVersion = {
  version_number: 1,
  original_filename: 'report.docx',
}

function renderEditor(overrides = {}) {
  const props = {
    blob: new Blob(['docx'], { type: documentRecord.mime_type }),
    documentRecord,
    currentVersion,
    onSaved: vi.fn(),
    onConflict: vi.fn(),
    onCancel: vi.fn(),
    ...overrides,
  }
  render(<DocumentDocxEditor {...props} />)
  return props
}

describe('DocumentDocxEditor', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    extractDocxHtml.mockResolvedValue({
      html: '<h1>Quarterly report</h1><p>Original body</p>',
      messages: [],
    })
    buildDocxBlob.mockResolvedValue(
      new Blob(['docx'], { type: documentRecord.mime_type }),
    )
  })

  it('loads DOCX content and saves edits as a new version', async () => {
    const interaction = userEvent.setup()
    const result = {
      document: { ...documentRecord, file_size: 40 },
      version: { version_number: 2, original_filename: 'report.docx' },
    }
    createDocumentVersion.mockResolvedValue(result)
    const props = renderEditor()

    const editor = await screen.findByRole('textbox', {
      name: 'Document content',
    })
    await waitFor(() => expect(editor.innerHTML).toContain('Original body'))

    const saveButton = screen.getByRole('button', { name: 'Save new version' })
    expect(saveButton).toBeDisabled()

    editor.innerHTML = '<h1>Quarterly report</h1><p>Updated body</p>'
    fireEvent.input(editor)
    await interaction.type(
      screen.getByLabelText(/Change summary/),
      'Clarified results',
    )
    await waitFor(() => expect(saveButton).toBeEnabled())
    await interaction.click(saveButton)

    await waitFor(() => expect(createDocumentVersion).toHaveBeenCalledTimes(1))
    expect(buildDocxBlob).toHaveBeenCalledWith(
      expect.stringContaining('Updated body'),
      { title: 'report.docx' },
    )
    expect(createDocumentVersion).toHaveBeenCalledWith(
      documentRecord.id,
      expect.any(File),
      1,
      'Clarified results',
    )
    const savedFile = createDocumentVersion.mock.calls[0][1]
    expect(savedFile.name).toBe('report.docx')
    expect(props.onSaved).toHaveBeenCalledWith(result)
  })

  it('reports a version conflict and prevents further saving', async () => {
    const conflict = new Error('A newer version already exists.')
    conflict.response = { status: 409 }
    createDocumentVersion.mockRejectedValue(conflict)
    const props = renderEditor()

    const editor = await screen.findByRole('textbox', {
      name: 'Document content',
    })
    await waitFor(() => expect(editor.innerHTML).toContain('Original body'))
    editor.innerHTML = '<p>Conflicting edit</p>'
    fireEvent.input(editor)

    const saveButton = screen.getByRole('button', { name: 'Save new version' })
    await waitFor(() => expect(saveButton).toBeEnabled())
    fireEvent.click(saveButton)

    expect(await screen.findByRole('alert')).toHaveTextContent(
      /newer version already exists/i,
    )
    expect(props.onConflict).toHaveBeenCalledTimes(1)
    expect(saveButton).toBeDisabled()
  })

  it('cancels without saving', async () => {
    const props = renderEditor()

    await screen.findByRole('textbox', { name: 'Document content' })
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))

    expect(props.onCancel).toHaveBeenCalledTimes(1)
    expect(createDocumentVersion).not.toHaveBeenCalled()
  })
})
