import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AuthContext } from '@/auth/useAuth'
import { DocumentDetailsPage } from '@/pages/DocumentDetailsPage'
import {
  createDocumentVersion,
  getDocument,
  listDocumentVersions,
  previewDocument,
  updateDocumentTextContent,
} from '@/services/documents'

vi.mock('@/services/documents', () => ({
  createDocumentVersion: vi.fn(),
  deleteDocument: vi.fn(),
  downloadDocument: vi.fn(),
  downloadDocumentVersion: vi.fn(),
  getDocument: vi.fn(),
  listDocumentVersions: vi.fn(),
  previewDocument: vi.fn(),
  updateDocument: vi.fn(),
  updateDocumentTextContent: vi.fn(),
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

function renderPage() {
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
      <MemoryRouter initialEntries={[`/documents/${textDocument.id}`]}>
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
    listDocumentVersions.mockResolvedValue({
      items: [makeVersion(1, true)],
      total: 1,
      current_version_number: 1,
    })
    previewDocument.mockResolvedValue({
      blob: new Blob(['Initial notes\n'], { type: 'text/plain' }),
      contentType: 'text/plain',
    })
  })

  it('shows a secure preview and version history to READ-only recipients', async () => {
    const readDocument = { ...textDocument, access_level: 'READ' }
    getDocument.mockResolvedValue(readDocument)
    renderPage()

    expect(await screen.findByText('Initial notes')).toBeInTheDocument()
    expect(screen.getByText('Secure content preview')).toBeInTheDocument()
    expect(screen.getByText('Version history')).toBeInTheDocument()
    expect(screen.getByText('Initial upload')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Edit metadata' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Edit text' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'New version' })).toBeNull()
    expect(listDocumentVersions).toHaveBeenCalledWith(
      textDocument.id,
      expect.any(AbortSignal),
    )
  })

  it('saves edited plain-text content as a new version', async () => {
    const interaction = userEvent.setup()
    const newVersion = makeVersion(2, true)
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
})
