import { useEffect, useState } from 'react'
import { FileQuestion, LoaderCircle, RefreshCw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { previewKindOf } from '@/lib/documents'
import { getApiErrorMessage } from '@/services/api'
import { previewDocument } from '@/services/documents'

function isAbortError(error) {
  return error?.code === 'ERR_CANCELED' || error?.name === 'CanceledError'
}

export function DocumentPreview({ documentRecord }) {
  const kind = previewKindOf(documentRecord)
  const [blobUrl, setBlobUrl] = useState(null)
  const [text, setText] = useState(null)
  const [isLoading, setIsLoading] = useState(kind !== 'unsupported')
  const [error, setError] = useState(null)
  const [refreshKey, setRefreshKey] = useState(0)

  useEffect(() => {
    if (kind === 'unsupported') {
      return undefined
    }

    const controller = new AbortController()
    let createdUrl = null

    previewDocument(documentRecord.id, controller.signal)
      .then(async ({ blob }) => {
        if (kind === 'text') {
          setText(await blob.text())
          return
        }
        createdUrl = URL.createObjectURL(blob)
        setBlobUrl(createdUrl)
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

  if (kind === 'unsupported') {
    return (
      <div className="flex flex-col items-center gap-3 rounded-lg border border-dashed px-6 py-12 text-center">
        <span className="flex size-12 items-center justify-center rounded-xl bg-muted text-muted-foreground">
          <FileQuestion className="size-6" aria-hidden="true" />
        </span>
        <div className="space-y-1">
          <h3 className="font-semibold">Preview unavailable</h3>
          <p className="max-w-md text-sm text-muted-foreground">
            TrustVault can preview PDF, plain-text, PNG, and JPEG files. Download this
            document to review it in an approved desktop application.
          </p>
        </div>
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

  return (
    <iframe
      src={blobUrl}
      title={`Preview of ${documentRecord.name}`}
      sandbox="allow-same-origin"
      referrerPolicy="no-referrer"
      className="h-[34rem] w-full rounded-lg border bg-muted/20"
    />
  )
}
