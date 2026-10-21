import { ShieldCheck } from 'lucide-react'
import { Link } from 'react-router-dom'

export function BrandMark({ to = '/dashboard', compact = false }) {
  return (
    <Link
      to={to}
      className="group inline-flex items-center gap-3 rounded-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
      aria-label="TrustVault home"
    >
      <span className="flex size-10 items-center justify-center rounded-xl bg-primary text-primary-foreground shadow-sm transition-transform group-hover:-translate-y-0.5">
        <ShieldCheck className="size-6" aria-hidden="true" />
      </span>
      <span
        className={
          compact ? 'hidden flex-col leading-none sm:flex' : 'flex flex-col leading-none'
        }
      >
        <span className="text-lg font-semibold tracking-tight">TrustVault</span>
        <span className="mt-1 text-[10px] font-medium uppercase tracking-[0.2em] text-muted-foreground">
          Secure document vault
        </span>
      </span>
    </Link>
  )
}
