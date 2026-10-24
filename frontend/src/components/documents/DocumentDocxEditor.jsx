import { useEffect, useRef, useState } from 'react'
import {
  Bold,
  Heading1,
  Heading2,
  Italic,
  List,
  ListOrdered,
  LoaderCircle,
  Redo2,
  Save,
  ShieldCheck,
  Underline,
  Undo2,
  X,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { replaceExtension } from '@/lib/documents'
import { getApiErrorMessage } from '@/services/api'
import { createDocumentVersion } from '@/services/documents'

function isAbortError(error) {
  return error?.code === 'ERR_CANCELED' || error?.name === 'CanceledError'
}

const TOOLBAR_BUTTONS = [
  { command: 'bold', label: 'Bold', icon: Bold },
  { command: 'italic', label: 'Italic', icon: Italic },
  { command: 'underline', label: 'Underline', icon: Underline },
  { command: 'insertUnorderedList', label: 'Bulleted list', icon: List },
  { command: 'insertOrderedList', label: 'Numbered list', icon: ListOrdered },
]

/**
 * In-browser DOCX editor.
 *
 * The file is fetched through the authenticated preview endpoint, converted to
 * semantic HTML with mammoth, edited in a contenteditable surface, and exported
 * to a real DOCX with the `docx` package. Saving calls the normal version API,
 * so the backend still enforces EDIT permission and optimistic version checks.
 *
 * Fidelity limits: this is a rich-text round-trip, not a full Word layout
 * engine. Complex styles, text boxes, columns, comments, tracked changes, and
 * some headers/footers may be simplified or dropped.
 */
export function DocumentDocxEditor({
  blob,
  documentRecord,
  currentVersion,
  onSaved,
  onConflict,
  onCancel,
}) {
  const editorRef = useRef(null)
  const [originalHtml, setOriginalHtml] = useState('')
  const [currentHtml, setCurrentHtml] = useState('')
  const [changeSummary, setChangeSummary] = useState('')
  const [isLoading, setIsLoading] = useState(true)
  const [loadError, setLoadError] = useState(null)
  const [saveError, setSaveError] = useState(null)
  const [isSaving, setIsSaving] = useState(false)
  const [isStale, setIsStale] = useState(false)

  useEffect(() => {
    let active = true

    if (!blob) {
      return undefined
    }

    setIsLoading(true)
    setLoadError(null)

    import('@/lib/docx')
      .then(({ extractDocxHtml }) => extractDocxHtml(blob))
      .then(({ html }) => {
        if (!active) {
          return
        }
        setOriginalHtml(html)
        setCurrentHtml(html)
        if (editorRef.current) {
          editorRef.current.innerHTML = html
        }
      })
      .catch((error) => {
        if (active && !isAbortError(error)) {
          setLoadError(error)
        }
      })
      .finally(() => {
        if (active) {
          setIsLoading(false)
        }
      })

    return () => {
      active = false
    }
  }, [blob])

  const hasChanges = currentHtml !== originalHtml
  const canSave =
    Boolean(currentVersion) &&
    hasChanges &&
    !isLoading &&
    !loadError &&
    !isSaving &&
    !isStale

  function syncHtml() {
    if (editorRef.current) {
      setCurrentHtml(editorRef.current.innerHTML)
    }
  }

  function runCommand(command, value = null) {
    const editor = editorRef.current
    if (!editor) {
      return
    }
    editor.focus()
    if (typeof document.execCommand === 'function') {
      document.execCommand(command, false, value)
    }
    syncHtml()
  }

  async function handleSubmit(event) {
    event.preventDefault()
    if (!canSave) {
      return
    }

    setSaveError(null)
    setIsSaving(true)
    try {
      const html = editorRef.current?.innerHTML ?? currentHtml
      const { DOCX_MIME, buildDocxBlob } = await import('@/lib/docx')
      const blob = await buildDocxBlob(html, { title: documentRecord.name })
      const file = new File([blob], replaceExtension(documentRecord.name, 'docx'), {
        type: DOCX_MIME,
      })
      const result = await createDocumentVersion(
        documentRecord.id,
        file,
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
          <CardTitle>Edit document content</CardTitle>
          <p className="mt-1 text-sm text-muted-foreground">
            Edit headings, text, lists, tables, and embedded images. Saving creates a
            new immutable DOCX version and keeps earlier versions.
          </p>
        </div>
        <Button type="button" variant="ghost" size="sm" onClick={onCancel}>
          <X className="size-4" aria-hidden="true" />
          Close
        </Button>
      </CardHeader>
      <CardContent>
        {loadError ? (
          <div
            role="alert"
            className="mb-4 rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive"
          >
            {getApiErrorMessage(loadError)}
          </div>
        ) : null}

        {!currentVersion ? (
          <div
            role="alert"
            className="mb-4 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900"
          >
            Version history is unavailable, so this file cannot be saved safely.
            Refresh the page and try again.
          </div>
        ) : null}

        <form className="space-y-4" onSubmit={handleSubmit}>
          {saveError ? (
            <div
              role="alert"
              className="rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive"
            >
              {saveError}
            </div>
          ) : null}

          <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-xs text-amber-900">
            Editing uses a continuous-flow surface, not Word's paginated layout. Preview
            navigation follows rendered page-break and section elements. This editor
            preserves common formatting, but complex layouts, text boxes, comments, and
            tracked changes may be simplified. The original version is never overwritten.
          </div>

          <div className="overflow-hidden rounded-md border">
            <div
              role="toolbar"
              aria-label="Document formatting"
              className="flex flex-wrap items-center gap-1 border-b bg-muted/30 px-2 py-1.5"
            >
              {TOOLBAR_BUTTONS.map(({ command, label, icon: Icon }) => (
                <Button
                  key={command}
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="h-8 px-2"
                  aria-label={label}
                  title={label}
                  onMouseDown={(event) => event.preventDefault()}
                  onClick={() => runCommand(command)}
                  disabled={isLoading || isStale}
                >
                  <Icon className="size-4" aria-hidden="true" />
                </Button>
              ))}
              <span className="mx-1 h-5 w-px bg-border" aria-hidden="true" />
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="h-8 px-2"
                aria-label="Heading 1"
                title="Heading 1"
                onMouseDown={(event) => event.preventDefault()}
                onClick={() => runCommand('formatBlock', '<h1>')}
                disabled={isLoading || isStale}
              >
                <Heading1 className="size-4" aria-hidden="true" />
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="h-8 px-2"
                aria-label="Heading 2"
                title="Heading 2"
                onMouseDown={(event) => event.preventDefault()}
                onClick={() => runCommand('formatBlock', '<h2>')}
                disabled={isLoading || isStale}
              >
                <Heading2 className="size-4" aria-hidden="true" />
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="h-8 px-2"
                aria-label="Undo"
                title="Undo"
                onMouseDown={(event) => event.preventDefault()}
                onClick={() => runCommand('undo')}
                disabled={isLoading || isStale}
              >
                <Undo2 className="size-4" aria-hidden="true" />
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="h-8 px-2"
                aria-label="Redo"
                title="Redo"
                onMouseDown={(event) => event.preventDefault()}
                onClick={() => runCommand('redo')}
                disabled={isLoading || isStale}
              >
                <Redo2 className="size-4" aria-hidden="true" />
              </Button>
            </div>

            <div className="relative">
              {isLoading ? (
                <div
                  className="absolute inset-0 z-10 flex min-h-80 items-center justify-center gap-3 bg-background/80 text-sm text-muted-foreground"
                  aria-busy="true"
                  aria-live="polite"
                >
                  <LoaderCircle className="size-5 animate-spin" aria-hidden="true" />
                  Loading editable document...
                </div>
              ) : null}
              <div
                ref={editorRef}
                contentEditable={!isLoading && !isStale}
                suppressContentEditableWarning
                role="textbox"
                aria-multiline="true"
                aria-label="Document content"
                spellCheck
                onInput={syncHtml}
                className="min-h-80 max-h-[36rem] overflow-auto bg-background px-6 py-5 text-sm leading-7 outline-none [&_h1]:mb-4 [&_h1]:text-2xl [&_h1]:font-semibold [&_h2]:mb-3 [&_h2]:mt-6 [&_h2]:text-xl [&_h2]:font-semibold [&_li]:ml-6 [&_ol]:my-3 [&_ol]:list-decimal [&_p]:my-3 [&_table]:my-4 [&_table]:w-full [&_td]:border [&_td]:p-2 [&_th]:border [&_th]:bg-muted [&_th]:p-2 [&_ul]:my-3 [&_ul]:list-disc"
              />
            </div>
          </div>

          <div className="space-y-2">
            <label htmlFor="docx-change-summary" className="text-sm font-medium">
              Change summary{' '}
              <span className="font-normal text-muted-foreground">(optional)</span>
            </label>
            <input
              id="docx-change-summary"
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
      </CardContent>
    </Card>
  )
}
