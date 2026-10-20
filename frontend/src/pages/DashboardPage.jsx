import { useEffect, useState } from 'react'
import {
  ArrowRight,
  CheckCircle2,
  FileText,
  KeyRound,
  LockKeyhole,
  ServerCog,
} from 'lucide-react'
import { Link } from 'react-router-dom'
import { useAuth } from '@/auth/useAuth'
import { PageHeader } from '@/components/PageHeader'
import { buttonVariants } from '@/components/ui/button-variants'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { cn } from '@/lib/utils'
import { formatRole } from '@/lib/roles'
import { apiBaseUrl, apiClient, getApiErrorMessage, isApiConfigured } from '@/services/api'

function StatusPill({ tone, children }) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-2 rounded-full px-2.5 py-1 text-xs font-medium',
        tone === 'success' && 'bg-emerald-50 text-emerald-700',
        tone === 'warning' && 'bg-amber-50 text-amber-700',
        tone === 'neutral' && 'bg-muted text-muted-foreground',
      )}
    >
      <span
        className={cn(
          'size-1.5 rounded-full',
          tone === 'success' && 'bg-emerald-500',
          tone === 'warning' && 'bg-amber-500',
          tone === 'neutral' && 'bg-muted-foreground',
        )}
        aria-hidden="true"
      />
      {children}
    </span>
  )
}

export function DashboardPage() {
  const { user } = useAuth()
  const [health, setHealth] = useState(() =>
    isApiConfigured
      ? { status: 'loading', message: 'Checking backend health...' }
      : { status: 'unconfigured', message: 'VITE_API_BASE_URL is not configured.' },
  )

  useEffect(() => {
    if (!isApiConfigured) {
      return
    }

    let active = true

    apiClient
      .get('/health')
      .then(({ data }) => {
        if (active) {
          setHealth({
            status: 'online',
            message: `${data.service} v${data.version} responded successfully.`,
          })
        }
      })
      .catch((error) => {
        if (active) {
          setHealth({ status: 'offline', message: getApiErrorMessage(error) })
        }
      })

    return () => {
      active = false
    }
  }, [])

  const healthTone =
    health.status === 'online' ? 'success' : health.status === 'loading' ? 'neutral' : 'warning'

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Phase 4"
        title={user ? `Welcome back, ${user.name.split(' ')[0]}` : 'Application dashboard'}
        description="You are signed in to TrustVault. Authentication and secure document uploads are live; document listing, sharing permissions, downloads, and the audit UI arrive in later phases."
        actions={
          <Link to="/documents" className={buttonVariants({ variant: 'outline' })}>
            View documents
            <ArrowRight className="size-4" aria-hidden="true" />
          </Link>
        }
      />

      <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-3">
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between gap-3">
              <CardTitle>Authentication</CardTitle>
              <StatusPill tone="success">Live</StatusPill>
            </div>
            <CardDescription>Your session is verified by the backend.</CardDescription>
          </CardHeader>
          <CardContent>
            <ul className="space-y-3 text-sm">
              {[
                'Short-lived access token held in memory',
                'Rotating HttpOnly refresh session',
                'Database-backed role and account checks',
              ].map((item) => (
                <li key={item} className="flex items-start gap-2.5">
                  <CheckCircle2
                    className="mt-0.5 size-4 shrink-0 text-emerald-600"
                    aria-hidden="true"
                  />
                  <span>{item}</span>
                </li>
              ))}
              <li className="flex items-center justify-between gap-3 border-t pt-3">
                <span className="text-muted-foreground">Signed in as</span>
                <span className="text-right font-medium">
                  {user ? formatRole(user.role) : ''}
                </span>
              </li>
            </ul>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <div className="flex items-center justify-between gap-3">
              <CardTitle>API connection</CardTitle>
              <StatusPill tone={healthTone}>
                {health.status === 'online'
                  ? 'Online'
                  : health.status === 'loading'
                    ? 'Checking'
                    : health.status === 'offline'
                      ? 'Offline'
                      : 'Not configured'}
              </StatusPill>
            </div>
            <CardDescription>Live result from the backend health endpoint.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            <p className="text-muted-foreground">{health.message}</p>
            <div className="rounded-md bg-muted px-3 py-2 font-mono text-xs break-all">
              {isApiConfigured ? apiBaseUrl : 'VITE_API_BASE_URL is not set'}
            </div>
            {!isApiConfigured ? (
              <p className="text-xs leading-5 text-muted-foreground">
                Copy <code className="font-mono">frontend/.env.example</code> to{' '}
                <code className="font-mono">frontend/.env</code> and start the backend.
              </p>
            ) : null}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <div className="flex items-center justify-between gap-3">
              <CardTitle>Document access</CardTitle>
              <StatusPill tone="success">Uploads live</StatusPill>
            </div>
            <CardDescription>
              Owner and Administrator accounts can upload supported files.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3 text-sm text-muted-foreground">
            <div className="flex items-center gap-2">
              <FileText className="size-4" aria-hidden="true" />
              Private Wasabi object storage with server-generated keys.
            </div>
            <div className="flex items-center gap-2">
              <LockKeyhole className="size-4" aria-hidden="true" />
              Server-side file type, size, and signature validation.
            </div>
            <div className="flex items-center gap-2">
              <KeyRound className="size-4" aria-hidden="true" />
              SHA-256 checksums recorded in PostgreSQL.
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-5 lg:grid-cols-[2fr_1fr]">
        <Card>
          <CardHeader>
            <CardTitle>Security model</CardTitle>
            <CardDescription>How TrustVault enforces access today and later.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4 text-sm leading-6 text-muted-foreground">
            <div className="flex items-start gap-3">
              <ServerCog className="mt-0.5 size-4 shrink-0 text-primary" aria-hidden="true" />
              <p>
                The FastAPI backend is the sole authorization enforcement point. Hiding frontend
                controls is a user-experience choice, not a security control.
              </p>
            </div>
            <div className="flex items-start gap-3">
              <LockKeyhole className="mt-0.5 size-4 shrink-0 text-primary" aria-hidden="true" />
              <p>
                Every protected request validates the access token, active server-side session,
                and current database role. Signing out revokes the refresh session immediately.
              </p>
            </div>
            <p className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-amber-900">
              Current limitation: document listing, per-document permissions, downloads, and audit
              views are not implemented. Uploads are private, but retrieval and sharing workflows
              are not exposed yet.
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Quick links</CardTitle>
            <CardDescription>Navigate the current application.</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            <Link
              to="/documents"
              className="flex items-center justify-between rounded-lg border px-4 py-3 text-sm font-medium transition-colors hover:bg-accent"
            >
              Documents
              <ArrowRight className="size-4" aria-hidden="true" />
            </Link>
            {user?.role === 'ADMINISTRATOR' ? (
              <Link
                to="/admin"
                className="flex items-center justify-between rounded-lg border px-4 py-3 text-sm font-medium transition-colors hover:bg-accent"
              >
                Administrator area
                <ArrowRight className="size-4" aria-hidden="true" />
              </Link>
            ) : null}
            <a
              href="https://github.com/saisankeerth27/TrustVault"
              className="flex items-center justify-between rounded-lg border px-4 py-3 text-sm font-medium transition-colors hover:bg-accent"
              target="_blank"
              rel="noreferrer"
            >
              Project repository
              <ArrowRight className="size-4" aria-hidden="true" />
            </a>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
