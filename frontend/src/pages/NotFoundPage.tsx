import { SearchX } from 'lucide-react'
import { Link } from 'react-router-dom'
import { buttonVariants } from '@/components/ui/button-variants'

export function NotFoundPage() {
  return (
    <div className="flex flex-col items-center justify-center gap-6 py-20 text-center">
      <span className="flex size-16 items-center justify-center rounded-2xl bg-muted text-muted-foreground">
        <SearchX className="size-8" aria-hidden="true" />
      </span>
      <div className="space-y-3">
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-primary">404</p>
        <h1 className="text-3xl font-semibold tracking-tight">Page not found</h1>
        <p className="mx-auto max-w-md text-sm leading-6 text-muted-foreground">
          The page you requested does not exist in TrustVault.
        </p>
      </div>
      <Link to="/dashboard" className={buttonVariants()}>
        Back to dashboard
      </Link>
    </div>
  )
}
