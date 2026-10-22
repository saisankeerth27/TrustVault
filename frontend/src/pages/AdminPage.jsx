import { useEffect, useState } from 'react'
import {
  Activity,
  ArrowLeft,
  ArrowRight,
  FileText,
  LoaderCircle,
  RefreshCw,
  Search,
  ShieldCheck,
  Users,
  X,
} from 'lucide-react'
import { Link } from 'react-router-dom'
import { useAuth } from '@/auth/useAuth'
import { PageHeader } from '@/components/PageHeader'
import { Button } from '@/components/ui/button'
import { buttonVariants } from '@/components/ui/button-variants'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { formatDateTime } from '@/lib/documents'
import { formatRole } from '@/lib/roles'
import { cn } from '@/lib/utils'
import { getApiErrorMessage } from '@/services/api'
import {
  getAdminSummary,
  listAdminUsers,
  updateAdminUserRole,
  updateAdminUserStatus,
} from '@/services/admin'

const PAGE_SIZE = 25
const EMPTY_FILTERS = { q: '', status: '', role: '' }
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

function StatCard({ icon: Icon, label, value, hint, isLoading }) {
  return (
    <Card>
      <CardContent className="flex items-start justify-between gap-4 p-5">
        <div>
          <p className="text-sm text-muted-foreground">{label}</p>
          <p className="mt-2 text-3xl font-semibold tracking-tight">
            {isLoading ? (
              <span className="inline-block h-8 w-10 animate-pulse rounded bg-muted align-middle" />
            ) : (
              (value ?? 0)
            )}
          </p>
          <p className="mt-2 text-xs text-muted-foreground">{hint}</p>
        </div>
        <span className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
          <Icon className="size-5" aria-hidden="true" />
        </span>
      </CardContent>
    </Card>
  )
}

function StatusBadge({ status }) {
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full px-2.5 py-1 text-xs font-medium ring-1 ring-inset',
        status === 'ACTIVE'
          ? 'bg-emerald-50 text-emerald-800 ring-emerald-200'
          : 'bg-amber-50 text-amber-900 ring-amber-200',
      )}
    >
      {status === 'ACTIVE' ? 'Active' : 'Disabled'}
    </span>
  )
}

