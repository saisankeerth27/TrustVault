import { useEffect, useMemo, useState } from 'react'
import {
  ArrowRight,
  FileText,
  LoaderCircle,
  RefreshCw,
  Share2,
  ShieldCheck,
  UploadCloud,
} from 'lucide-react'
import { Link, useLocation } from 'react-router-dom'
import { useAuth } from '@/auth/useAuth'
import { AccessLevelBadge } from '@/components/documents/AccessLevelBadge'
import { PageHeader } from '@/components/PageHeader'
import { Button } from '@/components/ui/button'
import { buttonVariants } from '@/components/ui/button-variants'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { canUploadDocuments, formatBytes, formatDate } from '@/lib/documents'
import { getApiErrorMessage } from '@/services/api'
import { listDocuments, listSharedDocuments } from '@/services/documents'

const RECENT_PAGE_SIZE = 3
const EMPTY_SUMMARY = {
  items: [],
  total: 0,
  page: 1,
  page_size: RECENT_PAGE_SIZE,
  pages: 0,
  has_next: false,
  has_previous: false,
}

function isAbortError(error) {
  return error?.code === 'ERR_CANCELED' || error?.name === 'CanceledError'
}

function StatCard({ icon: Icon, label, value, hint, to, isLoading }) {
  return (
    <Link
      to={to}
      className="group rounded-xl border bg-card p-5 shadow-xs transition-colors hover:border-primary/40 hover:bg-accent/30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-sm text-muted-foreground">{label}</p>
          <p className="mt-2 text-3xl font-semibold tracking-tight">
            {isLoading ? (
              <span
                className="inline-block h-8 w-12 animate-pulse rounded bg-muted align-middle"
                aria-label="Loading"
              />
            ) : (
              (value ?? '—')
            )}
          </p>
        </div>
        <span className="flex size-10 items-center justify-center rounded-lg bg-primary/10 text-primary">
          <Icon className="size-5" aria-hidden="true" />
        </span>
      </div>
      <p className="mt-4 flex items-center gap-1.5 text-xs text-muted-foreground">
        {hint}
        <ArrowRight
          className="size-3.5 transition-transform group-hover:translate-x-0.5"
          aria-hidden="true"
        />
      </p>
    </Link>
  )
}

