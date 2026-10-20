import { ShieldX } from 'lucide-react'
import { Link } from 'react-router-dom'
import { useAuth } from '@/auth/useAuth'
import { buttonVariants } from '@/components/ui/button-variants'
import { formatRole } from '@/lib/roles'

export function ForbiddenState({ requiredRole }: { requiredRole: string }) {
  const { user } = useAuth()

  return (
    <div className="flex flex-col items-center justify-center gap-6 py-20 text-center">
      <span className="flex size-16 items-center justify-center rounded-2xl bg-destructive/10 text-destructive">
        <ShieldX className="size-8" aria-hidden="true" />
      </span>
      <div className="space-y-3">
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-destructive">403</p>
        <h1 className="text-3xl font-semibold tracking-tight">Access denied</h1>
        <p className="mx-auto max-w-md text-sm leading-6 text-muted-foreground">
          This area requires the {requiredRole} role
          {user ? `, and your account has the ${formatRole(user.role)} role` : ''}. The backend
          enforces this restriction regardless of what the interface shows.
        </p>
      </div>
      <Link to="/dashboard" className={buttonVariants()}>
        Back to dashboard
      </Link>
    </div>
  )
}
