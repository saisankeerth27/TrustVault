import {
  Clock3,
  Download,
  History,
  LoaderCircle,
  RefreshCw,
  UserRound,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { formatBytes, formatDateTime } from '@/lib/documents'
import { cn } from '@/lib/utils'

export function VersionHistory({
  versions,
  currentVersionNumber,
  isLoading,
  error,
  onRefresh,
  onDownload,
  downloadingVersion,
}) {
  return (
    <Card>
      <CardHeader className="flex-row items-start justify-between gap-4">
        <div>
          <CardTitle className="flex items-center gap-2">
            <History className="size-4 text-primary" aria-hidden="true" />
            Version history
          </CardTitle>
          <p className="mt-1 text-sm text-muted-foreground">
            Every replacement is retained with its uploader, checksum, and timestamp.
          </p>
        </div>
        <Button type="button" variant="outline" size="sm" onClick={onRefresh}>
          <RefreshCw className="size-4" aria-hidden="true" />
          Refresh
        </Button>
      </CardHeader>
      <CardContent>
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
              return (
                <li
                  key={version.id}
                  className={cn(
                    'rounded-lg border px-4 py-4',
                    version.is_current && 'border-primary/30 bg-primary/5',
                  )}
                >
                  <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                    <div className="min-w-0 space-y-2">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-medium">
                          Version {version.version_number}
                        </span>
                        {version.is_current ? (
                          <span className="rounded-full bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary ring-1 ring-primary/20 ring-inset">
                            Current
                          </span>
                        ) : null}
                      </div>
                      <p className="text-sm break-words">
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
                        <span>{formatBytes(version.file_size)}</span>
                        <span>{version.original_filename}</span>
                      </div>
                      <p
                        className="font-mono text-[11px] break-all text-muted-foreground"
                        title={version.checksum}
                      >
                        SHA-256 {version.checksum}
                      </p>
                    </div>
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={() => onDownload(version)}
                      disabled={Boolean(downloadingVersion)}
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
                  </div>
                </li>
              )
            })}
          </ol>
        )}

        {currentVersionNumber ? (
          <p className="mt-4 text-xs text-muted-foreground">
            Current version: {currentVersionNumber}
          </p>
        ) : null}
      </CardContent>
    </Card>
  )
}
