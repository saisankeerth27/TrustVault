import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { ArrowRight, History, LoaderCircle, LockKeyhole, Share2, ShieldCheck } from 'lucide-react'
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom'
import { z } from 'zod'
import { useAuth } from '@/auth/useAuth'
import { AuthLoadingScreen } from '@/components/AuthLoadingScreen'
import { BrandMark } from '@/components/BrandMark'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { getApiErrorMessage } from '@/services/api'

const loginSchema = z.object({
  email: z.string().trim().email({ message: 'Enter a valid email address.' }),
  password: z.string().min(1, { message: 'Enter your password.' }),
})

function redirectPathFrom(state) {
  if (
    state &&
    typeof state === 'object' &&
    'from' in state &&
    typeof state.from === 'string' &&
    state.from.startsWith('/') &&
    !state.from.startsWith('//')
  ) {
    return state.from
  }
  return '/dashboard'
}

export function LoginPage() {
  const { status, login } = useAuth()
  const location = useLocation()
  const navigate = useNavigate()
  const [serverError, setServerError] = useState(null)
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
    setError,
    clearErrors,
  } = useForm({
    defaultValues: { email: '', password: '' },
  })

  const destination = redirectPathFrom(location.state)

  if (status === 'loading') {
    return <AuthLoadingScreen />
  }

  if (status === 'authenticated') {
    return <Navigate to={destination} replace />
  }

  const onSubmit = async (values) => {
    clearErrors()
    setServerError(null)
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

    try {
      await login(result.data)
      navigate(destination, { replace: true })
    } catch (error) {
      setServerError(getApiErrorMessage(error))
    }
  }

  return (
    <div className="grid min-h-screen lg:grid-cols-2">
      <section className="relative hidden overflow-hidden bg-primary px-10 py-12 text-primary-foreground lg:flex lg:flex-col lg:justify-between">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_20%_20%,rgba(255,255,255,0.18),transparent_45%),radial-gradient(circle_at_80%_70%,rgba(255,255,255,0.12),transparent_40%)]" />
        <div className="relative">
          <Link
            to="/login"
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
            Secure access
          </p>
          <h1 className="text-3xl font-semibold leading-tight tracking-tight">
            Your Documents. Your Control.
          </h1>
          <p className="text-sm leading-6 text-white/80">
            Securely manage your documents, share access with trusted people, and stay in control of who can view or edit your files.
          </p>
          <ul className="space-y-3 text-sm text-white/85">
            <li className="flex items-start gap-3">
              <Share2 className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
              Secure Document Sharing
            </li>
            <li className="flex items-start gap-3">
              <LockKeyhole className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
              Controlled Read and Edit Access
            </li>
            <li className="flex items-start gap-3">
              <History className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
              Document Version History
            </li>
            <li className="flex items-start gap-3">
              <ShieldCheck className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
              Activity and Access Tracking
            </li>
          </ul>
        </div>

        <p className="relative text-xs text-white/60">
          Normal user accounts can be created through public registration. Administrator
          accounts are provisioned by an existing administrator.
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
              Sign in with your TrustVault account. Contact an administrator if you need
              administrator access.
            </p>
          </div>

          {typeof location.state?.recoveryMessage === 'string' ? (
            <div role="status" className="rounded-lg border border-primary/20 bg-primary/5 px-4 py-3 text-sm">
              {location.state.recoveryMessage}
            </div>
          ) : null}

          <form className="space-y-5" onSubmit={handleSubmit(onSubmit)} noValidate>
            {serverError ? (
              <div
                role="alert"
                className="rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive"
              >
                {serverError}
              </div>
            ) : null}

            <div className="space-y-2">
              <label htmlFor="email" className="text-sm font-medium">
                Email address
              </label>
              <Input
                id="email"
                type="email"
                autoComplete="email"
                autoCapitalize="none"
                spellCheck={false}
                placeholder="you@example.com"
                disabled={isSubmitting}
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
                placeholder="Enter your password"
                disabled={isSubmitting}
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

            <div className="-mt-2 text-right">
              <Link
                to="/recover-password"
                className="text-sm font-medium text-primary underline-offset-4 hover:underline"
              >
                Forgot Password?
              </Link>
            </div>

            <Button type="submit" className="w-full" size="lg" disabled={isSubmitting}>
              {isSubmitting ? (
                <>
                  <LoaderCircle className="size-4 animate-spin" aria-hidden="true" />
                  Signing in...
                </>
              ) : (
                <>
                  Continue
                  <ArrowRight className="size-4" aria-hidden="true" />
                </>
              )}
            </Button>
          </form>

          <p className="text-sm text-muted-foreground">
            New to TrustVault?{' '}
            <Link
              to="/register"
              className="font-medium text-primary underline-offset-4 hover:underline"
            >
              Create a user account
            </Link>
          </p>

          <p className="text-xs leading-5 text-muted-foreground">
            Access is rate limited. Repeated failed attempts are rejected temporarily. If you
            believe an account was compromised, contact an administrator immediately.
          </p>
        </div>
      </section>
    </div>
  )
}
