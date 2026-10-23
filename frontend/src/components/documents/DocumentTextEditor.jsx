import { useEffect, useState } from 'react'
import { LoaderCircle, Save, ShieldCheck, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { getApiErrorMessage } from '@/services/api'
import { previewDocument, updateDocumentTextContent } from '@/services/documents'

function isAbortError(error) {
  return error?.code === 'ERR_CANCELED' || error?.name === 'CanceledError'
}

export function DocumentTextEditor({
  documentRecord,
  currentVersion,
  onSaved,
  onConflict,
  onCancel,
}) {
  const [content, setContent] = useState('')
  const [originalContent, setOriginalContent] = useState('')
  const [changeSummary, setChangeSummary] = useState('')
  const [isLoading, setIsLoading] = useState(true)
  const [loadError, setLoadError] = useState(null)
  const [saveError, setSaveError] = useState(null)
  const [isSaving, setIsSaving] = useState(false)
  const [isStale, setIsStale] = useState(false)

  useEffect(() => {
    const controller = new AbortController()

    previewDocument(documentRecord.id, controller.signal)
      .then(async ({ blob }) => {
        const value = await blob.text()
        setContent(value)
        setOriginalContent(value)
      })
      .catch((error) => {
        if (!isAbortError(error)) {
          setLoadError(error)
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setIsLoading(false)
        }
      })

    return () => controller.abort()
  }, [documentRecord.id])

  const hasChanges = content !== originalContent
  const canSave =
    Boolean(currentVersion) &&
    hasChanges &&
    content.length > 0 &&
    !isSaving &&
    !isStale

  async function handleSubmit(event) {
    event.preventDefault()
    if (!canSave) {
      return
    }

    setSaveError(null)
    setIsSaving(true)
    try {
      const result = await updateDocumentTextContent(
        documentRecord.id,
        content,
        currentVersion.version_number,
        changeSummary,
      )
      onSaved(result)
    } catch (error) {
      if (error?.response?.status === 409) {
        setIsStale(true)
        onConflict?.()
      }
      setSaveError(
        error?.response?.status === 409
          ? `${getApiErrorMessage(error)} Close this editor and reopen it from the refreshed version before saving again.`
          : getApiErrorMessage(error),
      )
    } finally {
      setIsSaving(false)
    }
  }

  return (
    <Card>
      <CardHeader className="flex-row items-start justify-between gap-4">
        <div>
          <CardTitle>Edit text content</CardTitle>
          <p className="mt-1 text-sm text-muted-foreground">
            Saving creates a new immutable version. Earlier versions remain available.
          </p>
        </div>
        <Button type="button" variant="ghost" size="sm" onClick={onCancel}>
          <X className="size-4" aria-hidden="true" />
          Close
        </Button>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="flex min-h-48 items-center justify-center gap-3 text-sm text-muted-foreground">
            <LoaderCircle className="size-5 animate-spin" aria-hidden="true" />
            Loading editable content...
          </div>
        ) : loadError ? (
          <div
            role="alert"
            className="rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive"
          >
            {getApiErrorMessage(loadError)}
          </div>
        ) : !currentVersion ? (
          <div
            role="alert"
            className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900"
          >
            Version history is unavailable, so this file cannot be saved safely.
            Refresh the page and try again.
          </div>
        ) : (
          <form className="space-y-4" onSubmit={handleSubmit}>
            {saveError ? (
              <div
                role="alert"
                className="rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive"
              >
                {saveError}
              </div>
            ) : null}

            <div className="space-y-2">
              <label htmlFor="document-text-content" className="text-sm font-medium">
                File content
              </label>
              <textarea
                id="document-text-content"
                value={content}
                onChange={(event) => setContent(event.target.value)}
                rows={18}
                maxLength={10_000_000}
                spellCheck={false}
                disabled={isSaving || isStale}
                className="flex min-h-80 w-full rounded-md border border-input bg-background px-3 py-3 font-mono text-sm leading-6 shadow-xs focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
              />
              <div className="flex flex-wrap justify-between gap-2 text-xs text-muted-foreground">
                <span>{content.length.toLocaleString()} characters</span>
                <span>UTF-8 plain text</span>
              </div>
            </div>

            <div className="space-y-2">
              <label htmlFor="document-change-summary" className="text-sm font-medium">
                Change summary{' '}
                <span className="font-normal text-muted-foreground">(optional)</span>
              </label>
              <input
                id="document-change-summary"
                type="text"
                value={changeSummary}
                maxLength={500}
                onChange={(event) => setChangeSummary(event.target.value)}
                placeholder="Describe what changed in this version"
                disabled={isSaving || isStale}
                className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-xs placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
              />
            </div>

            <div className="flex flex-wrap items-center gap-3">
              <Button type="submit" disabled={!canSave}>
                {isSaving ? (
                  <LoaderCircle className="size-4 animate-spin" aria-hidden="true" />
                ) : (
                  <Save className="size-4" aria-hidden="true" />
                )}
                {isSaving ? 'Saving version...' : 'Save new version'}
              </Button>
              <Button
                type="button"
                variant="outline"
                onClick={onCancel}
                disabled={isSaving || isStale}
              >
                Cancel
              </Button>
              <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
                <ShieldCheck className="size-3.5" aria-hidden="true" />
                The server validates and audits every new version.
              </span>
            </div>
          </form>
        )}
      </CardContent>
    </Card>
  )
}
