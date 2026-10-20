import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { CheckCircle2, FileUp, LoaderCircle, LockKeyhole, Upload, X } from 'lucide-react'
import { Link } from 'react-router-dom'
import { z } from 'zod'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import {
  ALLOWED_EXTENSIONS,
  CATEGORY_OPTIONS,
  MAX_UPLOAD_BYTES,
  extensionOf,
  formatBytes,
  isFile,
} from '@/lib/documents'
import { getApiErrorMessage } from '@/services/api'
import { uploadDocument } from '@/services/documents'

const uploadSchema = z.object({
  file: z
    .custom(isFile, { message: 'Choose a file to upload.' })
    .refine((file) => isFile(file) && file.size > 0, {
      message: 'The selected file is empty.',
    })
    .refine((file) => isFile(file) && file.size <= MAX_UPLOAD_BYTES, {
      message: 'The selected file must be 10 MB or smaller.',
    })
    .refine(
      (file) => isFile(file) && ALLOWED_EXTENSIONS.includes(extensionOf(file.name)),
      {
        message: 'Choose a PDF, TXT, DOCX, PNG, or JPEG file.',
      },
    ),
  category: z.string().trim().max(100, { message: 'Category must be 100 characters or fewer.' }),
  description: z
    .string()
    .trim()
    .max(2000, { message: 'Description must be 2,000 characters or fewer.' }),
})