function RecentDocuments({ title, description, documents, isLoading, emptyMessage }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      <CardContent className="p-0">
        {isLoading ? (
          <div className="space-y-2 px-5 pb-5" aria-busy="true" aria-live="polite">
            {[0, 1, 2].map((row) => (
              <div key={row} className="flex items-center gap-3 rounded-lg border p-3">
                <div className="size-9 animate-pulse rounded-lg bg-muted" />
                <div className="flex-1 space-y-2">
                  <div className="h-3 w-1/2 animate-pulse rounded bg-muted" />
                  <div className="h-3 w-1/4 animate-pulse rounded bg-muted" />
                </div>
              </div>
            ))}
          </div>
        ) : documents.length === 0 ? (
          <div className="px-5 pb-6">
            <p className="rounded-lg border border-dashed px-4 py-8 text-center text-sm text-muted-foreground">
              {emptyMessage}
            </p>
          </div>
        ) : (
          <ul className="divide-y border-t">
            {documents.slice(0, 3).map((documentRecord) => (
              <li key={documentRecord.id}>
                <Link
                  to={`/documents/${documentRecord.id}`}
                  className="flex items-center gap-3 px-5 py-3.5 transition-colors hover:bg-muted/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring"
                >
                  <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-accent text-accent-foreground">
                    <FileText className="size-4" aria-hidden="true" />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-medium">
                      {documentRecord.name}
                    </span>
                    <span className="mt-0.5 block truncate text-xs text-muted-foreground">
                      {documentRecord.owner_name} · {formatBytes(documentRecord.file_size)} ·{' '}
                      {formatDate(documentRecord.updated_at)}
                    </span>
                  </span>
                  <AccessLevelBadge accessLevel={documentRecord.access_level} />
                </Link>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  )
}

export function DashboardPage() {
  const { user } = useAuth()
  const location = useLocation()
  const [documents, setDocuments] = useState(EMPTY_SUMMARY)
  const [shared, setShared] = useState(EMPTY_SUMMARY)
  const [owned, setOwned] = useState(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState(null)
  const [refreshKey, setRefreshKey] = useState(0)

  useEffect(() => {
    if (!user?.id) {
      return undefined
    }

    const controller = new AbortController()

    Promise.all([
      listDocuments(
        {
          page: 1,
          page_size: RECENT_PAGE_SIZE,
          sort_by: 'updated_at',
          order: 'desc',
        },
        controller.signal,
      ),
      listSharedDocuments(
        {
          page: 1,
          page_size: RECENT_PAGE_SIZE,
          sort_by: 'updated_at',
          order: 'desc',
        },
        controller.signal,
      ),
      listDocuments(
        {
          page: 1,
          page_size: 1,
          owner_id: user.id,
        },
        controller.signal,
      ),
    ])
      .then(([documentSummary, sharedSummary, ownedSummary]) => {
        if (!controller.signal.aborted) {
          setDocuments(documentSummary)
          setShared(sharedSummary)
          setOwned(ownedSummary)
        }
      })
      .catch((requestError) => {
        if (!isAbortError(requestError)) {
          setError(getApiErrorMessage(requestError))
          setDocuments(EMPTY_SUMMARY)
          setShared(EMPTY_SUMMARY)
          setOwned(null)
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setIsLoading(false)
        }
      })

    return () => controller.abort()
  }, [refreshKey, user?.id])

  const canUpload = canUploadDocuments(user)
  const visibleTotal = isLoading ? null : documents.total
  const sharedTotal = isLoading ? null : shared.total
  const ownedTotal = isLoading ? null : (owned?.total ?? 0)

  const quickLinks = useMemo(() => {
    const links = [
      { to: '/documents', label: 'Browse the document library' },
      { to: '/shared-with-me', label: 'Review documents shared with you' },
    ]
    if (canUpload) {
      links.push({ to: '/upload', label: 'Upload a new document' })
    }
    if (user?.role === 'ADMINISTRATOR') {
      links.push({ to: '/admin/audit', label: 'Review the administrator audit trail' })
    }
    return links
  }, [canUpload, user?.role])

  return (
    <div className="space-y-8">
      {typeof location.state?.registrationMessage === 'string' ? (
        <div
          role="status"
          className="rounded-lg border border-primary/20 bg-primary/5 px-4 py-3 text-sm"
        >
          {location.state.registrationMessage}
        </div>
      ) : null}
      <PageHeader
        eyebrow="Overview"
        title={user ? `Welcome back, ${user.name.split(' ')[0]}` : 'Dashboard'}
        description="Your current document access, recent shares, and the actions available to your account."
        actions={
          <>
            {canUpload ? (
              <Link to="/upload" className={buttonVariants()}>
                <UploadCloud className="size-4" aria-hidden="true" />
                Upload document
              </Link>
            ) : null}
            <Link
              to="/documents"
              className={buttonVariants({ variant: canUpload ? 'outline' : 'default' })}
            >
              View documents
              <ArrowRight className="size-4" aria-hidden="true" />
            </Link>
          </>
        }
      />

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
              setIsLoading(true)
              setError(null)
              setRefreshKey((key) => key + 1)
            }}
          >
            <RefreshCw className="size-4" aria-hidden="true" />
            Retry
          </Button>
        </div>
      ) : null}

      <section aria-label="Document summary" className="grid gap-4 md:grid-cols-3">
        <StatCard
          icon={FileText}
          label="Accessible documents"
          value={visibleTotal}
          hint={
            user?.role === 'ADMINISTRATOR'
              ? 'Metadata visible to your administrator account'
              : 'Owned or shared with your account'
          }
          to="/documents"
          isLoading={isLoading}
        />
        <StatCard
          icon={Share2}
          label="Shared with me"
          value={sharedTotal}
          hint="Active READ or EDIT grants"
          to="/shared-with-me"
          isLoading={isLoading}
        />
        <StatCard
          icon={ShieldCheck}
          label="Owned by me"
          value={ownedTotal}
          hint="Documents uploaded under your account"
          to="/documents"
          isLoading={isLoading}
        />
      </section>

      <div className="grid gap-5 lg:grid-cols-2">
        <RecentDocuments
          title="Recently updated"
          description="The latest documents visible to your account, ordered by update time."
          documents={documents.items}
          isLoading={isLoading}
          emptyMessage={
            canUpload
              ? 'No accessible documents yet. Upload your first document to get started.'
              : 'No documents are visible to your account yet.'
          }
        />
        <RecentDocuments
          title="Recently shared with you"
          description="Documents with an active grant from another owner."
          documents={shared.items}
          isLoading={isLoading}
          emptyMessage="No active shares are available to your account."
        />
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Quick actions</CardTitle>
          <CardDescription>Common tasks for your current role.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {quickLinks.map((link) => (
            <Link
              key={link.to}
              to={link.to}
              className="flex items-center justify-between gap-3 rounded-lg border px-4 py-3 text-sm font-medium transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
            >
              <span>{link.label}</span>
              <ArrowRight className="size-4 shrink-0" aria-hidden="true" />
            </Link>
          ))}
          <div className="rounded-lg bg-muted/50 px-4 py-3 text-xs leading-5 text-muted-foreground sm:col-span-2 lg:col-span-3">
            <p className="flex items-center gap-2 font-medium text-foreground">
              {isLoading ? (
                <LoaderCircle className="size-3.5 animate-spin" aria-hidden="true" />
              ) : (
                <ShieldCheck className="size-3.5" aria-hidden="true" />
              )}
              {isLoading ? 'Refreshing access summary' : 'Backend-enforced access'}
            </p>
            <p className="mt-1">
              This dashboard only shows documents the backend returns for your active session.
              Access changes apply on the next request.
            </p>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
