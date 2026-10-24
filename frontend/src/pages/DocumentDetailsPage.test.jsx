import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AuthContext } from '@/auth/useAuth'
import { DocumentDetailsPage } from '@/pages/DocumentDetailsPage'
import {
  createDocumentVersion,
  deleteDocumentVersion,
  getDocument,
  listDocumentActivity,
  listDocumentVersions,
  previewDocument,
  updateDocumentTextContent,
} from '@/services/documents'

vi.mock('@/services/documents', () => ({
  createDocumentVersion: vi.fn(),
  deleteDocument: vi.fn(),
  deleteDocumentVersion: vi.fn(),
  downloadDocument: vi.fn(),
  downloadDocumentVersion: vi.fn(),
  getDocument: vi.fn(),
  listDocumentActivity: vi.fn(),
  listDocumentVersions: vi.fn(),
  previewDocument: vi.fn(),
  updateDocumentTextContent: vi.fn(),
}))

vi.mock('docx-preview', () => ({
  renderAsync: vi.fn().mockResolvedValue(undefined),
}))

vi.mock('@/lib/docx', () => ({
  DOCX_MIME:
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  buildDocxBlob: vi.fn(),
  extractDocxHtml: vi.fn().mockResolvedValue({
    html: '<h1>Quarterly report</h1><p>Report body</p>',
    messages: [],
  }),
}))

const owner = {
  id: '11111111-1111-4111-8111-111111111111',
  name: 'Avery Owner',
  email: 'avery@example.com',
  role: 'USER',
  status: 'ACTIVE',
}

const textDocument = {
  id: '22222222-2222-4222-8222-222222222222',
  owner_id: owner.id,
  owner_name: owner.name,
  name: 'notes.txt',
  category: 'General',
  description: 'Shared notes',
  mime_type: 'text/plain',
  file_size: 15,
  checksum: 'b'.repeat(64),
  access_level: 'EDIT',
  created_at: '2026-10-20T12:00:00Z',
  updated_at: '2026-10-20T12:00:00Z',
}

function makeVersion(number, current = false) {
  return {
    id: `version-${number}`,
    document_id: textDocument.id,
    version_number: number,
    original_filename: 'notes.txt',
    mime_type: 'text/plain',
    file_size: 15,
    checksum: `${number}`.repeat(64).slice(0, 64),
    uploaded_by: owner.id,
    uploader_name: owner.name,
    change_summary: number === 1 ? 'Initial upload' : 'Clarified terms',
    is_current: current,
    created_at: `2026-10-2${number}T12:00:00Z`,
  }
}

function versionPayload(items, overrides = {}) {
  const current = items.find((version) => version.is_current) ?? null
  return {
    items,
    total: items.length,
    total_size: items.reduce((sum, version) => sum + version.file_size, 0),
    current_version: current,
    current_version_number: current?.version_number ?? null,
    page: 1,
    page_size: 5,
    pages: 1,
    has_next: false,
    has_previous: false,
    ...overrides,
  }
}

function renderPage(record = textDocument) {
  return render(
    <AuthContext.Provider
      value={{
        status: 'authenticated',
        user: owner,
        login: vi.fn(),
        register: vi.fn(),
        logout: vi.fn(),
      }}
    >
      <MemoryRouter initialEntries={[`/documents/${record.id}`]}>
        <Routes>
          <Route path="/documents/:documentId" element={<DocumentDetailsPage />} />
        </Routes>
      </MemoryRouter>
    </AuthContext.Provider>,
  )
}