export function UploadDocumentPanel({ onUploaded, onCancel }) {
  const [file, setFile] = useState(null)
  const [fileError, setFileError] = useState(null)
  const [serverError, setServerError] = useState(null)
  const [uploaded, setUploaded] = useState(null)
  const [progress, setProgress] = useState(0)
  const {
    register,
    handleSubmit,
    reset,
    setError,
    clearErrors,
    formState: { errors, isSubmitting },
  } = useForm({
    defaultValues: { category: 'General', description: '' },
  })

  function handleFileChange(event) {
    setFile(event.target.files?.[0] ?? null)
    setFileError(null)
    setServerError(null)
    setUploaded(null)
  }

  const onSubmit = async (values, event) => {
    setServerError(null)
    setUploaded(null)
    setProgress(0)

    const result = uploadSchema.safeParse({
      file,
      category: values.category,
      description: values.description,
    })

    if (!result.success) {
      setFileError(null)
      clearErrors()
      for (const issue of result.error.issues) {
        const field = issue.path[0]
        if (field === 'file') {
          setFileError(issue.message)
        } else if (field === 'category' || field === 'description') {
          setError(field, { type: 'manual', message: issue.message })
        }
      }
      return
    }

    try {
      const documentRecord = await uploadDocument(
        result.data.file,
        {
          category: result.data.category,
          description: result.data.description,
        },
        setProgress,
      )
      setUploaded(documentRecord)
      setFile(null)
      setFileError(null)
      setProgress(100)
      reset({ category: 'General', description: '' })
      event?.target?.reset()
      onUploaded?.(documentRecord)
    } catch (error) {
      setServerError(getApiErrorMessage(error))
    }
  }

  return (
    <Card className="border-primary/20">
      <CardContent className="space-y-6 px-6 py-6">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 className="text-lg font-semibold tracking-tight">Upload a document</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              Files are validated by the backend and stored in a private bucket.
            </p>
          </div>
          <Button type="button" variant="ghost" size="sm" onClick={onCancel}>
            <X className="size-4" aria-hidden="true" />
            Close
          </Button>
        </div>

        {uploaded ? (
          <div
            className="flex flex-col gap-3 rounded-lg border border-emerald-200 bg-emerald-50/70 px-4 py-4 sm:flex-row sm:items-center sm:justify-between"
            role="status"
          >
            <div className="flex items-start gap-3">
              <CheckCircle2 className="mt-0.5 size-5 shrink-0 text-emerald-600" aria-hidden="true" />
              <div>
                <p className="font-medium">Upload completed</p>
                <p className="text-sm text-muted-foreground">
                  {uploaded.name} is now available in your document library.
                </p>
              </div>
            </div>
            <Link
              to={`/documents/${uploaded.id}`}
              className="text-sm font-medium text-primary underline-offset-4 hover:underline"
            >
              View details
            </Link>
          </div>
        ) : null}

        {serverError ? (
          <div
            role="alert"
            className="rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive"
          >
            {serverError}
          </div>
        ) : null}

        <form className="grid gap-6 lg:grid-cols-[1.5fr_1fr]" onSubmit={handleSubmit(onSubmit)}>
          <div className="space-y-5">
            <div className="space-y-2">
              <label htmlFor="document-file" className="text-sm font-medium">
                Document file
              </label>
              <input
                id="document-file"
                name="file"
                type="file"
                accept=".pdf,.txt,.docx,.png,.jpg,.jpeg"
                onChange={handleFileChange}
                disabled={isSubmitting}
                aria-invalid={fileError ? true : undefined}
                aria-describedby={fileError ? 'document-file-error' : 'document-file-help'}
                className="block w-full cursor-pointer rounded-lg border border-input bg-background px-3 py-3 text-sm file:mr-3 file:rounded-md file:border-0 file:bg-primary file:px-3 file:py-2 file:text-sm file:font-medium file:text-primary-foreground hover:file:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-50"
              />
              <p id="document-file-help" className="text-xs leading-5 text-muted-foreground">
                PDF, TXT, DOCX, PNG, JPG, or JPEG. Maximum 10 MB.
              </p>
              {fileError ? (
                <p id="document-file-error" className="text-sm text-destructive">
                  {fileError}
                </p>
              ) : null}
            </div>

            <div className="grid gap-5 sm:grid-cols-2">
              <div className="space-y-2">
                <label htmlFor="document-category" className="text-sm font-medium">
                  Category
                </label>
                <select
                  id="document-category"
                  className="flex h-11 w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-xs transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                  disabled={isSubmitting}
                  aria-invalid={errors.category ? true : undefined}
                  aria-describedby={errors.category ? 'document-category-error' : undefined}
                  {...register('category')}
                >
                  {CATEGORY_OPTIONS.map((category) => (
                    <option key={category} value={category}>
                      {category}
                    </option>
                  ))}
                </select>
                {errors.category ? (
                  <p id="document-category-error" className="text-sm text-destructive">
                    {errors.category.message}
                  </p>
                ) : null}
              </div>

              <div className="space-y-2 sm:row-span-2">
                <label htmlFor="document-description" className="text-sm font-medium">
                  Description{' '}
                  <span className="font-normal text-muted-foreground">(optional)</span>
                </label>
                <textarea
                  id="document-description"
                  rows={4}
                  maxLength={2000}
                  placeholder="A short description for your own reference"
                  className="flex min-h-24 w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-xs transition-colors placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 aria-invalid:border-destructive"
                  disabled={isSubmitting}
                  aria-invalid={errors.description ? true : undefined}
                  aria-describedby={
                    errors.description ? 'document-description-error' : undefined
                  }
                  {...register('description')}
                />
                {errors.description ? (
                  <p id="document-description-error" className="text-sm text-destructive">
                    {errors.description.message}
                  </p>
                ) : null}
              </div>
            </div>

            {isSubmitting ? (
              <div className="space-y-2" aria-live="polite">
                <div className="flex items-center justify-between text-xs text-muted-foreground">
                  <span>Uploading securely...</span>
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
              <Button type="submit" disabled={isSubmitting || !file}>
                {isSubmitting ? (
                  <>
                    <LoaderCircle className="size-4 animate-spin" aria-hidden="true" />
                    Uploading...
                  </>
                ) : (
                  <>
                    <Upload className="size-4" aria-hidden="true" />
                    Upload document
                  </>
                )}
              </Button>
              <span className="text-xs text-muted-foreground">
                The backend validates the file again.
              </span>
            </div>
          </div>

          <div className="space-y-4">
            <div className="flex items-center gap-2 text-sm font-medium">
              <LockKeyhole className="size-4 text-primary" aria-hidden="true" />
              Private by default
            </div>
            <p className="text-sm leading-6 text-muted-foreground">
              The server generates the storage key and records the owner, size, MIME type, and
              SHA-256 checksum. Object keys are never sent to the browser.
            </p>

            {file ? (
              <div className="rounded-lg border bg-muted/30 p-4">
                <div className="flex items-center gap-2 text-sm font-medium">
                  <FileUp className="size-4 text-primary" aria-hidden="true" />
                  Selected file
                </div>
                <p className="mt-2 truncate text-sm">{file.name}</p>
                <p className="text-xs text-muted-foreground">{formatBytes(file.size)}</p>
              </div>
            ) : null}
          </div>
        </form>
      </CardContent>
    </Card>
  )
}
