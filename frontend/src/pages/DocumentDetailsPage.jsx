import { useEffect, useState } from 'react'
import { useForm } from 'react-hook-form'
import {
  ArrowLeft,
  CalendarDays,
  Download,
  FileText,
  FileUp,
  Fingerprint,
  HardDrive,
  KeyRound,
  LoaderCircle,
  Pencil,
  PencilLine,
  RefreshCw,
  ShieldAlert,
  ShieldCheck,
  Trash2,
  UserRound,
  X,
} from 'lucide-react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { z } from 'zod'
import { useAuth } from '@/auth/useAuth'
import { AccessLevelBadge } from '@/components/documents/AccessLevelBadge'
import { DocumentPreview } from '@/components/documents/DocumentPreview'
import { DocumentTextEditor } from '@/components/documents/DocumentTextEditor'
import { ReplaceDocumentVersion } from '@/components/documents/ReplaceDocumentVersion'
import { VersionHistory } from '@/components/documents/VersionHistory'
import { PageHeader } from '@/components/PageHeader'
import { Button } from '@/components/ui/button'
import { buttonVariants } from '@/components/ui/button-variants'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  ACCESS_LEVEL_META,
  canDeleteDocument,
  canEditDocument,
  canEditTextContent,
  canManageDocumentPermissions,
  canReadDocument,
  canReplaceDocumentFile,
  categoryChoices,
  formatBytes,
  formatDateTime,
  saveBlob,
} from '@/lib/documents'
import { getApiErrorMessage } from '@/services/api'
import {
  deleteDocument,
  downloadDocument,
  downloadDocumentVersion,
  getDocument,
  listDocumentVersions,
  updateDocument,
} from '@/services/documents'

const editSchema = z.object({
  name: z
    .string()
    .trim()
    .min(1, { message: 'Document name is required.' })
    .max(255, { message: 'Name must be 255 characters or fewer.' }),
  category: z.string().trim().max(100, { message: 'Category must be 100 characters or fewer.' }),
  description: z
    .string()
    .trim()
    .max(2000, { message: 'Description must be 2,000 characters or fewer.' }),
})

function isAbortError(error) {
  return error?.code === 'ERR_CANCELED' || error?.name === 'CanceledError'
}

function MetadataItem({ icon: Icon, label, children, className }) {
  return (
    <div className={className}>
      <dt className="flex items-center gap-2 text-xs font-medium tracking-wide text-muted-foreground uppercase">
        <Icon className="size-3.5" aria-hidden="true" />
        {label}
      </dt>
      <dd className="mt-2 text-sm break-words">{children}</dd>
    </div>
  )
}

export function DocumentDetailsPage() {
  const { documentId } = useParams()
  return <DocumentDetailsView key={documentId} documentId={documentId} />
}

