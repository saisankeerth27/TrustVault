import { useEffect, useMemo, useState } from 'react'
import {
  ArrowLeft,
  ArrowRight,
  FileText,
  LoaderCircle,
  RefreshCw,
  Search,
  UploadCloud,
  X,
} from 'lucide-react'
import { Link, useLocation } from 'react-router-dom'
import { useAuth } from '@/auth/useAuth'
import { AccessLevelBadge } from '@/components/documents/AccessLevelBadge'
import { PageHeader } from '@/components/PageHeader'
import { Button } from '@/components/ui/button'
import { buttonVariants } from '@/components/ui/button-variants'
import { Card, CardContent } from '@/components/ui/card'
import {
  CATEGORY_OPTIONS,
  SORT_OPTIONS,
  formatBytes,
  formatDate,
  canUploadDocuments,
} from '@/lib/documents'
import { cn } from '@/lib/utils'
import { getApiErrorMessage } from '@/services/api'
import { listDocuments } from '@/services/documents'

const PAGE_SIZE = 5
const EMPTY_RESULT = {
  items: [],
  total: 0,
  page: 1,
  page_size: PAGE_SIZE,
  pages: 0,
  has_next: false,
  has_previous: false,
}

const fieldClassName =
  'flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-xs transition-colors placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50'

function isAbortError(error) {
  return error?.code === 'ERR_CANCELED' || error?.name === 'CanceledError'
}

