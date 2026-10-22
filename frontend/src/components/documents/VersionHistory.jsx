import { useState } from 'react'
import {
  AlertTriangle,
  Clock3,
  Download,
  HardDrive,
  History,
  LoaderCircle,
  RefreshCw,
  Trash2,
  UserRound,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { formatBytes, formatDateTime } from '@/lib/documents'
import { cn } from '@/lib/utils'

export function VersionHistory({
  versions = [],
  currentVersionNumber,
  totalSize,
  isLoading,
  error,
  actionError,
  onRefresh,
  onDownload,
  downloadingVersion,
  canDeleteVersion = false,
  onDeleteVersion,
  deletingVersion,
}) {
  const [confirmingVersion, setConfirmingVersion] = useState(null)

  const hasMultipleVersions = versions.length > 1

  async function handleConfirmDelete() {
    if (!confirmingVersion || !onDeleteVersion) return
    const target = confirmingVersion
    try {
      await onDeleteVersion(target)
      setConfirmingVersion(null)
    } catch {
      // error handled by parent page
    }
  }

  return (
    <Card>
      <CardHeader className="flex-row items-start justify-between gap-4">
        <div>
          <CardTitle className="flex items-center gap-2">
            <History className="size-4 text-primary" aria-hidden="true" />
            Version history
          </CardTitle>
          <p className="mt-1 text-sm text-muted-foreground">
            Every file revision is preserved with its author, checksum, and size. Historical
            versions can be downloaded or safely pruned by the document owner.
          </p>
        </div>
        <div className="flex items-center gap-3">
          {Number.isFinite(totalSize) && totalSize >= 0 ? (
            <span className="hidden items-center gap-1.5 rounded-md border bg-muted/30 px-2.5 py-1 text-xs text-muted-foreground sm:inline-flex">
              <HardDrive className="size-3.5" aria-hidden="true" />
              Total storage: <strong className="font-medium text-foreground">{formatBytes(totalSize)}</strong>
            </span>
          ) : null}
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={onRefresh}
            disabled={isLoading}
          >
            <RefreshCw className={cn('size-4', isLoading && 'animate-spin')} aria-hidden="true" />
            Refresh
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {actionError ? (
          <div
            role="alert"
            className="rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive"
          >
            {actionError}
          </div>
        ) : null}

        {isLoading ? (
          <div className="space-y-3" aria-busy="true" aria-live="polite">
            {[0, 1].map((row) => (
              <div key={row} className="space-y-2 rounded-lg border p-4">
                <div className="h-3 w-1/3 animate-pulse rounded bg-muted" />
                <div className="h-3 w-2/3 animate-pulse rounded bg-muted" />
              </div>
            ))}
          </div>
        ) : error ? (
          <div
            role="alert"
            className="rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive"
          >
            {error}
          </div>
        ) : versions.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No content versions are recorded for this document.
          </p>
        ) : (
          <ol className="space-y-3">
            {versions.map((version) => {
              const isDownloading = downloadingVersion === version.version_number
              const isDeleting = deletingVersion === version.version_number
              const isHistorical = !version.is_current
              const allowDelete = canDeleteVersion && isHistorical && hasMultipleVersions

              return (
                <li
                  key={version.id}
                  className={cn(
                    'rounded-lg border px-4 py-4 transition-colors',
                    version.is_current ? 'border-primary/30 bg-primary/5' : 'bg-card',
                  )}
                >
                  <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                    <div className="min-w-0 space-y-2">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-semibold text-foreground">
                          Version {version.version_number}
                        </span>
                        {version.is_current ? (
                          <span className="rounded-full bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary ring-1 ring-primary/20 ring-inset">
                            Current version
                          </span>
                        ) : (
                          <span className="rounded-full bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground ring-1 ring-border ring-inset">
                            Historical revision
                          </span>
                        )}
                      </div>

                      <p className="text-sm text-foreground break-words">
                        {version.change_summary || 'No change summary provided.'}
                      </p>

                      <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
                        <span className="inline-flex items-center gap-1.5">
                          <Clock3 className="size-3.5" aria-hidden="true" />
                          {formatDateTime(version.created_at)}
                        </span>
                        <span className="inline-flex items-center gap-1.5">
                          <UserRound className="size-3.5" aria-hidden="true" />
                          {version.uploader_name}
                        </span>
                        <span className="font-medium text-foreground">
                          {formatBytes(version.file_size)}
                        </span>
                        <span>{version.original_filename}</span>
                      </div>

                      <p
                        className="font-mono text-[11px] break-all text-muted-foreground"
                        title={version.checksum}
                      >
                        SHA-256 {version.checksum}
                      </p>
                    </div>

                    <div className="flex shrink-0 items-center gap-2">
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        onClick={() => onDownload(version)}
                        disabled={Boolean(downloadingVersion) || Boolean(deletingVersion)}
                        aria-label={`Download version ${version.version_number}`}
                      >
                        {isDownloading ? (
                          <LoaderCircle
                            className="size-4 animate-spin"
                            aria-hidden="true"
                          />
                        ) : (
                          <Download className="size-4" aria-hidden="true" />
                        )}
                        {isDownloading ? 'Downloading...' : 'Download'}
                      </Button>

                      {allowDelete ? (
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          onClick={() => setConfirmingVersion(version)}
                          disabled={Boolean(deletingVersion) || Boolean(downloadingVersion)}
                          aria-label={`Delete historical version ${version.version_number}`}
                          className="text-destructive hover:bg-destructive/10 hover:text-destructive"
                        >
                          {isDeleting ? (
                            <LoaderCircle
                              className="size-4 animate-spin"
                              aria-hidden="true"
                            />
                          ) : (
                            <Trash2 className="size-4" aria-hidden="true" />
                          )}
                          Delete
                        </Button>
                      ) : null}
                    </div>
                  </div>
                </li>
              )
            })}
          </ol>
        )}

        {/* Confirmation Dialog for Historical Version Deletion */}
        {confirmingVersion ? (
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="confirm-version-delete-title"
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
          >
            <div className="w-full max-w-md rounded-xl border bg-background p-6 shadow-xl space-y-4">
              <div className="flex items-start gap-3">
                <span className="flex size-10 shrink-0 items-center justify-center rounded-full bg-destructive/10 text-destructive">
                  <AlertTriangle className="size-5" aria-hidden="true" />
                </span>
                <div className="space-y-1">
                  <h3 id="confirm-version-delete-title" className="font-semibold text-foreground">
                    Delete Version {confirmingVersion.version_number}?
                  </h3>
                  <p className="text-sm text-muted-foreground leading-5">
                    You are deleting historical Version {confirmingVersion.version_number} (
                    <strong className="text-foreground">{confirmingVersion.original_filename}</strong>,{' '}
                    {formatBytes(confirmingVersion.file_size)}).
                  </p>
                </div>
              </div>

              <p className="text-xs text-muted-foreground bg-muted/40 p-3 rounded-md">
                This will safely delete the specific object from private storage and update your retained storage total. The audit record of this revision and its deletion will be preserved. Other versions will remain intact.
              </p>

              <div className="flex justify-end gap-3 pt-2">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => setConfirmingVersion(null)}
                  disabled={Boolean(deletingVersion)}
                >
                  Cancel
                </Button>
                <Button
                  type="button"
                  variant="destructive"
                  size="sm"
                  onClick={handleConfirmDelete}
                  disabled={Boolean(deletingVersion)}
                >
                  {deletingVersion === confirmingVersion.version_number ? (
                    <LoaderCircle className="size-4 animate-spin" aria-hidden="true" />
                  ) : (
                    <Trash2 className="size-4" aria-hidden="true" />
                  )}
                  {deletingVersion === confirmingVersion.version_number
                    ? 'Deleting...'
                    : 'Confirm deletion'}
                </Button>
              </div>
            </div>
          </div>
        ) : null}

        {currentVersionNumber ? (
          <p className="text-xs text-muted-foreground">
            Current active version: <strong>Version {currentVersionNumber}</strong>
          </p>
        ) : null}
      </CardContent>
    </Card>
  )
}
