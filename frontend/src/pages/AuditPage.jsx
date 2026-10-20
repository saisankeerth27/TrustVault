import { useEffect, useMemo, useState } from 'react'
import {
  Activity,
  ArrowLeft,
  ArrowRight,
  Database,
  Fingerprint,
  LoaderCircle,
  RefreshCw,
  Search,
  ShieldAlert,
  ShieldCheck,
  X,
} from 'lucide-react'
import { ForbiddenState } from '@/components/ForbiddenState'
import { PageHeader } from '@/components/PageHeader'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import {
  AUDIT_ACTION_OPTIONS,
  checkpointMeta,
  formatAuditAction,
  integrityMeta,
  outcomeMeta,
} from '@/lib/audit'
import { formatDateTime } from '@/lib/documents'
import { cn } from '@/lib/utils'
import { getApiErrorMessage } from '@/services/api'
import { getAuditIntegrity, listAuditEvents } from '@/services/audit'

const PAGE_SIZE = 25
const EMPTY_FILTERS = {
  action: '',
  outcome: '',
  actorId: '',
  documentId: '',
  dateFrom: '',
  dateTo: '',
}
const EMPTY_RESULT = {
  items: [],
  total: 0,
  page: 1,
  page_size: PAGE_SIZE,
  pages: 0,
  has_next: false,
  has_previous: false,
}
const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i

const fieldClassName =
  'flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-xs transition-colors placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50'

function isAbortError(error) {
  return error?.code === 'ERR_CANCELED' || error?.name === 'CanceledError'
}

function OutcomeBadge({ outcome }) {
  const meta = outcomeMeta(outcome)
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full px-2.5 py-1 text-xs font-medium ring-1 ring-inset',
        meta.tone,
      )}
    >
      {meta.label}
    </span>
  )
}

function IntegrityStatus({ label, value, tone = 'text-foreground' }) {
  return (
    <div className="flex items-center justify-between gap-4 border-b py-2 last:border-b-0">
      <span className="text-muted-foreground">{label}</span>
      <span className={cn('text-right font-medium', tone)}>{value}</span>
    </div>
  )
}

function IntegrityPanel({
  integrity,
  isLoading,
  error,
  lastChecked,
  onRefresh,
}) {
  const meta = integrityMeta(integrity?.status)
  const checkpoint = checkpointMeta(integrity?.checkpoint?.status)

  return (
    <Card>
      <CardHeader className="flex-row items-start justify-between gap-4">
        <div className="space-y-1.5">
          <CardTitle className="flex items-center gap-2">
            <Fingerprint className="size-4 text-primary" aria-hidden="true" />
            Integrity verification
          </CardTitle>
          <CardDescription>
            Chain hashes are recomputed from stored events and compared with the signed external
            checkpoint head.
          </CardDescription>
        </div>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={onRefresh}
          disabled={isLoading}
        >
          <RefreshCw
            className={cn('size-4', isLoading && 'animate-spin')}
            aria-hidden="true"
          />
          Refresh
        </Button>
      </CardHeader>
      <CardContent className="space-y-5">
        {error ? (
          <div
            role="alert"
            className="rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive"
          >
            {error}
          </div>
        ) : null}

        {isLoading && !integrity ? (
          <div className="space-y-3" aria-busy="true" aria-live="polite">
            <div className="h-5 w-40 animate-pulse rounded bg-muted" />
            <div className="h-3 w-full animate-pulse rounded bg-muted" />
            <div className="h-3 w-2/3 animate-pulse rounded bg-muted" />
          </div>
        ) : integrity ? (
          <>
            <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
              <div className="space-y-1">
                <span
                  className={cn(
                    'inline-flex items-center gap-2 rounded-full px-3 py-1 text-sm font-medium ring-1 ring-inset',
                    meta.tone,
                  )}
                >
                  {integrity.status === 'INVALID' ? (
                    <ShieldAlert className="size-4" aria-hidden="true" />
                  ) : (
                    <ShieldCheck className="size-4" aria-hidden="true" />
                  )}
                  {meta.label}
                </span>
                <p className="max-w-2xl text-sm leading-6 text-muted-foreground">
                  {meta.description}
                </p>
              </div>
              {lastChecked ? (
                <p className="text-xs whitespace-nowrap text-muted-foreground">
                  Checked {formatDateTime(lastChecked)}
                </p>
              ) : null}
            </div>

            <div className="grid gap-5 md:grid-cols-2">
              <div className="rounded-lg border px-4 py-3 text-sm">
                <p className="mb-2 flex items-center gap-2 font-medium">
                  <Activity className="size-4 text-primary" aria-hidden="true" />
                  Hash chain
                </p>
                <IntegrityStatus label="Status" value={integrity.chain.status} />
                <IntegrityStatus label="Events" value={integrity.chain.event_count} />
                <IntegrityStatus
                  label="Latest sequence"
                  value={integrity.chain.last_chain_index ?? '—'}
                />
                {integrity.chain.failure_chain_index ? (
                  <IntegrityStatus
                    label="Failure sequence"
                    value={integrity.chain.failure_chain_index}
                    tone="text-destructive"
                  />
                ) : null}
                <p className="mt-3 text-xs leading-5 text-muted-foreground">
                  {integrity.chain.message}
                </p>
              </div>

              <div className="rounded-lg border px-4 py-3 text-sm">
                <p className="mb-2 flex items-center gap-2 font-medium">
                  <Database className="size-4 text-primary" aria-hidden="true" />
                  Signed checkpoint
                </p>
                <IntegrityStatus
                  label="Status"
                  value={checkpoint.label}
                  tone={checkpoint.tone}
                />
                <IntegrityStatus
                  label="Covers sequence"
                  value={integrity.checkpoint.last_chain_index ?? '—'}
                />
                <IntegrityStatus
                  label="Created"
                  value={
                    integrity.checkpoint.created_at
                      ? formatDateTime(integrity.checkpoint.created_at)
                      : 'Not recorded'
                  }
                />
                <p className="mt-3 text-xs leading-5 text-muted-foreground">
                  {integrity.checkpoint.message}
                </p>
              </div>
            </div>

            <p className="text-xs leading-5 text-muted-foreground">
              The checkpoint is an HMAC-signed file stored outside the database. Database-only
              tampering is detectable only up to the last signed checkpoint; protect the signing
              key and checkpoint file with the same care as the database.
            </p>
          </>
        ) : (
          <p className="text-sm text-muted-foreground">
            Integrity status is unavailable. Refresh to try again.
          </p>
        )}
      </CardContent>
    </Card>
  )
}

