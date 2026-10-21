import { ArrowRight, KeyRound, ScrollText, ShieldCheck, UserCog, Users } from 'lucide-react'
import { Link } from 'react-router-dom'
import { useAuth } from '@/auth/useAuth'
import { PageHeader } from '@/components/PageHeader'
import { buttonVariants } from '@/components/ui/button-variants'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { formatRole } from '@/lib/roles'

export function AdminPage() {
  const { user } = useAuth()

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Administration"
        title="Administrator area"
        description="This route is gated by the ADMINISTRATOR role in the frontend and by the backend session checks. Audit history and integrity verification are available to administrators."
      />

      <div className="grid gap-5 md:grid-cols-2">
        <Card>
          <CardHeader>
            <div className="flex items-center gap-3">
              <span className="flex size-10 items-center justify-center rounded-lg bg-primary/10 text-primary">
                <UserCog className="size-5" aria-hidden="true" />
              </span>
              <div>
                <CardTitle>Current account</CardTitle>
                <CardDescription>Signed-in identity and effective role.</CardDescription>
              </div>
            </div>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            <div className="flex items-center justify-between gap-4">
              <span className="text-muted-foreground">Name</span>
              <span className="font-medium">{user?.name}</span>
            </div>
            <div className="flex items-center justify-between gap-4">
              <span className="text-muted-foreground">Email</span>
              <span className="truncate font-medium">{user?.email}</span>
            </div>
            <div className="flex items-center justify-between gap-4">
              <span className="text-muted-foreground">Role</span>
              <span className="font-medium">{user ? formatRole(user.role) : ''}</span>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <div className="flex items-center gap-3">
              <span className="flex size-10 items-center justify-center rounded-lg bg-primary/10 text-primary">
                <ShieldCheck className="size-5" aria-hidden="true" />
              </span>
              <div>
                <CardTitle>Backend-enforced roles</CardTitle>
                <CardDescription>Backend authorization remains authoritative.</CardDescription>
              </div>
            </div>
          </CardHeader>
          <CardContent className="space-y-3 text-sm leading-6 text-muted-foreground">
            <p>
              Public registration always creates Viewer accounts. Elevated roles are provisioned
              with the backend account script.
            </p>
            <p>
              Hiding this navigation item is only a convenience. Requests are still authorized
              against the database role and active session on the server.
            </p>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <div className="flex items-center gap-3">
            <span className="flex size-10 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <ScrollText className="size-5" aria-hidden="true" />
            </span>
            <div>
              <CardTitle>Audit trail</CardTitle>
              <CardDescription>
                Review authentication, document, permission, and denial events.
              </CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent className="flex flex-col gap-4 text-sm text-muted-foreground sm:flex-row sm:items-center sm:justify-between">
          <p className="max-w-2xl leading-6">
            The audit view shows append-only chain metadata and a hash-integrity report. Checkpoint
            signatures verify the trail head without exposing credentials or document content.
          </p>
          <Link
            to="/admin/audit"
            className={buttonVariants({ variant: 'outline' })}
          >
            Open audit trail
            <ArrowRight className="size-4" aria-hidden="true" />
          </Link>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <div className="flex items-center gap-3">
            <span className="flex size-10 items-center justify-center rounded-lg bg-muted text-muted-foreground">
              <Users className="size-5" aria-hidden="true" />
            </span>
            <div>
              <CardTitle>Account management</CardTitle>
              <CardDescription>Account administration APIs are not exposed yet.</CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent className="flex flex-col gap-3 text-sm text-muted-foreground">
          <p className="flex items-start gap-2.5">
            <KeyRound className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
            Use the provisioning command to create Administrator or Document owner accounts. No
            passwords are displayed by the script.
          </p>
          <p>
            Listing, disabling, and role-changing users is intentionally deferred. This page
            does not display sample accounts or fake administrative data.
          </p>
        </CardContent>
      </Card>
    </div>
  )
}
