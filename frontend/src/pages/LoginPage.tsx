import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { ArrowRight, LockKeyhole, ShieldCheck } from 'lucide-react'
import { Link } from 'react-router-dom'
import { z } from 'zod'
import { BrandMark } from '@/components/BrandMark'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'

const loginSchema = z.object({
  email: z.string().trim().email({ message: 'Enter a valid email address.' }),
  password: z.string().min(8, { message: 'Password must be at least 8 characters.' }),
})

type LoginFormValues = z.infer<typeof loginSchema>

export function LoginPage() {
  const [notice, setNotice] = useState<string | null>(null)
  const {
    register,
    handleSubmit,
    formState: { errors },
    setError,
    clearErrors,
  } = useForm<LoginFormValues>({
    defaultValues: { email: '', password: '' },
  })

  const onSubmit = (values: LoginFormValues) => {
    clearErrors()
    const result = loginSchema.safeParse(values)

    if (!result.success) {
      for (const issue of result.error.issues) {
        const field = issue.path[0]
        if (field === 'email' || field === 'password') {
          setError(field, { type: 'manual', message: issue.message })
        }
      }
      return
    }

    setNotice(
      'Authentication is not implemented yet. Sign-in, sessions, and roles arrive in Phase 3.',
    )
  }

  return (
    <div className="grid min-h-screen lg:grid-cols-2">
      <section className="relative hidden overflow-hidden bg-primary px-10 py-12 text-primary-foreground lg:flex lg:flex-col lg:justify-between">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_20%_20%,rgba(255,255,255,0.18),transparent_45%),radial-gradient(circle_at_80%_70%,rgba(255,255,255,0.12),transparent_40%)]" />
        <div className="relative">
          <Link
            to="/dashboard"
            className="inline-flex items-center gap-3 rounded-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/70"
          >
            <span className="flex size-11 items-center justify-center rounded-xl bg-white/15">
              <ShieldCheck className="size-6" aria-hidden="true" />
            </span>
            <span className="flex flex-col leading-none">
              <span className="text-xl font-semibold tracking-tight">TrustVault</span>
              <span className="mt-1 text-[10px] font-medium uppercase tracking-[0.2em] text-white/70">
                Secure document vault
              </span>
            </span>
          </Link>
        </div>

        <div className="relative max-w-md space-y-6">
          <p className="text-xs font-semibold uppercase tracking-[0.24em] text-white/70">
            Access enforced by the backend
          </p>
          <h1 className="text-3xl font-semibold leading-tight tracking-tight">
            Share documents with confidence, not hope.
          </h1>
          <p className="text-sm leading-6 text-white/80">
            TrustVault is designed around named-user, per-document permissions and a
            tamper-evident audit trail. Frontend controls are never the security boundary.
          </p>
          <ul className="space-y-3 text-sm text-white/85">
            <li className="flex items-start gap-3">
              <LockKeyhole className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
              Every request is authorized server-side.
            </li>
            <li className="flex items-start gap-3">
              <ShieldCheck className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
              Uploads, downloads, and permission changes are audited.
            </li>
          </ul>
        </div>

        <p className="relative text-xs text-white/60">
          Phase 1 scaffold · No production authentication exists yet.
        </p>
      </section>

      <section className="flex min-h-screen items-center justify-center px-4 py-12 sm:px-8">
        <div className="w-full max-w-md space-y-8">
          <div className="lg:hidden">
            <BrandMark to="/login" />
          </div>

          <div className="space-y-2">
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-primary">
              Welcome back
            </p>
            <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">Sign in</h1>
            <p className="text-sm leading-6 text-muted-foreground">
              This form is a Phase 1 placeholder. Authentication is intentionally not connected
              to a backend yet.
            </p>
          </div>

          <form className="space-y-5" onSubmit={handleSubmit(onSubmit)} noValidate>
            <div className="space-y-2">
              <label htmlFor="email" className="text-sm font-medium">
                Email address
              </label>
              <Input
                id="email"
                type="email"
                autoComplete="email"
                placeholder="you@example.com"
                aria-invalid={errors.email ? true : undefined}
                aria-describedby={errors.email ? 'email-error' : undefined}
                {...register('email')}
              />
              {errors.email ? (
                <p id="email-error" className="text-sm text-destructive">
                  {errors.email.message}
                </p>
              ) : null}
            </div>

            <div className="space-y-2">
              <label htmlFor="password" className="text-sm font-medium">
                Password
              </label>
              <Input
                id="password"
                type="password"
                autoComplete="current-password"
                placeholder="At least 8 characters"
                aria-invalid={errors.password ? true : undefined}
                aria-describedby={errors.password ? 'password-error' : undefined}
                {...register('password')}
              />
              {errors.password ? (
                <p id="password-error" className="text-sm text-destructive">
                  {errors.password.message}
                </p>
              ) : null}
            </div>

            <Button type="submit" className="w-full" size="lg">
              Continue
              <ArrowRight className="size-4" aria-hidden="true" />
            </Button>
          </form>

          <div
            role="status"
            aria-live="polite"
            className={notice ? 'rounded-lg border border-accent bg-accent/60 p-4 text-sm' : 'sr-only'}
          >
            {notice}
          </div>

          <p className="text-sm text-muted-foreground">
            <Link
              to="/dashboard"
              className="font-medium text-primary underline-offset-4 hover:underline"
            >
              Return to the dashboard
            </Link>
          </p>
        </div>
      </section>
    </div>
  )
}