export function AuditPage() {
  const [draftFilters, setDraftFilters] = useState({ ...EMPTY_FILTERS })
  const [appliedFilters, setAppliedFilters] = useState({ ...EMPTY_FILTERS })
  const [filterError, setFilterError] = useState(null)
  const [page, setPage] = useState(1)
  const [result, setResult] = useState(EMPTY_RESULT)
  const [isLoadingEvents, setIsLoadingEvents] = useState(true)
  const [eventError, setEventError] = useState(null)
  const [eventRefreshKey, setEventRefreshKey] = useState(0)
  const [integrity, setIntegrity] = useState(null)
  const [isLoadingIntegrity, setIsLoadingIntegrity] = useState(true)
  const [integrityError, setIntegrityError] = useState(null)
  const [integrityRefreshKey, setIntegrityRefreshKey] = useState(0)
  const [lastChecked, setLastChecked] = useState(null)

  const hasFilters = useMemo(
    () => Object.values(appliedFilters).some(Boolean),
    [appliedFilters],
  )

  useEffect(() => {
    const controller = new AbortController()
    const params = { page, page_size: PAGE_SIZE }

    if (appliedFilters.action) {
      params.action = appliedFilters.action
    }
    if (appliedFilters.outcome) {
      params.outcome = appliedFilters.outcome
    }
    if (appliedFilters.actorId) {
      params.actor_id = appliedFilters.actorId
    }
    if (appliedFilters.documentId) {
      params.document_id = appliedFilters.documentId
    }
    if (appliedFilters.dateFrom) {
      params.occurred_from = appliedFilters.dateFrom
    }
    if (appliedFilters.dateTo) {
      params.occurred_to = appliedFilters.dateTo
    }

    listAuditEvents(params, controller.signal)
      .then((payload) => {
        setResult(payload)
      })
      .catch((requestError) => {
        if (!isAbortError(requestError)) {
          setEventError(requestError)
          setResult(EMPTY_RESULT)
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setIsLoadingEvents(false)
        }
      })

    return () => controller.abort()
  }, [appliedFilters, eventRefreshKey, page])

  useEffect(() => {
    const controller = new AbortController()
    getAuditIntegrity(controller.signal)
      .then((payload) => {
        setIntegrity(payload)
        setLastChecked(new Date().toISOString())
      })
      .catch((requestError) => {
        if (!isAbortError(requestError)) {
          setIntegrityError(getApiErrorMessage(requestError))
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setIsLoadingIntegrity(false)
        }
      })

    return () => controller.abort()
  }, [integrityRefreshKey])

  const rangeLabel = useMemo(() => {
    if (result.total === 0) {
      return 'No audit events'
    }
    const start = (result.page - 1) * result.page_size + 1
    const end = Math.min(result.page * result.page_size, result.total)
    return `Showing ${start}-${end} of ${result.total}`
  }, [result])

  function updateDraft(field, value) {
    setDraftFilters((current) => ({ ...current, [field]: value }))
  }

  function beginEventRequest() {
    setIsLoadingEvents(true)
    setEventError(null)
  }

  function beginIntegrityRequest() {
    setIsLoadingIntegrity(true)
    setIntegrityError(null)
  }

  function refreshIntegrity() {
    beginIntegrityRequest()
    setIntegrityRefreshKey((key) => key + 1)
  }

  function applyFilters(event) {
    event.preventDefault()
    const actorId = draftFilters.actorId.trim()
    const documentId = draftFilters.documentId.trim()

    if (actorId && !UUID_PATTERN.test(actorId)) {
      setFilterError('Actor ID must be a valid UUID.')
      return
    }
    if (documentId && !UUID_PATTERN.test(documentId)) {
      setFilterError('Document ID must be a valid UUID.')
      return
    }
    if (
      draftFilters.dateFrom &&
      draftFilters.dateTo &&
      draftFilters.dateFrom > draftFilters.dateTo
    ) {
      setFilterError('The start date must be on or before the end date.')
      return
    }

    setFilterError(null)
    beginEventRequest()
    setPage(1)
    setAppliedFilters({
      action: draftFilters.action,
      outcome: draftFilters.outcome,
      actorId,
      documentId,
      dateFrom: draftFilters.dateFrom,
      dateTo: draftFilters.dateTo,
    })
  }

  function clearFilters() {
    setFilterError(null)
    beginEventRequest()
    setDraftFilters({ ...EMPTY_FILTERS })
    setAppliedFilters({ ...EMPTY_FILTERS })
    setPage(1)
  }

  function refreshAll() {
    beginEventRequest()
    beginIntegrityRequest()
    setEventRefreshKey((key) => key + 1)
    setIntegrityRefreshKey((key) => key + 1)
  }

  if (eventError?.response?.status === 403 || integrityError?.response?.status === 403) {
    return <ForbiddenState requiredRole="ADMINISTRATOR" />
  }

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Phase 7"
        title="Audit trail"
        description="Review tamper-evident authentication, document, permission, and denial events across TrustVault. Only the event's recorded metadata is shown; file contents and credentials are never included."
        actions={
          <Button type="button" variant="outline" onClick={refreshAll}>
            <RefreshCw className="size-4" aria-hidden="true" />
            Refresh
          </Button>
        }
      />

      <IntegrityPanel
        integrity={integrity}
        isLoading={isLoadingIntegrity}
        error={integrityError}
        lastChecked={lastChecked}
        onRefresh={refreshIntegrity}
      />

      <Card>
        <CardHeader>
          <CardTitle>Filter events</CardTitle>
          <CardDescription>
            Combine action, outcome, identity, document, and UTC date filters. Event history is
            ordered by the append-only chain sequence.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form className="space-y-5" onSubmit={applyFilters}>
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
              <div className="space-y-2">
                <label htmlFor="audit-action" className="text-sm font-medium">
                  Action
                </label>
                <select
                  id="audit-action"
                  value={draftFilters.action}
                  onChange={(event) => updateDraft('action', event.target.value)}
                  className={fieldClassName}
                >
                  <option value="">All actions</option>
                  {AUDIT_ACTION_OPTIONS.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </div>

              <div className="space-y-2">
                <label htmlFor="audit-outcome" className="text-sm font-medium">
                  Outcome
                </label>
                <select
                  id="audit-outcome"
                  value={draftFilters.outcome}
                  onChange={(event) => updateDraft('outcome', event.target.value)}
                  className={fieldClassName}
                >
                  <option value="">All outcomes</option>
                  <option value="SUCCESS">Success</option>
                  <option value="DENIED">Denied</option>
                  <option value="FAILURE">Failure</option>
                </select>
              </div>

              <div className="space-y-2">
                <label htmlFor="audit-date-from" className="text-sm font-medium">
                  Occurred from (UTC)
                </label>
                <input
                  id="audit-date-from"
                  type="date"
                  value={draftFilters.dateFrom}
                  max={draftFilters.dateTo || undefined}
                  onChange={(event) => updateDraft('dateFrom', event.target.value)}
                  className={fieldClassName}
                />
              </div>

              <div className="space-y-2">
                <label htmlFor="audit-date-to" className="text-sm font-medium">
                  Occurred to (UTC)
                </label>
                <input
                  id="audit-date-to"
                  type="date"
                  value={draftFilters.dateTo}
                  min={draftFilters.dateFrom || undefined}
                  onChange={(event) => updateDraft('dateTo', event.target.value)}
                  className={fieldClassName}
                />
              </div>

              <div className="space-y-2">
                <label htmlFor="audit-actor-id" className="text-sm font-medium">
                  Actor ID
                </label>
                <input
                  id="audit-actor-id"
                  type="text"
                  value={draftFilters.actorId}
                  onChange={(event) => updateDraft('actorId', event.target.value)}
                  placeholder="Optional user UUID"
                  spellCheck={false}
                  className={cn(fieldClassName, 'font-mono text-xs')}
                />
              </div>

              <div className="space-y-2">
                <label htmlFor="audit-document-id" className="text-sm font-medium">
                  Document ID
                </label>
                <input
                  id="audit-document-id"
                  type="text"
                  value={draftFilters.documentId}
                  onChange={(event) => updateDraft('documentId', event.target.value)}
                  placeholder="Optional document UUID"
                  spellCheck={false}
                  className={cn(fieldClassName, 'font-mono text-xs')}
                />
              </div>
            </div>

            {filterError ? (
              <p role="alert" className="text-sm text-destructive">
                {filterError}
              </p>
            ) : null}

            <div className="flex flex-wrap items-center gap-3 border-t pt-4">
              <Button type="submit">
                <Search className="size-4" aria-hidden="true" />
                Apply filters
              </Button>
              {hasFilters || Object.values(draftFilters).some(Boolean) ? (
                <Button type="button" variant="ghost" onClick={clearFilters}>
                  <X className="size-4" aria-hidden="true" />
                  Clear filters
                </Button>
              ) : null}
              <p className="ml-auto text-sm text-muted-foreground" aria-live="polite">
                {isLoadingEvents ? 'Loading events...' : rangeLabel}
              </p>
            </div>
          </form>
        </CardContent>
      </Card>

      {eventError ? (
        <div
          role="alert"
          className="flex flex-col gap-3 rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-4 text-sm text-destructive sm:flex-row sm:items-center sm:justify-between"
        >
          <span>{getApiErrorMessage(eventError)}</span>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => {
              beginEventRequest()
              setEventRefreshKey((key) => key + 1)
            }}
          >
            <RefreshCw className="size-4" aria-hidden="true" />
            Retry
          </Button>
        </div>
      ) : null}

      <Card>
        <CardContent className="p-0">
          {isLoadingEvents ? (
            <div className="space-y-3 px-6 py-6" aria-busy="true" aria-live="polite">
              {[0, 1, 2, 3].map((row) => (
                <div key={row} className="space-y-2 rounded-lg border p-4">
                  <div className="h-3 w-1/3 animate-pulse rounded bg-muted" />
                  <div className="h-3 w-2/3 animate-pulse rounded bg-muted" />
                  <div className="h-3 w-1/2 animate-pulse rounded bg-muted" />
                </div>
              ))}
            </div>
          ) : result.items.length === 0 && !eventError ? (
            <div className="flex flex-col items-center gap-3 px-6 py-14 text-center">
              <span className="flex size-12 items-center justify-center rounded-xl bg-muted text-muted-foreground">
                <Activity className="size-6" aria-hidden="true" />
              </span>
              <div className="space-y-1">
                <h3 className="font-semibold">
                  {hasFilters ? 'No events match these filters' : 'No audit events yet'}
                </h3>
                <p className="max-w-md text-sm text-muted-foreground">
                  {hasFilters
                    ? 'Adjust the filters and try again. Date filters use UTC calendar days.'
                    : 'Audit events appear here as users register, sign in, and access documents or permissions.'}
                </p>
              </div>
              {hasFilters ? (
                <Button type="button" variant="outline" size="sm" onClick={clearFilters}>
                  Clear filters
                </Button>
              ) : null}
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[1120px] text-sm">
                <thead className="border-b bg-muted/40 text-left text-xs tracking-wide text-muted-foreground uppercase">
                  <tr>
                    <th scope="col" className="px-6 py-3 font-medium">
                      Sequence / time
                    </th>
                    <th scope="col" className="px-4 py-3 font-medium">
                      Action
                    </th>
                    <th scope="col" className="px-4 py-3 font-medium">
                      Outcome
                    </th>
                    <th scope="col" className="px-4 py-3 font-medium">
                      Actor
                    </th>
                    <th scope="col" className="px-4 py-3 font-medium">
                      Document
                    </th>
                    <th scope="col" className="px-4 py-3 font-medium">
                      Request ID
                    </th>
                    <th scope="col" className="px-6 py-3 font-medium">
                      Details
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {result.items.map((event) => (
                    <tr
                      key={event.id}
                      className={cn('align-top', event.outcome === 'DENIED' && 'bg-amber-50/30')}
                    >
                      <td className="px-6 py-4">
                        <p className="font-mono text-xs text-muted-foreground">
                          #{event.chain_index}
                        </p>
                        <time
                          dateTime={event.occurred_at}
                          className="mt-1 block whitespace-nowrap font-medium"
                        >
                          {formatDateTime(event.occurred_at)}
                        </time>
                      </td>
                      <td className="px-4 py-4">
                        <span className="font-medium">{formatAuditAction(event.action)}</span>
                        <span className="mt-0.5 block font-mono text-[11px] text-muted-foreground">
                          {event.action}
                        </span>
                      </td>
                      <td className="px-4 py-4">
                        <OutcomeBadge outcome={event.outcome} />
                      </td>
                      <td className="px-4 py-4">
                        <span className="block max-w-40 truncate">
                          {event.actor_name || 'System / anonymous'}
                        </span>
                        {event.actor_id ? (
                          <span
                            title={event.actor_id}
                            className="mt-0.5 block max-w-40 truncate font-mono text-[11px] text-muted-foreground"
                          >
                            {event.actor_id}
                          </span>
                        ) : null}
                      </td>
                      <td className="px-4 py-4">
                        <span className="block max-w-44 truncate">
                          {event.document_name || '—'}
                        </span>
                        {event.document_id ? (
                          <span
                            title={event.document_id}
                            className="mt-0.5 block max-w-44 truncate font-mono text-[11px] text-muted-foreground"
                          >
                            {event.document_id}
                          </span>
                        ) : null}
                      </td>
                      <td className="px-4 py-4">
                        <span
                          title={event.request_id || undefined}
                          className="block max-w-36 truncate font-mono text-xs text-muted-foreground"
                        >
                          {event.request_id || '—'}
                        </span>
                      </td>
                      <td className="px-6 py-4">
                        <details>
                          <summary className="cursor-pointer text-xs font-medium text-primary">
                            View metadata
                          </summary>
                          <pre className="mt-2 max-h-64 max-w-72 overflow-auto rounded-md bg-muted/60 p-3 text-xs whitespace-pre-wrap break-all">
                            {JSON.stringify(event.details, null, 2)}
                          </pre>
                        </details>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {!isLoadingEvents && result.pages > 0 ? (
        <div className="flex flex-wrap items-center justify-between gap-3">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => {
              beginEventRequest()
              setPage((current) => Math.max(1, current - 1))
            }}
            disabled={!result.has_previous}
          >
            <ArrowLeft className="size-4" aria-hidden="true" />
            Previous
          </Button>
          <p className="text-sm text-muted-foreground">
            Page {result.page} of {result.pages}
          </p>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => {
              beginEventRequest()
              setPage((current) => current + 1)
            }}
            disabled={!result.has_next}
          >
            Next
            <ArrowRight className="size-4" aria-hidden="true" />
          </Button>
        </div>
      ) : null}

      {isLoadingEvents && result.items.length > 0 ? (
        <p className="flex items-center justify-center gap-2 text-sm text-muted-foreground">
          <LoaderCircle className="size-4 animate-spin" aria-hidden="true" />
          Refreshing events...
        </p>
      ) : null}
    </div>
  )
}
