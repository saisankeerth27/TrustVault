import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { DocxViewer } from '@/components/documents/DocxViewer'
import { renderAsync } from 'docx-preview'

vi.mock('docx-preview', () => ({
  renderAsync: vi.fn(),
}))

function addPages(container, count) {
  container.innerHTML = ''
  for (let index = 1; index <= count; index += 1) {
    const page = document.createElement('section')
    page.className = 'docx'
    page.textContent = `Rendered page ${index}`
    page.getBoundingClientRect = () => ({
      top: (index - 1) * 800,
      bottom: index * 800,
      height: 800,
      left: 0,
      right: 600,
      width: 600,
    })
    container.appendChild(page)
  }
}

describe('DocxViewer', () => {
  beforeEach(() => {
    vi.resetAllMocks()
  })

  it('shows a page indicator for a single-page document', async () => {
    renderAsync.mockImplementation(async (blob, container) => addPages(container, 1))

    render(<DocxViewer blob={new Blob(['docx'])} filename="single.docx" />)

    expect(await screen.findByText('Page 1 of 1')).toBeInTheDocument()
    expect(screen.getByText('single.docx')).toBeInTheDocument()
    expect(
      screen.getByText(/no page-break markers/i),
    ).toBeInTheDocument()
  })

  it('paginates a large document and navigates between pages', async () => {
    renderAsync.mockImplementation(async (blob, container) => addPages(container, 12))

    render(<DocxViewer blob={new Blob(['docx'])} filename="large.docx" />)

    expect(await screen.findByText('Page 1 of 12')).toBeInTheDocument()
    const previous = screen.getByRole('button', { name: 'Previous page' })
    const next = screen.getByRole('button', { name: 'Next page' })
    expect(previous).toBeDisabled()

    fireEvent.click(next)
    expect(screen.getByText('Page 2 of 12')).toBeInTheDocument()
    fireEvent.click(next)
    expect(screen.getByText('Page 3 of 12')).toBeInTheDocument()
    fireEvent.click(previous)
    expect(screen.getByText('Page 2 of 12')).toBeInTheDocument()
  })

  it('shows a recoverable error and retries rendering', async () => {
    renderAsync
      .mockRejectedValueOnce(new Error('corrupt package'))
      .mockImplementation(async (blob, container) => addPages(container, 2))

    render(<DocxViewer blob={new Blob(['docx'])} filename="broken.docx" />)

    expect(await screen.findByRole('alert')).toHaveTextContent(
      /could not be rendered/i,
    )
    fireEvent.click(screen.getByRole('button', { name: 'Retry preview' }))

    expect(await screen.findByText('Page 1 of 2')).toBeInTheDocument()
    await waitFor(() => expect(renderAsync).toHaveBeenCalledTimes(2))
  })
})
