import { useState } from 'react'
import { useForm } from 'react-hook-form'
import {
  CheckCircle2,
  FileText,
  FileUp,
  LoaderCircle,
  LockKeyhole,
  ShieldAlert,
  Upload,
} from 'lucide-react'
import { z } from 'zod'
import { useAuth } from '@/auth/useAuth'
import { PageHeader } from '@/components/PageHeader'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { getApiErrorMessage } from '@/services/api'
import { uploadDocument } from '@/services/documents'

const MAX_UPLOAD_BYTES = 10 * 1024 * 1024
const ALLOWED_EXTENSIONS = ['pdf', 'txt', 'docx', 'png', 'jpg', 'jpeg']
const CATEGORY_OPTIONS = [
  'General',
  'Contracts',
  'Finance',
  'Human resources',
  'Legal',
  'Other',
]

function isFile(value) {
  return typeof File !== 'undefined' && value instanceof File
}

function extensionOf(filename) {
  const parts = filename.toLowerCase().split('.')
  return parts.length > 1 ? parts.pop() : ''
}

function formatBytes(bytes) {
  if (bytes < 1024) {
    return `${bytes} B`
  }
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`
  }
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

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
  category: z.string().max(100, { message: 'Category must be 100 characters or fewer.' }),
  description: z
    .string()
    .max(2000, { message: 'Description must be 2,000 characters or fewer.' }),
})

export function DocumentsPage() {
  const { user } = useAuth()
  const canUpload = user?.role === 'ADMINISTRATOR' || user?.role === 'DOCUMENT_OWNER'
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
    formState: { errors, isSubmitting },
  } = useForm({
    defaultValues: { category: 'General', description: '' },
  })

  function handleFileChange(event) {
    setFile(event.target.files?.[0] ?? null)
    setFileError(null)
    setServerError(null)
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
      const document = await uploadDocument(
        result.data.file,
        {
          category: result.data.category,
          description: result.data.description,
        },
        setProgress,
      )
      setUploaded(document)
      setFile(null)
      setFileError(null)
      setProgress(100)
      reset()
      event?.target?.reset()
    } catch (error) {
      setServerError(getApiErrorMessage(error))
    }
  }

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Documents"
        title="Upload a document"
        description="Upload a supported file to private Wasabi storage. The backend validates the content, generates the storage key, records a SHA-256 checksum, and enforces your account role."
      />

      {!canUpload ? (
        <Card>
          <CardContent className="flex flex-col items-start gap-4 px-6 py-8">
            <span className="flex size-12 items-center justify-center rounded-xl bg-amber-50 text-amber-700">
              <ShieldAlert className="size-6" aria-hidden="true" />
            </span>
            <div className="space-y-2">
              <h2 className="text-lg font-semibold tracking-tight">
                Your role cannot upload documents
              </h2>
              <p className="max-w-2xl text-sm leading-6 text-muted-foreground">
                Viewer accounts can sign in but cannot upload. Ask an administrator to provision a
                Document owner or Administrator account if you need upload access. The backend
                rejects unauthorized uploads even if this interface is bypassed.
              </p>
            </div>
          </CardContent>
        </Card>
      ) : null}

      {uploaded ? (
        <Card>
          <CardContent className="flex flex-col gap-4 px-6 py-6" role="status">
            <div className="flex items-start gap-3">
              <CheckCircle2 className="mt-0.5 size-5 shrink-0 text-emerald-600" aria-hidden="true" />
              <div className="space-y-1">
                <h2 className="font-semibold">Upload completed</h2>
                <p className="text-sm text-muted-foreground">
                  {uploaded.name} was stored privately. No download or sharing link is available
                  yet.
                </p>
              </div>
            </div>
            <dl className="grid gap-3 rounded-lg border bg-muted/30 p-4 text-sm sm:grid-cols-2">
              <div>
                <dt className="text-muted-foreground">File size</dt>
                <dd className="font-medium">{formatBytes(uploaded.file_size)}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Category</dt>
                <dd className="font-medium">{uploaded.category || 'Uncategorized'}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">MIME type</dt>
                <dd className="font-medium">{uploaded.mime_type}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Uploaded</dt>
                <dd className="font-medium">
                  {new Date(uploaded.created_at).toLocaleString()}
                </dd>
              </div>
              <div className="sm:col-span-2">
                <dt className="text-muted-foreground">SHA-256 checksum</dt>
                <dd className="font-mono text-xs break-all">{uploaded.checksum}</dd>
              </div>
            </dl>
          </CardContent>
        </Card>
      ) : null}

      {canUpload ? (
        <div className="grid gap-5 lg:grid-cols-[2fr_1fr]">
          <Card>
            <CardContent className="px-6 py-6">
              <form className="space-y-6" onSubmit={handleSubmit(onSubmit)} noValidate>
                {serverError ? (
                  <div
                    role="alert"
                    className="rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive"
                  >
                    {serverError}
                  </div>
                ) : null}

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
                      Description <span className="font-normal text-muted-foreground">(optional)</span>
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
                    The backend validates the selected file again.
                  </span>
                </div>
              </form>
            </CardContent>
          </Card>

          <div className="space-y-5">
            <Card>
              <CardContent className="space-y-4 px-6 py-6">
                <div className="flex items-center gap-2 text-sm font-medium">
                  <LockKeyhole className="size-4 text-primary" aria-hidden="true" />
                  Private by default
                </div>
                <p className="text-sm leading-6 text-muted-foreground">
                  Files are stored in a private bucket. The server generates the object key and
                  records the owner, size, MIME type, and checksum. The storage key is never sent
                  to the browser.
                </p>
              </CardContent>
            </Card>

            {file ? (
              <Card>
                <CardContent className="space-y-2 px-6 py-6">
                  <div className="flex items-center gap-2 text-sm font-medium">
                    <FileUp className="size-4 text-primary" aria-hidden="true" />
                    Selected file
                  </div>
                  <p className="truncate text-sm">{file.name}</p>
                  <p className="text-xs text-muted-foreground">{formatBytes(file.size)}</p>
                </CardContent>
              </Card>
            ) : null}
          </div>
        </div>
      ) : null}

      <Card>
        <CardContent className="flex flex-col items-start gap-3 px-6 py-6 text-sm text-muted-foreground">
          <div className="flex items-center gap-2 font-medium text-foreground">
            <FileText className="size-4" aria-hidden="true" />
            Document library
          </div>
          <p className="max-w-3xl leading-6">
            Listing, search, downloads, and per-document permissions are not available yet. This
            page does not display sample documents or claim that those workflows exist.
          </p>
        </CardContent>
      </Card>
    </div>
  )
}