export function AdminPage() {
  const { user } = useAuth()
  const [draftFilters, setDraftFilters] = useState({ ...EMPTY_FILTERS })
  const [appliedFilters, setAppliedFilters] = useState({ ...EMPTY_FILTERS })
  const [page, setPage] = useState(1)
  const [result, setResult] = useState(EMPTY_RESULT)
  const [summary, setSummary] = useState(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState(null)
  const [actionError, setActionError] = useState(null)
  const [notice, setNotice] = useState(null)
  const [pendingUserId, setPendingUserId] = useState(null)
  const [refreshKey, setRefreshKey] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    const params = { page, page_size: PAGE_SIZE }
    if (appliedFilters.q.trim()) {
      params.q = appliedFilters.q.trim()
    }
    if (appliedFilters.status) {
      params.status = appliedFilters.status
    }
    if (appliedFilters.role) {
      params.role = appliedFilters.role
    }

    Promise.all([
      getAdminSummary(controller.signal),
      listAdminUsers(params, controller.signal),
    ])
      .then(([summaryPayload, usersPayload]) => {
        if (!controller.signal.aborted) {
          setSummary(summaryPayload)
          setResult(usersPayload)
          setError(null)
        }
      })
      .catch((requestError) => {
        if (!isAbortError(requestError)) {
          setError(requestError)
          setResult(EMPTY_RESULT)
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setIsLoading(false)
        }
      })

    return () => controller.abort()
  }, [appliedFilters, page, refreshKey])

  function applyFilters(event) {
    event.preventDefault()
    setIsLoading(true)
    setPage(1)
    setAppliedFilters({ ...draftFilters })
  }

  function clearFilters() {
    setIsLoading(true)
    setDraftFilters({ ...EMPTY_FILTERS })
    setAppliedFilters({ ...EMPTY_FILTERS })
    setPage(1)
  }

  function refresh() {
    setIsLoading(true)
    setError(null)
    setActionError(null)
    setNotice(null)
    setRefreshKey((key) => key + 1)
  }

  function changePage(nextPage) {
    setIsLoading(true)
    setPage(nextPage)
  }

  async function toggleStatus(account) {
    const nextStatus = account.status === 'ACTIVE' ? 'DISABLED' : 'ACTIVE'
    setPendingUserId(account.id)
    setActionError(null)
    setNotice(null)
    try {
      const payload = await updateAdminUserStatus(account.id, nextStatus)
      setNotice(
        `${payload.user.name} is now ${payload.user.status.toLowerCase()}. Session revocation and the audit record were applied by the backend.`,
      )
      setRefreshKey((key) => key + 1)
    } catch (requestError) {
      setActionError(getApiErrorMessage(requestError))
    } finally {
      setPendingUserId(null)
    }
  }

  async function changeRole(account, nextRole) {
    if (nextRole === account.role) {
      return
    }
    setPendingUserId(account.id)
    setActionError(null)
    setNotice(null)
    try {
      const payload = await updateAdminUserRole(account.id, nextRole)
      setNotice(
        `${payload.user.name} now has the ${formatRole(payload.user.role)} role. Existing sessions were revoked by the backend.`,
      )
      setRefreshKey((key) => key + 1)
    } catch (requestError) {
      setActionError(getApiErrorMessage(requestError))
    } finally {
      setPendingUserId(null)
    }
  }

  const hasFilters = Object.values(appliedFilters).some(Boolean)
  const rangeStart =
    result.total === 0 ? 0 : (result.page - 1) * result.page_size + 1
  const rangeEnd = Math.min(result.page * result.page_size, result.total)

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Administration"
        title="System oversight"
        description="Manage account access, review system-wide activity, and inspect document metadata without bypassing document permissions or downloading private content."
        actions={
          <Button type="button" variant="outline" onClick={refresh} disabled={isLoading}>
            <RefreshCw className={cn('size-4', isLoading && 'animate-spin')} aria-hidden="true" />
            Refresh
          </Button>
        }
      />

      {error ? (
        <div
          role="alert"
          className="rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-4 text-sm text-destructive"
        >
          {getApiErrorMessage(error)}
        </div>
      ) : null}

      {actionError ? (
        <div
          role="alert"
          className="rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-4 text-sm text-destructive"
        >
          {actionError}
        </div>
      ) : null}

      {notice ? (
        <div
          role="status"
          className="rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-4 text-sm text-emerald-900"
        >
          {notice}
        </div>
      ) : null}

      <section aria-label="System summary" className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        <StatCard
          icon={Users}
          label="Total accounts"
          value={summary?.total_users}
          hint={`${summary?.active_users ?? 0} active, ${summary?.disabled_users ?? 0} disabled`}
          isLoading={isLoading && !summary}
        />
        <StatCard
          icon={ShieldCheck}
          label="Administrators"
          value={summary?.administrators}
          hint={`${summary?.normal_users ?? 0} normal user accounts`}
          isLoading={isLoading && !summary}
        />
        <StatCard
          icon={FileText}
          label="Active documents"
          value={summary?.active_documents}
          hint={`${summary?.deleted_documents ?? 0} soft-deleted, ${summary?.active_grants ?? 0} active grants`}
          isLoading={isLoading && !summary}
        />
      </section>

      <Card>
        <CardHeader>
          <CardTitle>Account management</CardTitle>
          <CardDescription>
            Search and filter accounts, inspect last login and ownership, then disable, reactivate,
            or change a role. Every change is recorded in the audit trail.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form className="grid gap-4 md:grid-cols-[minmax(0,1fr)_12rem_12rem_auto]" onSubmit={applyFilters}>
            <div className="space-y-2">
              <label htmlFor="admin-user-search" className="text-sm font-medium">
                Search
              </label>
              <input
                id="admin-user-search"
                type="search"
                value={draftFilters.q}
                onChange={(event) =>
                  setDraftFilters((current) => ({ ...current, q: event.target.value }))
                }
                placeholder="Name or email"
                className={fieldClassName}
              />
            </div>
            <div className="space-y-2">
              <label htmlFor="admin-user-status" className="text-sm font-medium">
                Status
              </label>
              <select
                id="admin-user-status"
                value={draftFilters.status}
                onChange={(event) =>
                  setDraftFilters((current) => ({ ...current, status: event.target.value }))
                }
                className={fieldClassName}
              >
                <option value="">All statuses</option>
                <option value="ACTIVE">Active</option>
                <option value="DISABLED">Disabled</option>
              </select>
            </div>
            <div className="space-y-2">
              <label htmlFor="admin-user-role" className="text-sm font-medium">
                Role
              </label>
              <select
                id="admin-user-role"
                value={draftFilters.role}
                onChange={(event) =>
                  setDraftFilters((current) => ({ ...current, role: event.target.value }))
                }
                className={fieldClassName}
              >
                <option value="">All roles</option>
                <option value="ADMINISTRATOR">Administrator</option>
                <option value="USER">User</option>
              </select>
            </div>
            <div className="flex items-end gap-2">
              <Button type="submit">
                <Search className="size-4" aria-hidden="true" />
                Apply
              </Button>
              {hasFilters || Object.values(draftFilters).some(Boolean) ? (
                <Button type="button" variant="ghost" onClick={clearFilters}>
                  <X className="size-4" aria-hidden="true" />
                  Clear
                </Button>
              ) : null}
            </div>
          </form>

          <p className="mt-4 text-sm text-muted-foreground" aria-live="polite">
            {isLoading
              ? 'Loading accounts...'
              : result.total === 0
                ? 'No accounts match these filters.'
                : `Showing ${rangeStart}-${rangeEnd} of ${result.total} accounts`}
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="p-0">
          {isLoading && result.items.length === 0 ? (
            <div className="flex items-center justify-center gap-2 px-6 py-14 text-sm text-muted-foreground">
              <LoaderCircle className="size-4 animate-spin" aria-hidden="true" />
              Loading accounts
            </div>
          ) : result.items.length === 0 ? (
            <div className="px-6 py-14 text-center text-sm text-muted-foreground">
              No accounts match the current filters.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[1080px] text-sm">
                <thead className="border-b bg-muted/40 text-left text-xs tracking-wide text-muted-foreground uppercase">
                  <tr>
                    <th scope="col" className="px-6 py-3 font-medium">Account</th>
                    <th scope="col" className="px-4 py-3 font-medium">Role</th>
                    <th scope="col" className="px-4 py-3 font-medium">Status</th>
                    <th scope="col" className="px-4 py-3 font-medium">Documents</th>
                    <th scope="col" className="px-4 py-3 font-medium">Last login</th>
                    <th scope="col" className="px-4 py-3 font-medium">Created</th>
                    <th scope="col" className="px-6 py-3 text-right font-medium">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {result.items.map((account) => {
                    const isSelf = account.id === user?.id
                    const isPending = pendingUserId === account.id
                    return (
                      <tr key={account.id} className="align-top">
                        <td className="px-6 py-4">
                          <p className="font-medium">{account.name}</p>
                          <p className="mt-0.5 text-xs text-muted-foreground">{account.email}</p>
                          <p className="mt-1 font-mono text-[11px] text-muted-foreground">
                            {account.id}
                          </p>
                          {isSelf ? (
                            <p className="mt-1 text-xs font-medium text-primary">Current account</p>
                          ) : null}
                        </td>
                        <td className="px-4 py-4">
                          <select
                            aria-label={`Role for ${account.name}`}
                            value={account.role}
                            disabled={isSelf || isPending}
                            onChange={(event) => changeRole(account, event.target.value)}
                            className={cn(fieldClassName, 'h-9 min-w-36')}
                          >
                            <option value="USER">User</option>
                            <option value="ADMINISTRATOR">Administrator</option>
                          </select>
                        </td>
                        <td className="px-4 py-4">
                          <StatusBadge status={account.status} />
                        </td>
                        <td className="px-4 py-4">
                          <span className="font-medium">{account.document_count}</span>
                          <span className="block text-xs text-muted-foreground">owned</span>
                        </td>
                        <td className="px-4 py-4 whitespace-nowrap text-muted-foreground">
                          {formatDateTime(account.last_login_at)}
                        </td>
                        <td className="px-4 py-4 whitespace-nowrap text-muted-foreground">
                          {formatDateTime(account.created_at)}
                        </td>
                        <td className="px-6 py-4">
                          <div className="flex flex-col items-end gap-2">
                            <Button
                              type="button"
                              size="sm"
                              variant={account.status === 'ACTIVE' ? 'outline' : 'default'}
                              disabled={isSelf || isPending}
                              onClick={() => toggleStatus(account)}
                            >
                              {isPending
                                ? 'Saving...'
                                : account.status === 'ACTIVE'
                                  ? 'Disable'
                                  : 'Reactivate'}
                            </Button>
                            <Link
                              to={`/admin/audit?actor_id=${account.id}`}
                              className="text-xs font-medium text-primary hover:underline"
                            >
                              View activity
                            </Link>
                          </div>
                        </td>
                      </tr>
                    )
                  })}
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
            onClick={() => changePage(Math.max(1, page - 1))}
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
            onClick={() => changePage(page + 1)}
            disabled={!result.has_next}
          >
            Next
            <ArrowRight className="size-4" aria-hidden="true" />
          </Button>
        </div>
      ) : null}

      <div className="grid gap-5 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <FileText className="size-4 text-primary" aria-hidden="true" />
              Document oversight
            </CardTitle>
            <CardDescription>
              Review metadata for every active document. Document content remains protected by
              document-level permissions.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Link to="/documents" className={buttonVariants({ variant: 'outline' })}>
              Review document metadata
              <ArrowRight className="size-4" aria-hidden="true" />
            </Link>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Activity className="size-4 text-primary" aria-hidden="true" />
              Audit trail
            </CardTitle>
            <CardDescription>
              Search authentication, account, document, permission, denial, and download events
              with hash-chain integrity verification.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Link to="/admin/audit" className={buttonVariants({ variant: 'outline' })}>
              Open audit trail
              <ArrowRight className="size-4" aria-hidden="true" />
            </Link>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
