import { useState } from 'react'
import { FileUp, LoaderCircle, ShieldCheck, Upload, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  ALLOWED_EXTENSIONS,
  MAX_UPLOAD_BYTES,
  extensionOf,
  formatBytes,
  isFile,
} from '@/lib/documents'
import { getApiErrorMessage } from '@/services/api'
import { createDocumentVersion } from '@/services/documents'

function validateFile(file) {
  if (!isFile(file)) {
    return 'Choose a file to upload.'
  }
  if (file.size <= 0) {
    return 'The selected file is empty.'
  }
  if (file.size > MAX_UPLOAD_BYTES) {
    return 'The selected file must be 10 MB or smaller.'
  }
  if (!ALLOWED_EXTENSIONS.includes(extensionOf(file.name))) {
    return 'Choose a PDF, TXT, DOCX, PNG, or JPEG file.'
  }
  return null
}

export function ReplaceDocumentVersion({
  documentRecord,
  currentVersion,
  onReplaced,
  onConflict,
  onCancel,
}) {
  const [file, setFile] = useState(null)
  const [changeSummary, setChangeSummary] = useState('')
  const [fileError, setFileError] = useState(null)
  const [serverError, setServerError] = useState(null)
  const [progress, setProgress] = useState(0)
  const [isSubmitting, setIsSubmitting] = useState(false)

  function handleFileChange(event) {
    const selected = event.target.files?.[0] ?? null
    setFile(selected)
    setFileError(selected ? validateFile(selected) : null)
    setServerError(null)
    setProgress(0)
  }

  async function handleSubmit(event) {
    event.preventDefault()
    const validationError = validateFile(file)
    if (validationError) {
      setFileError(validationError)
      return
    }
    if (!currentVersion) {
      setServerError('Version history is unavailable. Refresh the page and try again.')
      return
    }

    setFileError(null)
    setServerError(null)
    setProgress(0)
    setIsSubmitting(true)
    try {
      const result = await createDocumentVersion(
        documentRecord.id,
        file,
        currentVersion.version_number,
        changeSummary,
        setProgress,
      )
      setProgress(100)
      onReplaced(result)
    } catch (error) {
      if (error?.response?.status === 409) {
        onConflict?.()
      }
      setServerError(
        error?.response?.status === 409
          ? `${getApiErrorMessage(error)} Refresh and retry to avoid overwriting a newer version.`
          : getApiErrorMessage(error),
      )
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <Card className="border-primary/20">
      <CardHeader className="flex-row items-start justify-between gap-4">
        <div>
          <CardTitle>Upload a revised version</CardTitle>
          <p className="mt-1 text-sm text-muted-foreground">
            Replacing the current file creates version{' '}
            {(currentVersion?.version_number ?? 0) + 1}. Earlier versions are retained.
          </p>
        </div>
        <Button type="button" variant="ghost" size="sm" onClick={onCancel}>
          <X className="size-4" aria-hidden="true" />
          Close
        </Button>
      </CardHeader>
      <CardContent>
        <form className="grid gap-5 lg:grid-cols-[1.5fr_1fr]" onSubmit={handleSubmit}>
          <div className="space-y-5">
            {serverError ? (
              <div
                role="alert"
                className="rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive"
              >
                {serverError}
              </div>
            ) : null}

            <div className="space-y-2">
              <label htmlFor="replacement-file" className="text-sm font-medium">
                Revised file
              </label>
              <input
                id="replacement-file"
                type="file"
                accept=".pdf,.txt,.docx,.png,.jpg,.jpeg"
                onChange={handleFileChange}
                disabled={isSubmitting}
                aria-invalid={fileError ? true : undefined}
                aria-describedby={
                  fileError ? 'replacement-file-error' : 'replacement-file-help'
                }
                className="block w-full cursor-pointer rounded-lg border border-input bg-background px-3 py-3 text-sm file:mr-3 file:rounded-md file:border-0 file:bg-primary file:px-3 file:py-2 file:text-sm file:font-medium file:text-primary-foreground hover:file:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-50"
              />
              <p
                id="replacement-file-help"
                className="text-xs leading-5 text-muted-foreground"
              >
                PDF, TXT, DOCX, PNG, JPG, or JPEG. Maximum 10 MB. The backend validates
                the file type, size, and checksum.
              </p>
              {fileError ? (
                <p id="replacement-file-error" className="text-sm text-destructive">
                  {fileError}
                </p>
              ) : null}
            </div>

            <div className="space-y-2">
              <label htmlFor="replacement-summary" className="text-sm font-medium">
                Change summary{' '}
                <span className="font-normal text-muted-foreground">(optional)</span>
              </label>
              <input
                id="replacement-summary"
                type="text"
                maxLength={500}
                value={changeSummary}
                onChange={(event) => setChangeSummary(event.target.value)}
                placeholder="Describe what changed in this version"
                disabled={isSubmitting}
                className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-xs placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
              />
            </div>

            {isSubmitting ? (
              <div className="space-y-2" aria-live="polite">
                <div className="flex items-center justify-between text-xs text-muted-foreground">
                  <span>Uploading secure version...</span>
                  <span>{progress}%</span>
                </div>
                <div className="h-2 overflow-hidden rounded-full bg-muted">
                  <div
                    className="h-full rounded-full bg-primary transition-all"
                    style={{ width: `${progress}%` }}
                  />
                </div>
              </div>
            ) : null}

            <div className="flex flex-wrap items-center gap-3">
              <Button type="submit" disabled={isSubmitting || !file || !currentVersion}>
                {isSubmitting ? (
                  <LoaderCircle className="size-4 animate-spin" aria-hidden="true" />
                ) : (
                  <Upload className="size-4" aria-hidden="true" />
                )}
                {isSubmitting ? 'Creating version...' : 'Create new version'}
              </Button>
              <span className="text-xs text-muted-foreground">
                Current version: {currentVersion?.version_number ?? 'unavailable'}
              </span>
            </div>
          </div>

          <div className="space-y-3 rounded-lg border bg-muted/20 p-4">
            <p className="flex items-center gap-2 text-sm font-medium">
              <FileUp className="size-4 text-primary" aria-hidden="true" />
              Version safety
            </p>
            <p className="text-sm leading-6 text-muted-foreground">
              The current file is never overwritten. If another user saves first, this
              upload is rejected instead of silently replacing their version.
            </p>
            {file ? (
              <div className="rounded-lg border bg-background p-3">
                <p className="truncate text-sm font-medium">{file.name}</p>
                <p className="text-xs text-muted-foreground">{formatBytes(file.size)}</p>
              </div>
            ) : null}
            <p className="flex items-start gap-2 text-xs leading-5 text-muted-foreground">
              <ShieldCheck className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
              Every version is stored privately and downloaded through the authorized API.
            </p>
          </div>
        </form>
      </CardContent>
    </Card>
  )
}
