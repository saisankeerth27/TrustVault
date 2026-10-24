import { useEffect, useState } from 'react'
import {
  ArrowLeft,
  CalendarDays,
  Download,
  FileText,
  FileUp,
  HardDrive,
  KeyRound,
  LoaderCircle,
  PencilLine,
  RefreshCw,
  ShieldAlert,
  Trash2,
  UserRound,
  X,
} from 'lucide-react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { AccessLevelBadge } from '@/components/documents/AccessLevelBadge'
import { DocumentActivityHistory } from '@/components/documents/DocumentActivityHistory'
import { DocumentDocxEditor } from '@/components/documents/DocumentDocxEditor'
import { DocumentPreview } from '@/components/documents/DocumentPreview'
import { DocumentTextEditor } from '@/components/documents/DocumentTextEditor'
import { ImageAnnotationEditor } from '@/components/documents/ImageAnnotationEditor'
import { PdfAnnotationEditor } from '@/components/documents/PdfAnnotationEditor'
import { ReplaceDocumentVersion } from '@/components/documents/ReplaceDocumentVersion'
import { VersionHistory } from '@/components/documents/VersionHistory'
import { PageHeader } from '@/components/PageHeader'
import { Button } from '@/components/ui/button'
import { buttonVariants } from '@/components/ui/button-variants'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  canDeleteDocument,
  canDeleteHistoricalVersion,
  canEditDocxContent,
  canEditImageContent,
  canEditPdfContent,
  canEditTextContent,
  canManageDocumentPermissions,
  canReadDocument,
  canReplaceDocumentFile,
  formatBytes,
  formatDateTime,
  saveBlob,
} from '@/lib/documents'
import { getApiErrorMessage } from '@/services/api'
import {
  deleteDocument,
  deleteDocumentVersion,
  downloadDocument,
  downloadDocumentVersion,
  getDocument,
  listDocumentVersions,
  previewDocument,
} from '@/services/documents'