describe('DocumentDetailsPage content workflows', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    getDocument.mockResolvedValue(textDocument)
    listDocumentVersions.mockResolvedValue(versionPayload([makeVersion(1, true)]))
    listDocumentActivity.mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      page_size: 5,
      pages: 0,
      has_next: false,
      has_previous: false,
    })
    previewDocument.mockResolvedValue({
      blob: new Blob(['Initial notes\n'], { type: 'text/plain' }),
      contentType: 'text/plain',
    })
    URL.createObjectURL = vi.fn(() => 'blob:preview')
    URL.revokeObjectURL = vi.fn()
  })

  it('shows a secure preview and version history to READ-only recipients', async () => {
    const readDocument = { ...textDocument, access_level: 'READ' }
    getDocument.mockResolvedValue(readDocument)
    renderPage()

    expect(await screen.findByText('Initial notes')).toBeInTheDocument()
    expect(screen.getByText('Secure content preview')).toBeInTheDocument()
    expect(screen.getByText('Document metadata')).toBeInTheDocument()
    expect(screen.queryByText('Your access')).toBeNull()
    expect(screen.getByText('Version history')).toBeInTheDocument()
    expect(screen.getByText('Initial upload')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Edit metadata' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Edit text' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'New version' })).toBeNull()
    expect(listDocumentVersions).toHaveBeenCalledWith(
      textDocument.id,
      { page: 1, page_size: 5 },
      expect.any(AbortSignal),
    )
  })

  it('saves edited plain-text content as a new version', async () => {
    const interaction = userEvent.setup()
    const newVersion = makeVersion(2, true)
    listDocumentVersions
      .mockReset()
      .mockResolvedValueOnce(versionPayload([makeVersion(1, true)]))
      .mockResolvedValueOnce(
        versionPayload([newVersion, makeVersion(1, false)]),
      )
    updateDocumentTextContent.mockResolvedValue({
      document: {
        ...textDocument,
        checksum: 'c'.repeat(64),
        file_size: 30,
      },
      version: newVersion,
    })
    renderPage()

    const editButton = await screen.findByRole('button', { name: 'Edit text' })
    await waitFor(() => expect(editButton).toBeEnabled())
    await interaction.click(editButton)

    const editor = await screen.findByLabelText('File content')
    expect(editor).toHaveValue('Initial notes\n')
    await interaction.clear(editor)
    await interaction.type(editor, 'Updated notes')
    await interaction.click(screen.getByRole('button', { name: 'Save new version' }))

    expect(updateDocumentTextContent).toHaveBeenCalledWith(
      textDocument.id,
      'Updated notes',
      1,
      '',
    )
    expect(await screen.findByText('Version 2 created.')).toBeInTheDocument()
    expect(screen.getAllByText('Version 2').length).toBeGreaterThan(0)
  })

  it('uploads a revised file with optimistic version protection', async () => {
    const interaction = userEvent.setup()
    const newVersion = makeVersion(2, true)
    createDocumentVersion.mockResolvedValue({
      document: {
        ...textDocument,
        checksum: 'd'.repeat(64),
        file_size: 21,
      },
      version: newVersion,
    })
    renderPage()

    const replaceButton = await screen.findByRole('button', {
      name: 'New version',
    })
    await waitFor(() => expect(replaceButton).toBeEnabled())
    await interaction.click(replaceButton)

    const fileInput = screen.getByLabelText('Revised file')
    const revisedFile = new File(['Revised notes\n'], 'revised.txt', {
      type: 'text/plain',
    })
    await interaction.upload(fileInput, revisedFile)
    await interaction.type(
      screen.getByLabelText(/Change summary/),
      'Clarified terms',
    )
    await interaction.click(
      screen.getByRole('button', { name: 'Create new version' }),
    )

    expect(createDocumentVersion).toHaveBeenCalledWith(
      textDocument.id,
      revisedFile,
      1,
      'Clarified terms',
      expect.any(Function),
    )
    expect(await screen.findByText('Version 2 created.')).toBeInTheDocument()
  })

  it('allows EDIT recipient to see Edit PDF button for PDF document', async () => {
    const pdfDocument = {
      ...textDocument,
      name: 'agreement.pdf',
      mime_type: 'application/pdf',
      access_level: 'EDIT',
    }
    getDocument.mockResolvedValue(pdfDocument)
    render(
      <AuthContext.Provider
        value={{
          status: 'authenticated',
          user: owner,
          login: vi.fn(),
          register: vi.fn(),
          logout: vi.fn(),
        }}
      >
        <MemoryRouter initialEntries={[`/documents/${pdfDocument.id}`]}>
          <Routes>
            <Route path="/documents/:documentId" element={<DocumentDetailsPage />} />
          </Routes>
        </MemoryRouter>
      </AuthContext.Provider>,
    )

    expect(await screen.findByRole('button', { name: 'Edit PDF' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Edit text' })).toBeNull()
  })

  it('shows read-only metadata without an Edit metadata action for owners', async () => {
    getDocument.mockResolvedValue({ ...textDocument, access_level: 'OWNER' })
    renderPage()

    expect(await screen.findByText('Shared notes')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Edit metadata' })).toBeNull()
    expect(screen.queryByRole('heading', { name: 'Edit metadata' })).toBeNull()
  })

  it('paginates version history five at a time', async () => {
    const interaction = userEvent.setup()
    getDocument.mockResolvedValue({ ...textDocument, access_level: 'OWNER' })
    const firstPageVersions = [7, 6, 5, 4, 3].map((number) =>
      makeVersion(number, number === 7),
    )
    const secondPageVersions = [makeVersion(2, false), makeVersion(1, false)]
    listDocumentVersions.mockImplementation((_documentId, params) => {
      if (params.page === 2) {
        return Promise.resolve(
          versionPayload(secondPageVersions, {
            total: 7,
            page: 2,
            pages: 2,
            has_next: false,
            has_previous: true,
            current_version: makeVersion(7, true),
            current_version_number: 7,
          }),
        )
      }
      return Promise.resolve(
        versionPayload(firstPageVersions, {
          total: 7,
          page: 1,
          pages: 2,
          has_next: true,
          has_previous: false,
        }),
      )
    })

    renderPage()

    expect((await screen.findAllByText('Version 7')).length).toBeGreaterThan(0)
    expect(screen.getByText('Showing 1-5 of 7 versions')).toBeInTheDocument()
    await interaction.click(
      screen.getByRole('button', { name: 'versions page 2' }),
    )

    await waitFor(() =>
      expect(listDocumentVersions).toHaveBeenLastCalledWith(
        textDocument.id,
        { page: 2, page_size: 5 },
        expect.any(AbortSignal),
      ),
    )
    expect((await screen.findAllByText('Version 2')).length).toBeGreaterThan(0)
    expect(screen.getByText('Showing 6-7 of 7 versions')).toBeInTheDocument()
  })

  it('deletes the current version only after confirming rollback', async () => {
    const interaction = userEvent.setup()
    getDocument.mockResolvedValue({ ...textDocument, access_level: 'OWNER' })
    const versionThree = makeVersion(3, true)
    const versionTwo = makeVersion(2, false)
    const versionOne = makeVersion(1, false)
    listDocumentVersions
      .mockReset()
      .mockResolvedValueOnce(
        versionPayload([versionThree, versionTwo, versionOne], {
          total: 3,
          pages: 1,
          current_version_number: 3,
        }),
      )
      .mockResolvedValueOnce(
        versionPayload(
          [
            { ...versionTwo, is_current: true },
            versionOne,
          ],
          {
            total: 2,
            pages: 1,
            current_version_number: 2,
          },
        ),
      )
    deleteDocumentVersion.mockResolvedValue({
      document: {
        ...textDocument,
        access_level: 'OWNER',
        checksum: versionTwo.checksum,
        file_size: 30,
      },
      current_version: { ...versionTwo, is_current: true },
      deleted_version_number: 3,
      deleted_file_size: versionThree.file_size,
      retained_total_size: 30,
      storage_deleted: true,
      rolled_back: true,
    })

    renderPage()

    await interaction.click(
      await screen.findByRole('button', { name: 'Delete version 3' }),
    )
    expect(
      screen.getByText(/rolls the document back to Version 2/i),
    ).toBeInTheDocument()
    await interaction.click(
      screen.getByRole('button', { name: 'Confirm deletion' }),
    )

    await waitFor(() =>
      expect(deleteDocumentVersion).toHaveBeenCalledWith(
        textDocument.id,
        3,
      ),
    )
    expect(
      await screen.findByText(
        'Version 3 deleted. The document rolled back to Version 2.',
      ),
    ).toBeInTheDocument()
    await waitFor(() =>
      expect(listDocumentVersions).toHaveBeenCalledTimes(2),
    )
    await waitFor(() =>
      expect(listDocumentActivity).toHaveBeenCalledTimes(2),
    )
  })

  it('blocks a stale text editor until it is reopened', async () => {
    const interaction = userEvent.setup()
    updateDocumentTextContent.mockRejectedValue({
      response: {
        status: 409,
        data: {
          error: {
            message: 'The document has changed since it was loaded.',
          },
        },
      },
    })
    renderPage()

    await interaction.click(
      await screen.findByRole('button', { name: 'Edit text' }),
    )
    const editor = await screen.findByLabelText('File content')
    await interaction.clear(editor)
    await interaction.type(editor, 'Conflicting update')
    await interaction.click(
      screen.getByRole('button', { name: 'Save new version' }),
    )

    expect(
      await screen.findByText(/Close this editor and reopen it/i),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: 'Save new version' }),
    ).toBeDisabled()
  })

  it('prevents READ-only recipient from seeing Edit PDF button for PDF document', async () => {
    const pdfDocument = {
      ...textDocument,
      name: 'agreement.pdf',
      mime_type: 'application/pdf',
      access_level: 'READ',
    }
    getDocument.mockResolvedValue(pdfDocument)
    render(
      <AuthContext.Provider
        value={{
          status: 'authenticated',
          user: owner,
          login: vi.fn(),
          register: vi.fn(),
          logout: vi.fn(),
        }}
      >
        <MemoryRouter initialEntries={[`/documents/${pdfDocument.id}`]}>
          <Routes>
            <Route path="/documents/:documentId" element={<DocumentDetailsPage />} />
          </Routes>
        </MemoryRouter>
      </AuthContext.Provider>,
    )

    expect(await screen.findByText('agreement.pdf')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Edit PDF' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Edit text' })).toBeNull()
  })

  it('lets an EDIT recipient open the DOCX editor', async () => {
    const docxDocument = {
      ...textDocument,
      name: 'report.docx',
      mime_type:
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
      access_level: 'EDIT',
    }
    getDocument.mockResolvedValue(docxDocument)
    renderPage(docxDocument)

    const editButton = await screen.findByRole('button', {
      name: 'Edit document',
    })
    expect(screen.queryByRole('button', { name: 'Edit text' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Edit PDF' })).toBeNull()
    await waitFor(() => expect(editButton).toBeEnabled())

    fireEvent.click(editButton)

    expect(await screen.findByText('Edit document content')).toBeInTheDocument()
    expect(
      await screen.findByRole('textbox', { name: 'Document content' }),
    ).toBeInTheDocument()
  })

  it('hides DOCX editing from READ-only recipients', async () => {
    const docxDocument = {
      ...textDocument,
      name: 'report.docx',
      mime_type:
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
      access_level: 'READ',
    }
    getDocument.mockResolvedValue(docxDocument)
    renderPage(docxDocument)

    expect(await screen.findByText('report.docx')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Edit document' })).toBeNull()
  })

  it('shows the image editor action only for EDIT recipients', async () => {
    const imageDocument = {
      ...textDocument,
      name: 'diagram.png',
      mime_type: 'image/png',
      access_level: 'EDIT',
    }
    getDocument.mockResolvedValue(imageDocument)
    renderPage(imageDocument)

    expect(await screen.findByRole('button', { name: 'Edit image' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Edit text' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Edit document' })).toBeNull()
  })

  it('hides image editing from READ-only recipients', async () => {
    const imageDocument = {
      ...textDocument,
      name: 'diagram.png',
      mime_type: 'image/png',
      access_level: 'READ',
    }
    getDocument.mockResolvedValue(imageDocument)
    renderPage(imageDocument)

    expect(await screen.findByText('diagram.png')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Edit image' })).toBeNull()
  })
})
