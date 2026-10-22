import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { ArrowRight, CheckCircle2, LoaderCircle, LockKeyhole, ShieldCheck } from 'lucide-react'
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom'
import { z } from 'zod'
import { useAuth } from '@/auth/useAuth'
import { AuthLoadingScreen } from '@/components/AuthLoadingScreen'
import { BrandMark } from '@/components/BrandMark'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { getApiErrorMessage } from '@/services/api'

const PASSWORD_MIN_LENGTH = 12
const PASSWORD_MAX_BYTES = 72

function passwordByteLength(value) {
  return new TextEncoder().encode(value).length
}

const registerSchema = z
  .object({
    name: z
      .string()
      .trim()
      .min(1, { message: 'Enter your name.' })
      .max(255, { message: 'Name must be 255 characters or fewer.' }),
    email: z.string().trim().email({ message: 'Enter a valid email address.' }),
    password: z
      .string()
      .min(PASSWORD_MIN_LENGTH, {
        message: `Password must be at least ${PASSWORD_MIN_LENGTH} characters long.`,
      })
      .refine((value) => passwordByteLength(value) <= PASSWORD_MAX_BYTES, {
        message: 'Password must be 72 bytes or fewer when UTF-8 encoded.',
      }),
    confirmPassword: z.string(),
  })
  .refine((values) => values.password === values.confirmPassword, {
    path: ['confirmPassword'],
    message: 'Passwords do not match.',
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

export function RegisterPage() {
  const { status, register: registerAccount } = useAuth()
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
    defaultValues: { name: '', email: '', password: '', confirmPassword: '' },
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
    const result = registerSchema.safeParse(values)

    if (!result.success) {
      for (const issue of result.error.issues) {
        const field = issue.path[0]
        if (
          field === 'name' ||
          field === 'email' ||
          field === 'password' ||
          field === 'confirmPassword'
        ) {
          setError(field, { type: 'manual', message: issue.message })
        }
      }
      return
    }

    try {
      await registerAccount({
        name: result.data.name,
        email: result.data.email.toLowerCase(),
        password: result.data.password,
      })
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
            Public registration
          </p>
          <h1 className="text-3xl font-semibold leading-tight tracking-tight">
            Create an account, upload your documents, and share on your terms.
          </h1>
          <p className="text-sm leading-6 text-white/80">
            New accounts are normal users. You can upload and own documents immediately, and
            documents appear when another owner grants you READ or EDIT access.
          </p>
          <ul className="space-y-3 text-sm text-white/85">
            <li className="flex items-start gap-3">
              <CheckCircle2 className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
              Own your uploads and share them with named users using READ or EDIT grants.
            </li>
            <li className="flex items-start gap-3">
              <LockKeyhole className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
              Passwords are hashed server-side and refresh credentials stay in an HttpOnly cookie.
            </li>
          </ul>
        </div>

        <p className="relative text-xs text-white/60">
          Need administrator oversight access? Ask an existing administrator to update your
          account role.
        </p>
      </section>

      <section className="flex min-h-screen items-center justify-center px-4 py-12 sm:px-8">
        <div className="w-full max-w-md space-y-8">
          <div className="lg:hidden">
            <BrandMark to="/login" />
          </div>

          <div className="space-y-2">
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-primary">
              Get started
            </p>
            <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">Create account</h1>
            <p className="text-sm leading-6 text-muted-foreground">
              Register as a normal user. You will be signed in automatically after creating your
              account.
            </p>
          </div>

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
              <label htmlFor="register-name" className="text-sm font-medium">
                Full name
              </label>
              <Input
                id="register-name"
                type="text"
                autoComplete="name"
                placeholder="Your name"
                disabled={isSubmitting}
                aria-invalid={errors.name ? true : undefined}
                aria-describedby={errors.name ? 'register-name-error' : undefined}
                {...register('name')}
              />
              {errors.name ? (
                <p id="register-name-error" className="text-sm text-destructive">
                  {errors.name.message}
                </p>
              ) : null}
            </div>

            <div className="space-y-2">
              <label htmlFor="register-email" className="text-sm font-medium">
                Email address
              </label>
              <Input
                id="register-email"
                type="email"
                autoComplete="email"
                autoCapitalize="none"
                spellCheck={false}
                placeholder="you@example.com"
                disabled={isSubmitting}
                aria-invalid={errors.email ? true : undefined}
                aria-describedby={errors.email ? 'register-email-error' : undefined}
                {...register('email')}
              />
              {errors.email ? (
                <p id="register-email-error" className="text-sm text-destructive">
                  {errors.email.message}
                </p>
              ) : null}
            </div>

            <div className="space-y-2">
              <label htmlFor="register-password" className="text-sm font-medium">
                Password
              </label>
              <Input
                id="register-password"
                type="password"
                autoComplete="new-password"
                placeholder="At least 12 characters"
                disabled={isSubmitting}
                aria-invalid={errors.password ? true : undefined}
                aria-describedby={
                  errors.password ? 'register-password-error' : 'register-password-help'
                }
                {...register('password')}
              />
              <p id="register-password-help" className="text-xs leading-5 text-muted-foreground">
                Use at least 12 characters. Passphrases are welcome.
              </p>
              {errors.password ? (
                <p id="register-password-error" className="text-sm text-destructive">
                  {errors.password.message}
                </p>
              ) : null}
            </div>

            <div className="space-y-2">
              <label htmlFor="register-confirm-password" className="text-sm font-medium">
                Confirm password
              </label>
              <Input
                id="register-confirm-password"
                type="password"
                autoComplete="new-password"
                placeholder="Repeat your password"
                disabled={isSubmitting}
                aria-invalid={errors.confirmPassword ? true : undefined}
                aria-describedby={
                  errors.confirmPassword ? 'register-confirm-password-error' : undefined
                }
                {...register('confirmPassword')}
              />
              {errors.confirmPassword ? (
                <p id="register-confirm-password-error" className="text-sm text-destructive">
                  {errors.confirmPassword.message}
                </p>
              ) : null}
            </div>

            <Button type="submit" className="w-full" size="lg" disabled={isSubmitting}>
              {isSubmitting ? (
                <>
                  <LoaderCircle className="size-4 animate-spin" aria-hidden="true" />
                  Creating account...
                </>
              ) : (
                <>
                  Create account
                  <ArrowRight className="size-4" aria-hidden="true" />
                </>
              )}
            </Button>
          </form>

          <p className="text-sm text-muted-foreground">
            Already have an account?{' '}
            <Link
              to="/login"
              className="font-medium text-primary underline-offset-4 hover:underline"
            >
              Sign in
            </Link>
          </p>

          <p className="text-xs leading-5 text-muted-foreground">
            Registration is rate limited. Public sign-up always creates a normal user account.
          </p>
        </div>
      </section>
    </div>
  )
}