const VERSION_PAGE_SIZE = 5

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
  const navigate = useNavigate()
  const [documentRecord, setDocumentRecord] = useState(null)
  const [isLoading, setIsLoading] = useState(true)
  const [loadError, setLoadError] = useState(null)
  const [actionError, setActionError] = useState(null)
  const [notice, setNotice] = useState(null)
  const [activeEditor, setActiveEditor] = useState(null)
  const [editorBlob, setEditorBlob] = useState(null)
  const [isLoadingEditorBlob, setIsLoadingEditorBlob] = useState(false)
  const [editorBlobError, setEditorBlobError] = useState(null)
  const [isDownloading, setIsDownloading] = useState(false)
  const [downloadingVersion, setDownloadingVersion] = useState(null)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [isDeleting, setIsDeleting] = useState(false)
  const [versions, setVersions] = useState([])
  const [currentVersion, setCurrentVersion] = useState(null)
  const [versionPage, setVersionPage] = useState(1)
  const [versionPages, setVersionPages] = useState(0)
  const [versionTotal, setVersionTotal] = useState(0)
  const [versionTotalSize, setVersionTotalSize] = useState(0)
  const [isLoadingVersions, setIsLoadingVersions] = useState(true)
  const [versionsError, setVersionsError] = useState(null)
  const [versionsRefreshKey, setVersionsRefreshKey] = useState(0)
  const [versionActionError, setVersionActionError] = useState(null)
  const [deletingVersion, setDeletingVersion] = useState(null)
  const [activityRefreshKey, setActivityRefreshKey] = useState(0)
  const [refreshKey, setRefreshKey] = useState(0)

  useEffect(() => {
    const controller = new AbortController()

    getDocument(documentId, controller.signal)
      .then((payload) => {
        setDocumentRecord(payload)
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
  }, [documentId, refreshKey])

  const canRead = canReadDocument(documentRecord)
  const canEditContent = canEditTextContent(documentRecord)
  const canEditPdf = canEditPdfContent(documentRecord)
  const canEditDocx = canEditDocxContent(documentRecord)
  const canEditImage = canEditImageContent(documentRecord)
  const canReplaceFile = canReplaceDocumentFile(documentRecord)
  const canDelete = canDeleteDocument(documentRecord)
  const canManagePermissions = canManageDocumentPermissions(documentRecord)
  const canDeleteVersion = canDeleteHistoricalVersion(documentRecord)
  const isMetadataOnly = documentRecord?.access_level === 'ADMINISTRATOR'
  const isNotFound = loadError?.response?.status === 404
  const recordId = documentRecord?.id

  const needsEditorBlob =
    activeEditor === 'pdf' || activeEditor === 'docx' || activeEditor === 'image'

  useEffect(() => {
    if (!needsEditorBlob || !recordId || editorBlob) {
      return undefined
    }

    const controller = new AbortController()
    setIsLoadingEditorBlob(true)
    setEditorBlobError(null)

    previewDocument(recordId, controller.signal)
      .then(({ blob }) => {
        setEditorBlob(blob)
      })
      .catch((err) => {
        if (!isAbortError(err)) {
          setEditorBlobError(getApiErrorMessage(err))
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setIsLoadingEditorBlob(false)
        }
      })

    return () => controller.abort()
  }, [needsEditorBlob, recordId, editorBlob])

  useEffect(() => {
    if (!recordId || !canRead) {
      return undefined
    }

    const controller = new AbortController()
    setIsLoadingVersions(true)
    setVersionsError(null)

    listDocumentVersions(
      recordId,
      { page: versionPage, page_size: VERSION_PAGE_SIZE },
      controller.signal,
    )
      .then((payload) => {
        setVersions(payload.items || [])
        setCurrentVersion(
          payload.current_version ??
            (payload.items || []).find((version) => version.is_current) ??
            null,
        )
        setVersionPages(payload.pages || 0)
        setVersionTotal(payload.total || 0)
        setVersionTotalSize(payload.total_size || 0)
        if (payload.pages > 0 && versionPage > payload.pages) {
          setVersionPage(payload.pages)
        }
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
  }, [canRead, recordId, versionPage, versionsRefreshKey])

  function refreshVersions() {
    setIsLoadingVersions(true)
    setVersionsError(null)
    setVersionsRefreshKey((key) => key + 1)
  }

  function applyVersionResult(result) {
    setDocumentRecord(result.document)
    setCurrentVersion(result.version)
    setActiveEditor(null)
    setEditorBlob(null)
    setEditorBlobError(null)
    setActionError(null)
    setNotice(`Version ${result.version.version_number} created.`)
    setVersionPage(1)
    setActivityRefreshKey((key) => key + 1)
    refreshVersions()
  }

  function toggleEditor(kind) {
    setActiveEditor((current) => (current === kind ? null : kind))
    setEditorBlob(null)
    setEditorBlobError(null)
    setActionError(null)
    setNotice(null)
  }

  function handleVersionConflict() {
    setVersionPage(1)
    refreshVersions()
    setNotice('The version history was refreshed because a newer version exists.')
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

  async function handleVersionDelete(version) {
    setVersionActionError(null)
    setDeletingVersion(version.version_number)
    try {
      const result = await deleteDocumentVersion(
        documentRecord.id,
        version.version_number,
      )
      const remaining = Math.max(0, versionTotal - 1)
      const nextPages = Math.ceil(remaining / VERSION_PAGE_SIZE)
      setDocumentRecord(result.document)
      setCurrentVersion(result.current_version)
      setVersionTotal(remaining)
      setVersionPages(nextPages)
      setVersionTotalSize(result.retained_total_size)
      setVersionPage(Math.min(versionPage, Math.max(1, nextPages)))
      setActivityRefreshKey((key) => key + 1)
      refreshVersions()
      setNotice(
        result.rolled_back
          ? `Version ${version.version_number} deleted. The document rolled back to Version ${result.current_version.version_number}.`
          : `Version ${version.version_number} deleted. Storage freed: ${result.storage_deleted ? 'Yes' : 'No'}.`,
      )
    } catch (error) {
      setVersionActionError(getApiErrorMessage(error))
    } finally {
      setDeletingVersion(null)
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
            {canEditContent ? (
              <Button
                type="button"
                variant="outline"
                onClick={() => toggleEditor('text')}
                disabled={!currentVersion || isLoadingVersions}
              >
                {activeEditor === 'text' ? (
                  <X className="size-4" aria-hidden="true" />
                ) : (
                  <PencilLine className="size-4" aria-hidden="true" />
                )}
                {activeEditor === 'text' ? 'Cancel text edit' : 'Edit text'}
              </Button>
            ) : null}
            {canEditPdf ? (
              <Button
                type="button"
                variant="outline"
                onClick={() => toggleEditor('pdf')}
                disabled={!currentVersion || isLoadingVersions}
              >
                {activeEditor === 'pdf' ? (
                  <X className="size-4" aria-hidden="true" />
                ) : (
                  <PencilLine className="size-4" aria-hidden="true" />
                )}
                {activeEditor === 'pdf' ? 'Cancel PDF edit' : 'Edit PDF'}
              </Button>
            ) : null}
            {canEditDocx ? (
              <Button
                type="button"
                variant="outline"
                onClick={() => toggleEditor('docx')}
                disabled={!currentVersion || isLoadingVersions}
              >
                {activeEditor === 'docx' ? (
                  <X className="size-4" aria-hidden="true" />
                ) : (
                  <PencilLine className="size-4" aria-hidden="true" />
                )}
                {activeEditor === 'docx' ? 'Cancel document edit' : 'Edit document'}
              </Button>
            ) : null}
            {canEditImage ? (
              <Button
                type="button"
                variant="outline"
                onClick={() => toggleEditor('image')}
                disabled={!currentVersion || isLoadingVersions}
              >
                {activeEditor === 'image' ? (
                  <X className="size-4" aria-hidden="true" />
                ) : (
                  <PencilLine className="size-4" aria-hidden="true" />
                )}
                {activeEditor === 'image' ? 'Cancel image edit' : 'Edit image'}
              </Button>
            ) : null}
            {canReplaceFile ? (
              <Button
                type="button"
                variant="outline"
                onClick={() => toggleEditor('replace')}
                disabled={!currentVersion || isLoadingVersions}
              >
                {activeEditor === 'replace' ? (
                  <X className="size-4" aria-hidden="true" />
                ) : (
                  <FileUp className="size-4" aria-hidden="true" />
                )}
                {activeEditor === 'replace' ? 'Cancel new version' : 'New version'}
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

      {activeEditor === 'text' && canEditContent ? (
        <DocumentTextEditor
          documentRecord={documentRecord}
          currentVersion={currentVersion}
          onSaved={applyVersionResult}
          onConflict={handleVersionConflict}
          onCancel={() => setActiveEditor(null)}
        />
      ) : null}

      {activeEditor === 'replace' && canReplaceFile ? (
        <ReplaceDocumentVersion
          documentRecord={documentRecord}
          currentVersion={currentVersion}
          onReplaced={applyVersionResult}
          onConflict={handleVersionConflict}
          onCancel={() => setActiveEditor(null)}
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

      {needsEditorBlob ? (
        isLoadingEditorBlob ? (
          <Card>
            <CardContent className="flex min-h-48 items-center justify-center gap-3 p-8 text-sm text-muted-foreground">
              <LoaderCircle className="size-5 animate-spin" aria-hidden="true" />
              Loading editable content...
            </CardContent>
          </Card>
        ) : editorBlobError ? (
          <div
            role="alert"
            className="rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive"
          >
            {editorBlobError}
          </div>
        ) : editorBlob ? (
          <>
            {activeEditor === 'pdf' && canEditPdf ? (
              <PdfAnnotationEditor
                blob={editorBlob}
                filename={documentRecord.name}
                documentRecord={documentRecord}
                currentVersion={currentVersion}
                onSaved={applyVersionResult}
                onConflict={handleVersionConflict}
                onCancel={() => setActiveEditor(null)}
              />
            ) : null}
            {activeEditor === 'docx' && canEditDocx ? (
              <DocumentDocxEditor
                blob={editorBlob}
                documentRecord={documentRecord}
                currentVersion={currentVersion}
                onSaved={applyVersionResult}
                onConflict={handleVersionConflict}
                onCancel={() => setActiveEditor(null)}
              />
            ) : null}
            {activeEditor === 'image' && canEditImage ? (
              <ImageAnnotationEditor
                blob={editorBlob}
                documentRecord={documentRecord}
                currentVersion={currentVersion}
                onSaved={applyVersionResult}
                onConflict={handleVersionConflict}
                onCancel={() => setActiveEditor(null)}
              />
            ) : null}
          </>
        ) : null
      ) : null}

      {!needsEditorBlob && canRead ? (
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
              key={`${documentRecord.id}-${documentRecord.updated_at}`}
              documentRecord={documentRecord}
            />
          </CardContent>
        </Card>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle>Document metadata</CardTitle>
        </CardHeader>
        <CardContent>
          <dl className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
            <MetadataItem icon={UserRound} label="Owner">
              {documentRecord.owner_name}
              {documentRecord.access_level === 'OWNER' ? (
                <span className="ml-2 text-xs text-muted-foreground">(you)</span>
              ) : null}
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
            <MetadataItem
              icon={FileText}
              label="Description"
              className="sm:col-span-2 lg:col-span-3"
            >
              <span className="whitespace-pre-wrap">
                {documentRecord.description || 'No description provided.'}
              </span>
            </MetadataItem>
          </dl>
        </CardContent>
      </Card>

      {canRead ? (
        <VersionHistory
          versions={versions}
          total={versionTotal}
          currentVersionNumber={currentVersion?.version_number ?? null}
          totalSize={versionTotalSize}
          page={versionPage}
          pageSize={VERSION_PAGE_SIZE}
          pages={versionPages}
          onPageChange={setVersionPage}
          isLoading={isLoadingVersions}
          error={versionsError}
          actionError={versionActionError}
          onRefresh={refreshVersions}
          onDownload={handleVersionDownload}
          downloadingVersion={downloadingVersion}
          canDeleteVersion={canDeleteVersion}
          onDeleteVersion={handleVersionDelete}
          deletingVersion={deletingVersion}
        />
      ) : null}

      {canDelete ? (
        <DocumentActivityHistory
          documentId={documentRecord.id}
          refreshKey={activityRefreshKey}
        />
      ) : null}

    </div>
  )
}
