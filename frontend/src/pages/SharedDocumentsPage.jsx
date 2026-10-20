import { useEffect, useMemo, useState } from 'react'
import {
  ArrowLeft,
  ArrowRight,
  FileText,
  LoaderCircle,
  RefreshCw,
  Share2,
} from 'lucide-react'
import { Link } from 'react-router-dom'
import { AccessLevelBadge } from '@/components/documents/AccessLevelBadge'
import { PageHeader } from '@/components/PageHeader'
import { Button } from '@/components/ui/button'
import { buttonVariants } from '@/components/ui/button-variants'
import { Card, CardContent } from '@/components/ui/card'
import { SORT_OPTIONS, formatBytes, formatDate } from '@/lib/documents'
import { getApiErrorMessage } from '@/services/api'
import { listSharedDocuments } from '@/services/documents'

const PAGE_SIZE = 10
const EMPTY_RESULT = {
  items: [],
  total: 0,
  page: 1,
  page_size: PAGE_SIZE,
  pages: 0,
  has_next: false,
  has_previous: false,
}

function isAbortError(error) {
  return error?.code === 'ERR_CANCELED' || error?.name === 'CanceledError'
}

export function SharedDocumentsPage() {
  const [sort, setSort] = useState(SORT_OPTIONS[0].value)
  const [page, setPage] = useState(1)
  const [refreshKey, setRefreshKey] = useState(0)
  const [result, setResult] = useState(EMPTY_RESULT)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    const controller = new AbortController()
    const [sortBy, order] = sort.split(':')

    listSharedDocuments(
      {
        page,
        page_size: PAGE_SIZE,
        sort_by: sortBy,
        order,
      },
      controller.signal,
    )
      .then((payload) => {
        setResult(payload)
      })
      .catch((requestError) => {
        if (!isAbortError(requestError)) {
          setError(getApiErrorMessage(requestError))
          setResult(EMPTY_RESULT)
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setIsLoading(false)
        }
      })

    return () => controller.abort()
  }, [page, refreshKey, sort])

  const rangeLabel = useMemo(() => {
    if (result.total === 0) {
      return 'No shared documents'
    }
    const start = (result.page - 1) * result.page_size + 1
    const end = Math.min(result.page * result.page_size, result.total)
    return `Showing ${start}-${end} of ${result.total}`
  }, [result])

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Phase 6"
        title="Shared with me"
        description="Documents another owner has shared with your account. READ grants allow viewing and downloads; EDIT grants also allow metadata updates. Access changes take effect on your next request."
        actions={
          <Link to="/documents" className={buttonVariants({ variant: 'outline' })}>
            <ArrowLeft className="size-4" aria-hidden="true" />
            Document library
          </Link>
        }
      />

      <Card>
        <CardContent className="flex flex-col gap-4 px-6 py-6 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h2 className="text-lg font-semibold tracking-tight">Direct shares</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              Only documents with an active permission grant appear here. Revoked and deleted
              documents are removed automatically.
            </p>
          </div>
          <label htmlFor="shared-sort" className="flex shrink-0 items-center gap-2 text-sm">
            <span className="text-muted-foreground">Sort</span>
            <select
              id="shared-sort"
              value={sort}
              onChange={(event) => {
                setError(null)
                setIsLoading(true)
                setPage(1)
                setSort(event.target.value)
              }}
              className="h-9 rounded-md border border-input bg-background px-2 text-sm shadow-xs focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
            >
              {SORT_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
        </CardContent>
      </Card>

      {error ? (
        <div
          role="alert"
          className="flex flex-col gap-3 rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-4 text-sm text-destructive sm:flex-row sm:items-center sm:justify-between"
        >
          <span>{error}</span>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => {
              setError(null)
              setIsLoading(true)
              setRefreshKey((key) => key + 1)
            }}
          >
            <RefreshCw className="size-4" aria-hidden="true" />
            Retry
          </Button>
        </div>
      ) : null}

      <Card>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="space-y-3 px-6 py-6" aria-busy="true" aria-live="polite">
              {[0, 1, 2].map((row) => (
                <div key={row} className="flex items-center gap-3 rounded-lg border p-4">
                  <div className="size-9 animate-pulse rounded-lg bg-muted" />
                  <div className="flex-1 space-y-2">
                    <div className="h-3 w-1/3 animate-pulse rounded bg-muted" />
                    <div className="h-3 w-1/5 animate-pulse rounded bg-muted" />
                  </div>
                  <LoaderCircle
                    className="size-4 animate-spin text-muted-foreground"
                    aria-hidden="true"
                  />
                </div>
              ))}
            </div>
          ) : result.items.length === 0 && !error ? (
            <div className="flex flex-col items-center gap-3 px-6 py-14 text-center">
              <span className="flex size-12 items-center justify-center rounded-xl bg-muted text-muted-foreground">
                <Share2 className="size-6" aria-hidden="true" />
              </span>
              <div className="space-y-1">
                <h3 className="font-semibold">Nothing has been shared with you</h3>
                <p className="max-w-md text-sm text-muted-foreground">
                  When a document owner grants your account READ or EDIT access, the document will
                  appear here.
                </p>
              </div>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[720px] text-sm">
                <thead className="border-b bg-muted/40 text-left text-xs tracking-wide text-muted-foreground uppercase">
                  <tr>
                    <th scope="col" className="px-6 py-3 font-medium">
                      Document
                    </th>
                    <th scope="col" className="px-4 py-3 font-medium">
                      Owner
                    </th>
                    <th scope="col" className="px-4 py-3 font-medium">
                      Your access
                    </th>
                    <th scope="col" className="px-4 py-3 font-medium">
                      Size
                    </th>
                    <th scope="col" className="px-4 py-3 font-medium">
                      Updated
                    </th>
                    <th scope="col" className="px-6 py-3 text-right font-medium">
                      Action
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {result.items.map((documentRecord) => (
                    <tr key={documentRecord.id} className="hover:bg-muted/30">
                      <td className="max-w-72 px-6 py-4">
                        <div className="flex items-start gap-3">
                          <span className="mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-lg bg-accent text-accent-foreground">
                            <FileText className="size-4" aria-hidden="true" />
                          </span>
                          <div className="min-w-0">
                            <Link
                              to={`/documents/${documentRecord.id}`}
                              className="block truncate font-medium hover:underline"
                            >
                              {documentRecord.name}
                            </Link>
                            <p className="mt-0.5 truncate text-xs text-muted-foreground">
                              {documentRecord.category || 'Uncategorized'}
                            </p>
                          </div>
                        </div>
                      </td>
                      <td className="px-4 py-4">
                        <span className="block max-w-40 truncate">{documentRecord.owner_name}</span>
                      </td>
                      <td className="px-4 py-4">
                        <AccessLevelBadge accessLevel={documentRecord.access_level} />
                      </td>
                      <td className="px-4 py-4 text-muted-foreground">
                        {formatBytes(documentRecord.file_size)}
                      </td>
                      <td className="px-4 py-4 text-muted-foreground">
                        {formatDate(documentRecord.updated_at)}
                      </td>
                      <td className="px-6 py-4 text-right">
                        <Link
                          to={`/documents/${documentRecord.id}`}
                          className={buttonVariants({ variant: 'outline', size: 'sm' })}
                        >
                          View
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {!isLoading && result.pages > 0 ? (
        <div className="flex flex-wrap items-center justify-between gap-3">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => {
              setError(null)
              setIsLoading(true)
              setPage((current) => Math.max(1, current - 1))
            }}
            disabled={!result.has_previous}
          >
            <ArrowLeft className="size-4" aria-hidden="true" />
            Previous
          </Button>
          <p className="text-sm text-muted-foreground">
            {rangeLabel} · Page {result.page} of {result.pages}
          </p>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => {
              setError(null)
              setIsLoading(true)
              setPage((current) => current + 1)
            }}
            disabled={!result.has_next}
          >
            Next
            <ArrowRight className="size-4" aria-hidden="true" />
          </Button>
        </div>
      ) : null}
    </div>
  )
}