export function DocumentsPage() {
  const { user } = useAuth()
  const location = useLocation()
  const canUpload = canUploadDocuments(user)
  const [query, setQuery] = useState('')
  const [debouncedQuery, setDebouncedQuery] = useState('')
  const [category, setCategory] = useState('')
  const [sort, setSort] = useState(SORT_OPTIONS[0].value)
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [page, setPage] = useState(1)
  const [refreshKey, setRefreshKey] = useState(0)
  const [result, setResult] = useState(EMPTY_RESULT)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState(null)
  const [notice, setNotice] = useState(() => location.state?.notice ?? null)

  const hasFilters = Boolean(
    query.trim() ||
      category.trim() ||
      dateFrom ||
      dateTo ||
      sort !== SORT_OPTIONS[0].value,
  )

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setDebouncedQuery(query.trim())
    }, 300)
    return () => window.clearTimeout(timer)
  }, [query])

  useEffect(() => {
    const controller = new AbortController()
    const [sortBy, order] = sort.split(':')
    const params = {
      page,
      page_size: PAGE_SIZE,
      sort_by: sortBy,
      order,
    }

    if (debouncedQuery) {
      params.q = debouncedQuery
    }
    if (category.trim()) {
      params.category = category.trim()
    }
    if (dateFrom) {
      params.created_from = dateFrom
    }
    if (dateTo) {
      params.created_to = dateTo
    }

    listDocuments(params, controller.signal)
      .then((payload) => {
        if (page > payload.pages && page > 1) {
          setPage(payload.pages > 0 ? payload.pages : 1)
          return
        }
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
  }, [category, dateFrom, dateTo, debouncedQuery, page, refreshKey, sort])

  const rangeLabel = useMemo(() => {
    if (result.total === 0) {
      return 'No documents'
    }
    const start = (result.page - 1) * result.page_size + 1
    const end = Math.min(result.page * result.page_size, result.total)
    return `Showing ${start}-${end} of ${result.total}`
  }, [result])

  function beginRequest() {
    setError(null)
    setIsLoading(true)
  }

  function updateQuery(value) {
    beginRequest()
    setQuery(value)
    setPage(1)
  }

  function clearFilters() {
    beginRequest()
    setQuery('')
    setDebouncedQuery('')
    setCategory('')
    setSort(SORT_OPTIONS[0].value)
    setDateFrom('')
    setDateTo('')
    setPage(1)
  }

  function retry() {
    beginRequest()
    setRefreshKey((key) => key + 1)
  }

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Library"
        title="Document library"
        description={
          canUpload
            ? 'Search, filter, inspect, download, and manage documents you own or that have been shared with you. Permission changes are enforced by the backend on every request.'
            : 'Documents shared directly with your account appear here. READ grants allow viewing and downloads; EDIT grants also allow metadata updates.'
        }
        actions={
          canUpload ? (
            <Link to="/upload" className={buttonVariants()}>
              <UploadCloud className="size-4" aria-hidden="true" />
              Upload document
            </Link>
          ) : undefined
        }
      />

      {notice ? (
        <div
          role="status"
          className="flex items-start justify-between gap-3 rounded-lg border border-emerald-200 bg-emerald-50/70 px-4 py-3 text-sm text-emerald-900"
        >
          <span>{notice}</span>
          <button
            type="button"
            className="rounded-sm text-emerald-800 underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            onClick={() => setNotice(null)}
          >
            Dismiss
          </button>
        </div>
      ) : null}

      <Card>
        <CardContent className="space-y-5 px-6 py-6">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <h2 className="text-lg font-semibold tracking-tight">Browse documents</h2>
              <p className="mt-1 text-sm text-muted-foreground">
                {user?.role === 'ADMINISTRATOR'
                  ? 'Administrator accounts can review metadata across the library. Content access still requires an explicit READ or EDIT grant from the owner.'
                  : 'You can see documents you own and documents shared directly with your account.'}
              </p>
            </div>
            {hasFilters ? (
              <Button type="button" variant="ghost" size="sm" onClick={clearFilters}>
                <X className="size-4" aria-hidden="true" />
                Clear filters
              </Button>
            ) : null}
          </div>

          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            <div className="space-y-2 md:col-span-2">
              <label htmlFor="document-search" className="text-sm font-medium">
                Search by name
              </label>
              <div className="relative">
                <Search
                  className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground"
                  aria-hidden="true"
                />
                <input
                  id="document-search"
                  type="search"
                  value={query}
                  onChange={(event) => updateQuery(event.target.value)}
                  placeholder="Search documents..."
                  className={cn(fieldClassName, 'pl-9')}
                />
              </div>
            </div>


            <div className="space-y-2">
              <label htmlFor="document-category-filter" className="text-sm font-medium">
                Category
              </label>
              <input
                id="document-category-filter"
                type="text"
                value={category}
                list="document-category-filter-options"
                maxLength={100}
                placeholder="All categories"
                onChange={(event) => {
                  beginRequest()
                  setCategory(event.target.value)
                  setPage(1)
                }}
                className={fieldClassName}
              />
              <datalist id="document-category-filter-options">
                {CATEGORY_OPTIONS.map((option) => (
                  <option key={option} value={option} />
                ))}
              </datalist>
            </div>

            <div className="space-y-2">
              <label htmlFor="document-date-from" className="text-sm font-medium">
                Created from
              </label>
              <input
                id="document-date-from"
                type="date"
                value={dateFrom}
                max={dateTo || undefined}
                onChange={(event) => {
                  const value = event.target.value
                  beginRequest()
                  setDateFrom(value)
                  if (dateTo && value && value > dateTo) {
                    setDateTo('')
                  }
                  setPage(1)
                }}
                className={fieldClassName}
              />
            </div>

            <div className="space-y-2">
              <label htmlFor="document-date-to" className="text-sm font-medium">
                Created to
              </label>
              <input
                id="document-date-to"
                type="date"
                value={dateTo}
                min={dateFrom || undefined}
                onChange={(event) => {
                  const value = event.target.value
                  beginRequest()
                  setDateTo(value)
                  if (dateFrom && value && value < dateFrom) {
                    setDateFrom('')
                  }
                  setPage(1)
                }}
                className={fieldClassName}
              />
            </div>
          </div>

          <div className="flex flex-wrap items-center justify-between gap-3 border-t pt-4">
            <label htmlFor="document-sort" className="flex items-center gap-2 text-sm">
              <span className="text-muted-foreground">Sort</span>
              <select
                id="document-sort"
                value={sort}
                onChange={(event) => {
                  beginRequest()
                  setSort(event.target.value)
                  setPage(1)
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
            <p className="text-sm text-muted-foreground" aria-live="polite">
              {isLoading ? 'Loading documents...' : rangeLabel}
            </p>
          </div>
        </CardContent>
      </Card>

      {error ? (
        <div
          role="alert"
          className="flex flex-col gap-3 rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-4 text-sm text-destructive sm:flex-row sm:items-center sm:justify-between"
        >
          <span>{error}</span>
          <Button type="button" variant="outline" size="sm" onClick={retry}>
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
                <FileText className="size-6" aria-hidden="true" />
              </span>
              <div className="space-y-1">
                <h3 className="font-semibold">
                  {hasFilters ? 'No documents match these filters' : 'No documents yet'}
                </h3>
                <p className="max-w-md text-sm text-muted-foreground">
                  {hasFilters
                    ? 'Adjust the search, category, owner, or date filters and try again.'
                    : canUpload
                      ? 'Upload your first document to start building the library.'
                      : 'No documents have been shared with your account yet.'}
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
              <table className="w-full min-w-[860px] text-sm">
                <thead className="border-b bg-muted/40 text-left text-xs tracking-wide text-muted-foreground uppercase">
                  <tr>
                    <th scope="col" className="px-6 py-3 font-medium">
                      Document
                    </th>
                    <th scope="col" className="px-4 py-3 font-medium">
                      Category
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
                              {documentRecord.mime_type}
                            </p>
                          </div>
                        </div>
                      </td>
                      <td className="px-4 py-4 text-muted-foreground">
                        {documentRecord.category || 'Uncategorized'}
                      </td>
                      <td className="px-4 py-4">
                        <span
                          className="block max-w-40 truncate"
                        >
                          {documentRecord.owner_name}
                        </span>
                        {documentRecord.access_level === 'OWNER' ? (
                          <span className="text-xs text-muted-foreground">You</span>
                        ) : null}
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
              beginRequest()
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
              beginRequest()
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
