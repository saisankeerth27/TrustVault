import { LoaderCircle, ShieldCheck } from 'lucide-react'

export function AuthLoadingScreen() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-5 bg-muted/30 px-4 text-center">
      <span className="flex size-14 items-center justify-center rounded-2xl bg-primary text-primary-foreground">
        <ShieldCheck className="size-7" aria-hidden="true" />
      </span>
      <div className="space-y-2">
        <h1 className="text-xl font-semibold tracking-tight">TrustVault</h1>
        <p className="flex items-center justify-center gap-2 text-sm text-muted-foreground">
          <LoaderCircle className="size-4 animate-spin" aria-hidden="true" />
          Checking your session...
        </p>
      </div>
    </div>
  )
}
