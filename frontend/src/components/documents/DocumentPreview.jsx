import { useEffect, useState } from 'react'
import { Download, FileQuestion, LoaderCircle, RefreshCw } from 'lucide-react'
import DOMPurify from 'dompurify'
import { Button } from '@/components/ui/button'
import { previewKindOf, saveBlob } from '@/lib/documents'
import { getApiErrorMessage } from '@/services/api'
import { downloadDocument, previewDocument } from '@/services/documents'
import { PdfViewer } from './PdfViewer'

function isAbortError(error) {
  return error?.code === 'ERR_CANCELED' || error?.name === 'CanceledError'
}

export function DocumentPreview({ documentRecord }) {
  const kind = previewKindOf(documentRecord)
  const [blob, setBlob] = useState(null)
  const [blobUrl, setBlobUrl] = useState(null)
  const [text, setText] = useState(null)
  const [docxHtml, setDocxHtml] = useState('')
  const [isLoading, setIsLoading] = useState(kind !== 'unsupported')
  const [isDownloading, setIsDownloading] = useState(false)
  const [downloadError, setDownloadError] = useState(null)
  const [error, setError] = useState(null)
  const [refreshKey, setRefreshKey] = useState(0)

  useEffect(() => {
    if (kind === 'unsupported') {
      return undefined
    }

    const controller = new AbortController()
    let createdUrl = null

    setIsLoading(true)
    setError(null)

    previewDocument(documentRecord.id, controller.signal)
      .then(async ({ blob: downloadedBlob }) => {
        setBlob(downloadedBlob)
        if (kind === 'text') {
          setText(await downloadedBlob.text())
          return
        }
        if (kind === 'docx') {
          const { default: mammoth } = await import('mammoth')
          const result = await mammoth.convertToHtml({
            arrayBuffer: await downloadedBlob.arrayBuffer(),
          })
          setDocxHtml(DOMPurify.sanitize(result.value))
          return
        }
        if (kind === 'image') {
          createdUrl = URL.createObjectURL(downloadedBlob)
          setBlobUrl(createdUrl)
        }
      })
      .catch((requestError) => {
        if (!isAbortError(requestError)) {
          setError(requestError)
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setIsLoading(false)
        }
      })

    return () => {
      controller.abort()
      if (createdUrl) {
        URL.revokeObjectURL(createdUrl)
      }
    }
  }, [documentRecord.id, kind, refreshKey])

  async function handleDownloadUnsupported() {
    setIsDownloading(true)
    setDownloadError(null)
    try {
      const { blob: downloaded, filename } = await downloadDocument(
        documentRecord.id,
        documentRecord.name,
      )
      saveBlob(downloaded, filename)
    } catch (err) {
      setDownloadError(getApiErrorMessage(err))
    } finally {
      setIsDownloading(false)
    }
  }

  if (kind === 'unsupported') {
    return (
      <div className="flex flex-col items-center gap-4 rounded-lg border border-dashed px-6 py-12 text-center">
        <span className="flex size-12 items-center justify-center rounded-xl bg-muted text-muted-foreground">
          <FileQuestion className="size-6" aria-hidden="true" />
        </span>
        <div className="space-y-1">
          <h3 className="font-semibold text-foreground">Preview unavailable</h3>
          <p className="max-w-md text-sm text-muted-foreground">
            TrustVault can preview DOCX, PDF, plain-text, PNG, and JPEG files. Download
            this document to review it in an approved application.
          </p>
        </div>
        {downloadError ? (
          <p className="text-xs text-destructive" role="alert">
            {downloadError}
          </p>
        ) : null}
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={handleDownloadUnsupported}
          disabled={isDownloading}
          aria-label={`Download ${documentRecord.name}`}
        >
          {isDownloading ? (
            <LoaderCircle className="size-4 animate-spin" aria-hidden="true" />
          ) : (
            <Download className="size-4" aria-hidden="true" />
          )}
          {isDownloading ? 'Downloading...' : 'Download document'}
        </Button>
      </div>
    )
  }

  if (isLoading) {
    return (
      <div
        className="flex min-h-64 items-center justify-center gap-3 rounded-lg border border-dashed text-sm text-muted-foreground"
        aria-busy="true"
        aria-live="polite"
      >
        <LoaderCircle className="size-5 animate-spin" aria-hidden="true" />
        Loading secure preview...
      </div>
    )
  }

  if (error) {
    return (
      <div className="space-y-3 rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-4 text-sm text-destructive">
        <p role="alert">{getApiErrorMessage(error)}</p>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => {
            setIsLoading(true)
            setError(null)
            setRefreshKey((key) => key + 1)
          }}
        >
          <RefreshCw className="size-4" aria-hidden="true" />
          Retry preview
        </Button>
      </div>
    )
  }

  if (kind === 'text') {
    return (
      <pre className="max-h-[34rem] overflow-auto rounded-lg border bg-muted/20 p-5 text-sm leading-6 whitespace-pre-wrap break-words">
        {text}
      </pre>
    )
  }

  if (kind === 'docx') {
    return (
      <article
        className="max-h-[34rem] overflow-auto rounded-lg border bg-background p-5 text-sm leading-6 [&_h1]:mb-4 [&_h1]:text-2xl [&_h1]:font-semibold [&_h2]:mb-3 [&_h2]:mt-6 [&_h2]:text-xl [&_h2]:font-semibold [&_li]:ml-6 [&_ol]:my-3 [&_ol]:list-decimal [&_p]:my-3 [&_table]:my-4 [&_table]:w-full [&_td]:border [&_td]:p-2 [&_th]:border [&_th]:bg-muted [&_th]:p-2 [&_ul]:my-3 [&_ul]:list-disc"
        dangerouslySetInnerHTML={{ __html: docxHtml }}
      />
    )
  }

  if (kind === 'image') {
    return (
      <div className="flex min-h-64 items-center justify-center overflow-auto rounded-lg border bg-muted/20 p-4">
        <img
          src={blobUrl}
          alt={`Preview of ${documentRecord.name}`}
          className="max-h-[32rem] max-w-full object-contain"
        />
      </div>
    )
  }

  if (kind === 'pdf') {
    if (!blob) {
      return (
        <div className="flex min-h-64 items-center justify-center text-sm text-muted-foreground">
          PDF content is unavailable.
        </div>
      )
    }
    return <PdfViewer blob={blob} filename={documentRecord.name} />
  }

  return null
}
