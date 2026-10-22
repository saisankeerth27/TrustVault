import { useEffect, useState } from 'react'
import {
  Activity,
  ArrowRight,
  Clock3,
  Download,
  Eye,
  FileEdit,
  FilePlus,
  KeyRound,
  RefreshCw,
  ShieldAlert,
  Trash2,
  UserRound,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { formatAuditAction, outcomeMeta } from '@/lib/audit'
import { formatBytes, formatDateTime } from '@/lib/documents'
import { cn } from '@/lib/utils'
import { getApiErrorMessage } from '@/services/api'
import { listDocumentActivity } from '@/services/documents'

function ActionIcon({ action, outcome }) {
  if (outcome === 'DENIED') {
    return <ShieldAlert className="size-4 text-amber-600" aria-hidden="true" />
  }
  switch (action) {
    case 'DOCUMENT_UPLOAD':
      return <FilePlus className="size-4 text-primary" aria-hidden="true" />
    case 'DOCUMENT_METADATA_UPDATE':
      return <FileEdit className="size-4 text-sky-600" aria-hidden="true" />
    case 'DOCUMENT_VERSION_CREATED':
      return <RefreshCw className="size-4 text-indigo-600" aria-hidden="true" />
    case 'DOCUMENT_VERSION_DELETE':
      return <Trash2 className="size-4 text-rose-600" aria-hidden="true" />
    case 'DOCUMENT_DOWNLOAD':
    case 'DOCUMENT_VERSION_DOWNLOAD':
      return <Download className="size-4 text-emerald-600" aria-hidden="true" />
    case 'DOCUMENT_PREVIEW':
      return <Eye className="size-4 text-teal-600" aria-hidden="true" />
    case 'PERMISSION_GRANT':
    case 'PERMISSION_UPDATE':
    case 'PERMISSION_REVOKE':
      return <KeyRound className="size-4 text-purple-600" aria-hidden="true" />
    default:
      return <Activity className="size-4 text-muted-foreground" aria-hidden="true" />
  }
}

function FieldChangesView({ fieldChanges }) {
  if (!fieldChanges || typeof fieldChanges !== 'object') {
    return null
  }
  const entries = Object.entries(fieldChanges)
  if (entries.length === 0) {
    return null
  }

  return (
    <div className="mt-2 space-y-1.5 rounded-md border bg-muted/30 p-2.5 text-xs">
      <p className="font-semibold text-muted-foreground uppercase tracking-wider text-[10px]">
        Recorded Field Changes:
      </p>
      <div className="space-y-2">
        {entries.map(([field, delta]) => {
          const prev = delta?.previous ?? '(none)'
          const next = delta?.new ?? '(cleared)'
          return (
            <div key={field} className="space-y-0.5">
              <span className="font-medium text-foreground capitalize">
                {field.replaceAll('_', ' ')}:
              </span>
              <div className="flex flex-wrap items-center gap-1.5 text-muted-foreground font-mono">
                <span className="rounded bg-background/80 px-1.5 py-0.5 text-rose-700 line-through">
                  {String(prev)}
                </span>
                <ArrowRight className="size-3 text-muted-foreground" aria-hidden="true" />
                <span className="rounded bg-background/80 px-1.5 py-0.5 text-emerald-700 font-semibold">
                  {String(next)}
                </span>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function VersionChangesView({ details }) {
  const versionNum = details?.version_number
  const prevVersionNum = details?.previous_version_number
  const textChanges = details?.text_changes
  const source = details?.source

  return (
    <div className="mt-2 space-y-2 rounded-md border bg-muted/30 p-2.5 text-xs">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium text-foreground">
          {Number.isInteger(prevVersionNum)
            ? `Version ${versionNum} replaced Version ${prevVersionNum}`
            : `Created Version ${versionNum}`}
        </span>
        {source ? (
          <span className="rounded-full bg-muted px-2 py-0.5 text-[11px] text-muted-foreground">
            via {source === 'INLINE_EDITOR' ? 'inline editor' : 'file upload'}
          </span>
        ) : null}
      </div>

      {details?.file_size && details?.previous_file_size ? (
        <p className="text-muted-foreground">
          Size: {formatBytes(details.previous_file_size)} → {formatBytes(details.file_size)}
        </p>
      ) : null}

      {textChanges ? (
        <div className="flex flex-wrap items-center gap-2 text-[11px]">
          <span className="font-medium text-muted-foreground">Text diff:</span>
          {textChanges.lines_added > 0 ? (
            <span className="rounded bg-emerald-100 px-1.5 py-0.2 font-mono text-emerald-800">
              +{textChanges.lines_added} lines
            </span>
          ) : null}
          {textChanges.lines_removed > 0 ? (
            <span className="rounded bg-rose-100 px-1.5 py-0.2 font-mono text-rose-800">
              -{textChanges.lines_removed} lines
            </span>
          ) : null}
          {textChanges.lines_unchanged > 0 ? (
            <span className="text-muted-foreground">
              ({textChanges.lines_unchanged} unchanged)
            </span>
          ) : null}
        </div>
      ) : null}
    </div>
  )
}

export function DocumentActivityHistory({ documentId }) {
  const [events, setEvents] = useState([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState(null)
  const [refreshKey, setRefreshKey] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    setIsLoading(true)
    setError(null)

    listDocumentActivity(documentId, controller.signal)
      .then((data) => {
        setEvents(data.items || [])
      })
      .catch((err) => {
        if (err?.code !== 'ERR_CANCELED' && err?.name !== 'CanceledError') {
          setError(getApiErrorMessage(err))
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setIsLoading(false)
        }
      })

    return () => controller.abort()
  }, [documentId, refreshKey])

  return (
    <Card>
      <CardHeader className="flex-row items-start justify-between gap-4">
        <div>
          <CardTitle className="flex items-center gap-2">
            <Activity className="size-4 text-primary" aria-hidden="true" />
            Document activity & change history
          </CardTitle>
          <p className="mt-1 text-sm text-muted-foreground">
            Verifiable record of who accessed, edited, revised, or managed permissions on this
            document.
          </p>
        </div>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => setRefreshKey((k) => k + 1)}
          disabled={isLoading}
        >
          <RefreshCw className={cn('size-4', isLoading && 'animate-spin')} aria-hidden="true" />
          Refresh activity
        </Button>
      </CardHeader>

      <CardContent>
        {isLoading ? (
          <div className="space-y-3" aria-busy="true" aria-live="polite">
            {[0, 1, 2].map((i) => (
              <div key={i} className="h-16 animate-pulse rounded-lg bg-muted/40" />
            ))}
          </div>
        ) : error ? (
          <div
            role="alert"
            className="rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive"
          >
            {error}
          </div>
        ) : events.length === 0 ? (
          <p className="text-sm text-muted-foreground py-4 text-center">
            No activity has been recorded on this document yet.
          </p>
        ) : (
          <ol className="relative space-y-4 border-l border-muted pl-4 ml-2">
            {events.map((event) => {
              const outcome = outcomeMeta(event.outcome)
              const details = event.details || {}
              const isMetadataEdit = event.action === 'DOCUMENT_METADATA_UPDATE'
              const isVersionCreated = event.action === 'DOCUMENT_VERSION_CREATED'

              return (
                <li key={event.id} className="space-y-1.5">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <ActionIcon action={event.action} outcome={event.outcome} />
                      <span className="font-medium text-sm text-foreground">
                        {formatAuditAction(event.action)}
                      </span>
                      <span
                        className={cn(
                          'rounded-full px-2 py-0.5 text-[11px] font-medium ring-1 ring-inset',
                          outcome.tone,
                        )}
                      >
                        {outcome.label}
                      </span>
                    </div>

                    <div className="flex items-center gap-3 text-xs text-muted-foreground">
                      <span className="inline-flex items-center gap-1">
                        <UserRound className="size-3.5" aria-hidden="true" />
                        <strong>{event.actor_name || 'System'}</strong>
                        {details.access_level ? (
                          <span className="ml-1 rounded bg-muted/80 px-1.5 py-0.5 text-[10px]">
                            {details.access_level}
                          </span>
                        ) : null}
                      </span>
                      <span className="inline-flex items-center gap-1">
                        <Clock3 className="size-3.5" aria-hidden="true" />
                        {formatDateTime(event.occurred_at)}
                      </span>
                    </div>
                  </div>

                  {/* Summary / description */}
                  {details.change_summary ? (
                    <p className="text-xs text-foreground bg-muted/20 px-2.5 py-1.5 rounded">
                      <strong>Summary:</strong> {details.change_summary}
                    </p>
                  ) : null}

                  {/* Field changes visual diff */}
                  {isMetadataEdit && details.field_changes ? (
                    <FieldChangesView fieldChanges={details.field_changes} />
                  ) : null}

                  {/* Version creation details */}
                  {isVersionCreated ? (
                    <VersionChangesView details={details} />
                  ) : null}

                  {/* Permission action details */}
                  {event.action.startsWith('PERMISSION_') ? (
                    <p className="text-xs text-muted-foreground">
                      {details.permission ? `Level: ${details.permission}. ` : ''}
                      {details.recipient_id ? `Target recipient: ${details.recipient_id}` : ''}
                    </p>
                  ) : null}

                  {/* Denial reason */}
                  {event.outcome === 'DENIED' && details.reason ? (
                    <p className="text-xs font-medium text-amber-700">
                      Reason: {details.reason.replaceAll('_', ' ')}
                    </p>
                  ) : null}
                </li>
              )
            })}
          </ol>
        )}
      </CardContent>
    </Card>
  )
}