function DocumentDetailsView({ documentId }) {
  const { user } = useAuth()
  const navigate = useNavigate()
  const [documentRecord, setDocumentRecord] = useState(null)
  const [isLoading, setIsLoading] = useState(true)
  const [loadError, setLoadError] = useState(null)
  const [actionError, setActionError] = useState(null)
  const [notice, setNotice] = useState(null)
  const [isEditing, setIsEditing] = useState(false)
  const [isEditingContent, setIsEditingContent] = useState(false)
  const [isReplacingFile, setIsReplacingFile] = useState(false)
  const [isDownloading, setIsDownloading] = useState(false)
  const [downloadingVersion, setDownloadingVersion] = useState(null)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [isDeleting, setIsDeleting] = useState(false)
  const [versions, setVersions] = useState([])
  const [isLoadingVersions, setIsLoadingVersions] = useState(true)
  const [versionsError, setVersionsError] = useState(null)
  const [versionsRefreshKey, setVersionsRefreshKey] = useState(0)
  const [refreshKey, setRefreshKey] = useState(0)
  const {
    register,
    handleSubmit,
    reset,
    setError,
    clearErrors,
    formState: { errors, isSubmitting },
  } = useForm({
    defaultValues: { name: '', category: '', description: '' },
  })

  useEffect(() => {
    const controller = new AbortController()

    getDocument(documentId, controller.signal)
      .then((payload) => {
        setDocumentRecord(payload)
        reset({
          name: payload.name,
          category: payload.category || '',
          description: payload.description || '',
        })
      })
      .catch((error) => {
        if (!isAbortError(error)) {
          setDocumentRecord(null)
          setLoadError(error)
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setIsLoading(false)
        }
      })

    return () => controller.abort()
  }, [documentId, refreshKey, reset])

  const canRead = canReadDocument(documentRecord)
  const canEdit = canEditDocument(documentRecord)
  const canEditContent = canEditTextContent(documentRecord)
  const canReplaceFile = canReplaceDocumentFile(documentRecord)
  const canDelete = canDeleteDocument(documentRecord)
  const canManagePermissions = canManageDocumentPermissions(documentRecord)
  const isMetadataOnly = documentRecord?.access_level === 'ADMINISTRATOR'
  const accessMeta = ACCESS_LEVEL_META[documentRecord?.access_level]
  const isNotFound = loadError?.response?.status === 404
  const recordId = documentRecord?.id
  const currentVersion = versions.find((version) => version.is_current) ?? null

  useEffect(() => {
    if (!recordId || !canRead) {
      return undefined
    }

    const controller = new AbortController()

    listDocumentVersions(recordId, controller.signal)
      .then((payload) => {
        setVersions(payload.items)
      })
      .catch((error) => {
        if (!isAbortError(error)) {
          setVersions([])
          setVersionsError(getApiErrorMessage(error))
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setIsLoadingVersions(false)
        }
      })

    return () => controller.abort()
  }, [canRead, recordId, versionsRefreshKey])

  function refreshVersions() {
    setIsLoadingVersions(true)
    setVersionsError(null)
    setVersionsRefreshKey((key) => key + 1)
  }

  function applyVersionResult(result) {
    setDocumentRecord(result.document)
    setVersions((current) => [
      result.version,
      ...current
        .filter((version) => version.id !== result.version.id)
        .map((version) => ({ ...version, is_current: false })),
    ])
    setIsEditingContent(false)
    setIsReplacingFile(false)
    setActionError(null)
    setNotice(`Version ${result.version.version_number} created.`)
  }

  function handleVersionConflict() {
    refreshVersions()
    setNotice('The version history was refreshed because a newer version exists.')
  }

  const onSubmit = async (values) => {
    setActionError(null)
    setNotice(null)

    const result = editSchema.safeParse(values)
    if (!result.success) {
      clearErrors()
      for (const issue of result.error.issues) {
        const field = issue.path[0]
        if (field === 'name' || field === 'category' || field === 'description') {
          setError(field, { type: 'manual', message: issue.message })
        }
      }
      return
    }

    try {
      const updated = await updateDocument(documentRecord.id, {
        name: result.data.name,
        category: result.data.category || null,
        description: result.data.description || null,
      })
      setDocumentRecord(updated)
      reset({
        name: updated.name,
        category: updated.category || '',
        description: updated.description || '',
      })
      setIsEditing(false)
      setNotice('Document metadata updated.')
    } catch (error) {
      setActionError(getApiErrorMessage(error))
    }
  }

  async function handleDownload() {
    setActionError(null)
    setIsDownloading(true)
    try {
      const { blob, filename } = await downloadDocument(documentRecord.id, documentRecord.name)
      saveBlob(blob, filename)
    } catch (error) {
      setActionError(getApiErrorMessage(error))
    } finally {
      setIsDownloading(false)
    }
  }

  async function handleVersionDownload(version) {
    setActionError(null)
    setDownloadingVersion(version.version_number)
    try {
      const { blob, filename } = await downloadDocumentVersion(
        documentRecord.id,
        version.version_number,
        version.original_filename,
      )
      saveBlob(blob, filename)
    } catch (error) {
      setActionError(getApiErrorMessage(error))
    } finally {
      setDownloadingVersion(null)
    }
  }

  async function handleDelete() {
    setActionError(null)
    setIsDeleting(true)
    try {
      await deleteDocument(documentRecord.id)
      navigate('/documents', {
        replace: true,
        state: { notice: `${documentRecord.name} was deleted.` },
      })
    } catch (error) {
      setActionError(getApiErrorMessage(error))
      setIsDeleting(false)
    }
  }

  if (isLoading) {
    return (
      <div className="flex min-h-80 items-center justify-center gap-3 text-sm text-muted-foreground">
        <LoaderCircle className="size-5 animate-spin" aria-hidden="true" />
        Loading document details...
      </div>
    )
  }

  if (isNotFound || (!loadError && !documentRecord)) {
    return (
      <div className="flex flex-col items-center justify-center gap-6 py-20 text-center">
        <span className="flex size-16 items-center justify-center rounded-2xl bg-muted text-muted-foreground">
          <FileText className="size-8" aria-hidden="true" />
        </span>
        <div className="space-y-3">
          <p className="text-xs font-semibold tracking-[0.2em] text-primary uppercase">
            Document unavailable
          </p>
          <h1 className="text-3xl font-semibold tracking-tight">Document not found</h1>
          <p className="mx-auto max-w-md text-sm leading-6 text-muted-foreground">
            The document does not exist, was deleted, or is not visible to your account.
          </p>
        </div>
        <Link to="/documents" className={buttonVariants({ variant: 'outline' })}>
          <ArrowLeft className="size-4" aria-hidden="true" />
          Back to documents
        </Link>
      </div>
    )
  }

  if (loadError) {
    return (
      <div
        role="alert"
        className="flex flex-col items-start gap-4 rounded-lg border border-destructive/30 bg-destructive/5 px-6 py-6 text-sm text-destructive"
      >
        <p>{getApiErrorMessage(loadError)}</p>
        <Button
          type="button"
          variant="outline"
          onClick={() => {
            setIsLoading(true)
            setLoadError(null)
            setRefreshKey((key) => key + 1)
          }}
        >
          <RefreshCw className="size-4" aria-hidden="true" />
          Retry
        </Button>
      </div>
    )
  }

  return (
    <div className="space-y-8">
      <Link
        to="/documents"
        className="inline-flex items-center gap-2 text-sm font-medium text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="size-4" aria-hidden="true" />
        Back to document library
      </Link>

      <PageHeader
        eyebrow="Document details"
        title={documentRecord.name}
        description={`${documentRecord.category || 'Uncategorized'} · ${formatBytes(
          documentRecord.file_size,
        )} · ${documentRecord.mime_type}`}
        actions={
          <>
            <AccessLevelBadge accessLevel={documentRecord.access_level} />
            {canRead ? (
              <Button
                type="button"
                variant="outline"
                onClick={handleDownload}
                disabled={isDownloading}
              >
                {isDownloading ? (
                  <LoaderCircle className="size-4 animate-spin" aria-hidden="true" />
                ) : (
                  <Download className="size-4" aria-hidden="true" />
                )}
                {isDownloading ? 'Preparing...' : 'Download'}
              </Button>
            ) : null}
            {canEdit ? (
              <Button
                type="button"
                variant="outline"
                onClick={() => {
                  setIsEditing((editing) => !editing)
                  setIsEditingContent(false)
                  setIsReplacingFile(false)
                  setActionError(null)
                  setNotice(null)
                }}
              >
                {isEditing ? (
                  <X className="size-4" aria-hidden="true" />
                ) : (
                  <Pencil className="size-4" aria-hidden="true" />
                )}
                {isEditing ? 'Cancel metadata edit' : 'Edit metadata'}
              </Button>
            ) : null}
            {canEditContent ? (
              <Button
                type="button"
                variant="outline"
                onClick={() => {
                  setIsEditingContent((editing) => !editing)
                  setIsEditing(false)
                  setIsReplacingFile(false)
                  setActionError(null)
                  setNotice(null)
                }}
                disabled={!currentVersion || isLoadingVersions}
              >
                {isEditingContent ? (
                  <X className="size-4" aria-hidden="true" />
                ) : (
                  <PencilLine className="size-4" aria-hidden="true" />
                )}
                {isEditingContent ? 'Cancel text edit' : 'Edit text'}
              </Button>
            ) : null}
            {canReplaceFile ? (
              <Button
                type="button"
                variant="outline"
                onClick={() => {
                  setIsReplacingFile((replacing) => !replacing)
                  setIsEditing(false)
                  setIsEditingContent(false)
                  setActionError(null)
                  setNotice(null)
                }}
                disabled={!currentVersion || isLoadingVersions}
              >
                {isReplacingFile ? (
                  <X className="size-4" aria-hidden="true" />
                ) : (
                  <FileUp className="size-4" aria-hidden="true" />
                )}
                {isReplacingFile ? 'Cancel new version' : 'New version'}
              </Button>
            ) : null}
            {canManagePermissions ? (
              <Link
                to={`/documents/${documentRecord.id}/permissions`}
                className={buttonVariants({ variant: 'outline' })}
              >
                <KeyRound className="size-4" aria-hidden="true" />
                Manage access
              </Link>
            ) : null}
            {canDelete ? (
              <Button
                type="button"
                variant="destructive"
                onClick={() => {
                  setConfirmDelete(true)
                  setActionError(null)
                  setNotice(null)
                }}
              >
                <Trash2 className="size-4" aria-hidden="true" />
                Delete
              </Button>
            ) : null}
          </>
        }
      />

      {isMetadataOnly ? (
        <div className="flex items-start gap-3 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          <ShieldAlert className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
          <p>
            Administrator metadata review only. Document content, metadata changes, deletion, and
            sharing require an explicit READ or EDIT grant from the owner.
          </p>
        </div>
      ) : null}

      {notice ? (
        <div
          role="status"
          className="rounded-lg border border-emerald-200 bg-emerald-50/70 px-4 py-3 text-sm text-emerald-900"
        >
          {notice}
        </div>
      ) : null}

      {actionError ? (
        <div
          role="alert"
          className="rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive"
        >
          {actionError}
        </div>
      ) : null}

      {isEditingContent && canEditContent ? (
        <DocumentTextEditor
          documentRecord={documentRecord}
          currentVersion={currentVersion}
          onSaved={applyVersionResult}
          onConflict={handleVersionConflict}
          onCancel={() => setIsEditingContent(false)}
        />
      ) : null}

      {isReplacingFile && canReplaceFile ? (
        <ReplaceDocumentVersion
          documentRecord={documentRecord}
          currentVersion={currentVersion}
          onReplaced={applyVersionResult}
          onConflict={handleVersionConflict}
          onCancel={() => setIsReplacingFile(false)}
        />
      ) : null}

      {confirmDelete && canDelete ? (
        <Card className="border-destructive/30">
          <CardContent className="flex flex-col gap-4 px-6 py-5 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h2 className="font-semibold">Delete this document?</h2>
              <p className="mt-1 text-sm text-muted-foreground">
                The document will be removed from the library and cleanup of its private object
                will be attempted. Metadata is retained for history, but the document cannot be
                restored from this interface.
              </p>
            </div>
            <div className="flex shrink-0 flex-wrap gap-2">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setConfirmDelete(false)}
                disabled={isDeleting}
              >
                Cancel
              </Button>
              <Button
                type="button"
                variant="destructive"
                size="sm"
                onClick={handleDelete}
                disabled={isDeleting}
              >
                {isDeleting ? (
                  <LoaderCircle className="size-4 animate-spin" aria-hidden="true" />
                ) : (
                  <Trash2 className="size-4" aria-hidden="true" />
                )}
                {isDeleting ? 'Deleting...' : 'Delete document'}
              </Button>
            </div>
          </CardContent>
        </Card>
      ) : null}

      {canRead ? (
        <Card>
          <CardHeader>
            <CardTitle>Secure content preview</CardTitle>
            <p className="mt-1 text-sm text-muted-foreground">
              Content is fetched through the authenticated API. Storage keys and private
              object URLs are never sent to the browser.
            </p>
          </CardHeader>
          <CardContent>
            <DocumentPreview
              key={`${documentRecord.id}-${documentRecord.checksum}`}
              documentRecord={documentRecord}
            />
          </CardContent>
        </Card>
      ) : null}

      <div className="grid gap-5 lg:grid-cols-[2fr_1fr]">
        <Card>
          <CardHeader>
            <CardTitle>Document metadata</CardTitle>
          </CardHeader>
          <CardContent>
            <dl className="grid gap-6 sm:grid-cols-2">
              <MetadataItem icon={UserRound} label="Owner">
                {documentRecord.owner_name}
                {documentRecord.owner_id === user?.id ? (
                  <span className="ml-2 text-xs text-muted-foreground">(you)</span>
                ) : null}
                <span className="mt-1 block font-mono text-xs text-muted-foreground break-all">
                  {documentRecord.owner_id}
                </span>
              </MetadataItem>
              <MetadataItem icon={FileText} label="Category">
                {documentRecord.category || 'Uncategorized'}
              </MetadataItem>
              <MetadataItem icon={HardDrive} label="File size">
                {formatBytes(documentRecord.file_size)}
              </MetadataItem>
              <MetadataItem icon={FileText} label="MIME type">
                {documentRecord.mime_type}
              </MetadataItem>
              <MetadataItem icon={CalendarDays} label="Created">
                {formatDateTime(documentRecord.created_at)}
              </MetadataItem>
              <MetadataItem icon={CalendarDays} label="Last updated">
                {formatDateTime(documentRecord.updated_at)}
              </MetadataItem>
              <MetadataItem icon={Fingerprint} label="SHA-256 checksum" className="sm:col-span-2">
                <span className="font-mono text-xs break-all">{documentRecord.checksum}</span>
              </MetadataItem>
              <MetadataItem icon={FileText} label="Description" className="sm:col-span-2">
                <span className="whitespace-pre-wrap">
                  {documentRecord.description || 'No description provided.'}
                </span>
              </MetadataItem>
            </dl>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Your access</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4 text-sm leading-6 text-muted-foreground">
            <div className="flex items-start gap-3">
              <ShieldCheck className="mt-0.5 size-4 shrink-0 text-primary" aria-hidden="true" />
              <div>
                <p className="font-medium text-foreground">{accessMeta?.label ?? 'No access'}</p>
                <p>{accessMeta?.description ?? 'Your account cannot access this document.'}</p>
              </div>
            </div>
            <p>
              The backend resolves ownership and active grants from the database on every request.
              Revoked access is denied immediately for previews, version history, and downloads.
            </p>
            <p>
              Storage keys and private object URLs are never exposed. Downloads are proxied through
              the authenticated API.
            </p>
            {canManagePermissions ? (
              <Link
                to={`/documents/${documentRecord.id}/permissions`}
                className="inline-flex items-center gap-2 font-medium text-primary underline-offset-4 hover:underline"
              >
                <KeyRound className="size-4" aria-hidden="true" />
                Manage document access
              </Link>
            ) : null}
          </CardContent>
        </Card>
      </div>

      {canRead ? (
        <VersionHistory
          versions={versions}
          currentVersionNumber={currentVersion?.version_number ?? null}
          isLoading={isLoadingVersions}
          error={versionsError}
          onRefresh={refreshVersions}
          onDownload={handleVersionDownload}
          downloadingVersion={downloadingVersion}
        />
      ) : null}

      {isEditing && canEdit ? (
        <Card>
          <CardHeader>
            <CardTitle>Edit metadata</CardTitle>
          </CardHeader>
          <CardContent>
            <form className="grid gap-5" onSubmit={handleSubmit(onSubmit)}>
              <div className="space-y-2">
                <label htmlFor="edit-name" className="text-sm font-medium">
                  Document name
                </label>
                <input
                  id="edit-name"
                  type="text"
                  maxLength={255}
                  className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-xs focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                  disabled={isSubmitting}
                  aria-invalid={errors.name ? true : undefined}
                  aria-describedby={errors.name ? 'edit-name-error' : undefined}
                  {...register('name')}
                />
                {errors.name ? (
                  <p id="edit-name-error" className="text-sm text-destructive">
                    {errors.name.message}
                  </p>
                ) : null}
              </div>

              <div className="grid gap-5 sm:grid-cols-2">
                <div className="space-y-2">
                  <label htmlFor="edit-category" className="text-sm font-medium">
                    Category
                  </label>
                  <input
                    id="edit-category"
                    type="text"
                    maxLength={100}
                    list="edit-category-options"
                    className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-xs focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                    disabled={isSubmitting}
                    aria-invalid={errors.category ? true : undefined}
                    aria-describedby={errors.category ? 'edit-category-error' : undefined}
                    {...register('category')}
                  />
                  <datalist id="edit-category-options">
                    {categoryChoices(documentRecord.category).map((category) => (
                      <option key={category} value={category} />
                    ))}
                  </datalist>
                  {errors.category ? (
                    <p id="edit-category-error" className="text-sm text-destructive">
                      {errors.category.message}
                    </p>
                  ) : null}
                </div>

                <div className="space-y-2 sm:row-span-2">
                  <label htmlFor="edit-description" className="text-sm font-medium">
                    Description
                  </label>
                  <textarea
                    id="edit-description"
                    rows={4}
                    maxLength={2000}
                    className="flex min-h-24 w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-xs focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                    disabled={isSubmitting}
                    aria-invalid={errors.description ? true : undefined}
                    aria-describedby={errors.description ? 'edit-description-error' : undefined}
                    {...register('description')}
                  />
                  {errors.description ? (
                    <p id="edit-description-error" className="text-sm text-destructive">
                      {errors.description.message}
                    </p>
                  ) : null}
                </div>
              </div>

              <div className="flex flex-wrap gap-3">
                <Button type="submit" disabled={isSubmitting}>
                  {isSubmitting ? (
                    <LoaderCircle className="size-4 animate-spin" aria-hidden="true" />
                  ) : (
                    <ShieldCheck className="size-4" aria-hidden="true" />
                  )}
                  {isSubmitting ? 'Saving...' : 'Save changes'}
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => {
                    setIsEditing(false)
                    setActionError(null)
                    reset({
                      name: documentRecord.name,
                      category: documentRecord.category || '',
                      description: documentRecord.description || '',
                    })
                  }}
                  disabled={isSubmitting}
                >
                  Cancel
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>
      ) : null}
    </div>
  )
}
