import { useEffect, useRef, useState } from 'react'
import { ArrowLeft, ArrowRight, LoaderCircle, ShieldCheck } from 'lucide-react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { z } from 'zod'
import { useAuth } from '@/auth/useAuth'
import { AuthLoadingScreen } from '@/components/AuthLoadingScreen'
import { BrandMark } from '@/components/BrandMark'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  requestPasswordRecovery,
  updatePasswordRecovery,
  verifyPasswordRecovery,
} from '@/services/auth'
import { getApiErrorMessage } from '@/services/api'

const PASSWORD_MIN_LENGTH = 12
const PASSWORD_MAX_BYTES = 72
const OTP_LENGTH = 8
const emailSchema = z.string().trim().email('Enter a valid email address.')
const passwordSchema = z
  .string()
  .min(PASSWORD_MIN_LENGTH, `Password must be at least ${PASSWORD_MIN_LENGTH} characters.`)
  .refine(
    (password) => new TextEncoder().encode(password).length <= PASSWORD_MAX_BYTES,
    `Password must be ${PASSWORD_MAX_BYTES} bytes or fewer when UTF-8 encoded.`,
  )

function recoveryError(error) {
  return getApiErrorMessage(error)
}

function recoveryRetryAfter(error) {
  if (error?.response?.status !== 429) return 0

  const retryAfter = Number.parseInt(error.response.headers?.['retry-after'], 10)
  return Number.isSafeInteger(retryAfter) && retryAfter > 0 ? retryAfter : 60
}

export function PasswordRecoveryPage() {
  const { status } = useAuth()
  const navigate = useNavigate()
  const [step, setStep] = useState('email')
  const [email, setEmail] = useState('')
  const [codeDigits, setCodeDigits] = useState(Array(OTP_LENGTH).fill(''))
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [isBusy, setIsBusy] = useState(false)
  const [cooldown, setCooldown] = useState(0)
  const codeInputs = useRef([])
  const code = codeDigits.join('')

  useEffect(() => {
    if (cooldown <= 0) return undefined
    const timer = window.setTimeout(() => setCooldown((current) => current - 1), 1000)
    return () => window.clearTimeout(timer)
  }, [cooldown])

  async function sendCode(event) {
    event.preventDefault()
    setError('')
    setMessage('')
    const parsed = emailSchema.safeParse(email)
    if (!parsed.success) {
      setError(parsed.error.issues[0]?.message || 'Enter a valid email address.')
      return
    }

    setIsBusy(true)
    try {
      const normalizedEmail = parsed.data.toLowerCase()
      await requestPasswordRecovery(normalizedEmail)
      setEmail(normalizedEmail)
      setCodeDigits(Array(OTP_LENGTH).fill(''))
      setStep('code')
      setCooldown(60)
      setMessage(
        'If an account exists for this email address, a verification code will be sent.',
      )
    } catch (requestError) {
      const retryAfter = recoveryRetryAfter(requestError)
      if (retryAfter) setCooldown(retryAfter)
      setError(recoveryError(requestError))
    } finally {
      setIsBusy(false)
    }
  }

  async function resendCode() {
    if (isBusy || cooldown > 0) return
    setError('')
    setMessage('')
    setIsBusy(true)
    try {
      await requestPasswordRecovery(email)
      setCooldown(60)
      setMessage(
        'If an account exists for this email address, a verification code will be sent.',
      )
    } catch (requestError) {
      const retryAfter = recoveryRetryAfter(requestError)
      if (retryAfter) setCooldown(retryAfter)
      setError(recoveryError(requestError))
    } finally {
      setIsBusy(false)
    }
  }

  async function verifyCode(event) {
    event.preventDefault()
    setError('')
    if (!/^[0-9]{8}$/.test(code)) {
      setError('Enter the eight-digit verification code.')
      return
    }

    setIsBusy(true)
    try {
      await verifyPasswordRecovery(email, code)
      setCodeDigits(Array(OTP_LENGTH).fill(''))
      setStep('password')
    } catch (verifyError) {
      setError(recoveryError(verifyError))
    } finally {
      setIsBusy(false)
    }
  }

  function updateCodeFromInput(index, value) {
    const digits = value.replace(/[^0-9]/g, '')
    if (!digits) {
      if (!value) {
        setCodeDigits((current) =>
          current.map((digit, digitIndex) => (digitIndex === index ? '' : digit)),
        )
      }
      return
    }

    const insertedDigits = digits.slice(0, OTP_LENGTH - index).split('')
    setCodeDigits((current) => {
      const next = [...current]
      insertedDigits.forEach((digit, offset) => {
        next[index + offset] = digit
      })
      return next
    })
    codeInputs.current[Math.min(index + insertedDigits.length, OTP_LENGTH - 1)]?.focus()
  }

  function handleCodeKeyDown(event, index) {
    if (event.key === 'Backspace' && !codeDigits[index] && index > 0) {
      event.preventDefault()
      setCodeDigits((current) =>
        current.map((digit, digitIndex) => (digitIndex === index - 1 ? '' : digit)),
      )
      codeInputs.current[index - 1]?.focus()
    } else if (event.key === 'ArrowLeft' && index > 0) {
      event.preventDefault()
      codeInputs.current[index - 1]?.focus()
    } else if (event.key === 'ArrowRight' && index < OTP_LENGTH - 1) {
      event.preventDefault()
      codeInputs.current[index + 1]?.focus()
    }
  }

  function handleCodePaste(event, index) {
    event.preventDefault()
    const digits = event.clipboardData
      .getData('text')
      .replace(/[^0-9]/g, '')
      .slice(0, OTP_LENGTH - index)
    if (!digits) return

    const pastedDigits = digits.split('')
    setCodeDigits((current) => {
      const next = [...current]
      pastedDigits.forEach((digit, offset) => {
        next[index + offset] = digit
      })
      return next
    })
    codeInputs.current[Math.min(index + pastedDigits.length, OTP_LENGTH - 1)]?.focus()
  }

  async function updatePassword(event) {
    event.preventDefault()
    setError('')
    const parsed = passwordSchema.safeParse(password)
    if (!parsed.success) {
      setError(parsed.error.issues[0]?.message || 'Enter a valid password.')
      return
    }
    if (password !== confirmPassword) {
      setError('Passwords do not match.')
      return
    }

    setIsBusy(true)
    try {
      await updatePasswordRecovery(password)
      setPassword('')
      setConfirmPassword('')
      setCodeDigits(Array(OTP_LENGTH).fill(''))
      setEmail('')
      navigate('/login', {
        replace: true,
        state: { recoveryMessage: 'Password updated. Sign in with your new password.' },
      })
    } catch (updateError) {
      setError(recoveryError(updateError))
    } finally {
      setIsBusy(false)
    }
  }

  function returnToEmail() {
    setError('')
    setMessage('')
    setCodeDigits(Array(OTP_LENGTH).fill(''))
    setStep('email')
  }

  const titles = {
    email: 'Forgot Password?',
    code: 'Verify Your Email',
    password: 'Create a New Password',
  }
  const descriptions = {
    email: 'Enter your registered email address to receive an eight-digit verification code.',
    code: 'Enter the eight-digit code sent to your email address.',
    password: 'Choose a new password for your TrustVault account.',
  }

  if (status === 'loading') {
    return <AuthLoadingScreen />
  }
  if (status === 'authenticated') {
    return <Navigate to="/dashboard" replace />
  }

  return (
    <div className="grid min-h-screen lg:grid-cols-2">
      <section className="relative hidden overflow-hidden bg-primary px-10 py-12 text-primary-foreground lg:flex lg:flex-col lg:justify-between">
        <Link
          to="/login"
          className="inline-flex w-fit items-center gap-3 rounded-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/70"
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
        <p className="relative max-w-md text-sm leading-6 text-white/80">
          Verify your email before changing your password. Recovery codes expire and can
          only be used once.
        </p>
        <p className="relative text-xs text-white/60">
          Account roles and document permissions are unchanged by password recovery.
        </p>
      </section>

      <section className="flex min-h-screen items-center justify-center px-4 py-12 sm:px-8">
        <div className="w-full max-w-md space-y-8">
          <div className="lg:hidden">
            <BrandMark to="/login" />
          </div>
          <div className="space-y-2">
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-primary">
              Account recovery
            </p>
            <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">
              {titles[step]}
            </h1>
            <p className="text-sm leading-6 text-muted-foreground">
              {descriptions[step]}
            </p>
          </div>

          {error ? (
            <div role="alert" className="rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">
              {error}
            </div>
          ) : null}
          {message ? (
            <div role="status" className="rounded-lg border border-primary/20 bg-primary/5 px-4 py-3 text-sm text-foreground">
              {message}
            </div>
          ) : null}

          {step === 'email' ? (
            <form className="space-y-5" onSubmit={sendCode} noValidate>
              <div className="space-y-2">
                <label htmlFor="recovery-email" className="text-sm font-medium">
                  Email Address
                </label>
                <Input
                  id="recovery-email"
                  type="email"
                  autoComplete="email"
                  autoCapitalize="none"
                  spellCheck={false}
                  required
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  disabled={isBusy}
                />
              </div>
              <Button
                type="submit"
                className="w-full"
                size="lg"
                disabled={isBusy || cooldown > 0}
              >
                {isBusy ? <LoaderCircle className="size-4 animate-spin" aria-hidden="true" /> : null}
                {cooldown > 0 ? `Try again in ${cooldown}s` : 'Send OTP'}
              </Button>
            </form>
          ) : null}

          {step === 'code' ? (
            <form className="space-y-5" onSubmit={verifyCode} noValidate>
              <div className="space-y-2">
                <p id="recovery-code-label" className="text-sm font-medium">
                  Eight-digit verification code
                </p>
                <div
                  className="flex justify-between gap-1.5 sm:gap-2"
                  role="group"
                  aria-labelledby="recovery-code-label"
                  aria-describedby="recovery-code-help"
                >
                  {codeDigits.map((digit, index) => (
                    <Input
                      key={index}
                      ref={(element) => {
                        codeInputs.current[index] = element
                      }}
                      aria-label={`Verification code digit ${index + 1}`}
                      type="text"
                      inputMode="numeric"
                      autoComplete={index === 0 ? 'one-time-code' : 'off'}
                      pattern="[0-9]*"
                      maxLength={OTP_LENGTH}
                      required
                      value={digit}
                      onChange={(event) =>
                        updateCodeFromInput(index, event.target.value)
                      }
                      onKeyDown={(event) => handleCodeKeyDown(event, index)}
                      onPaste={(event) => handleCodePaste(event, index)}
                      disabled={isBusy}
                      className="size-9 px-0 text-center text-base font-semibold sm:size-11 sm:text-lg"
                    />
                  ))}
                </div>
                <p id="recovery-code-help" className="text-xs text-muted-foreground">
                  Sent to {email}
                </p>
              </div>
              <Button
                type="submit"
                className="w-full"
                size="lg"
                disabled={isBusy || code.length !== OTP_LENGTH}
              >
                {isBusy ? <LoaderCircle className="size-4 animate-spin" aria-hidden="true" /> : null}
                Verify OTP
              </Button>
              <div className="flex items-center justify-between text-sm">
                <button
                  type="button"
                  className="font-medium text-primary underline-offset-4 hover:underline disabled:text-muted-foreground"
                  onClick={resendCode}
                  disabled={isBusy || cooldown > 0}
                >
                  {cooldown > 0 ? `Resend code in ${cooldown}s` : 'Resend Code'}
                </button>
                <button
                  type="button"
                  className="inline-flex items-center gap-1 text-muted-foreground hover:text-foreground"
                  onClick={returnToEmail}
                  disabled={isBusy}
                >
                  <ArrowLeft className="size-3.5" aria-hidden="true" />
                  Change email
                </button>
              </div>
            </form>
          ) : null}

          {step === 'password' ? (
            <form className="space-y-5" onSubmit={updatePassword} noValidate>
              <div className="space-y-2">
                <label htmlFor="new-password" className="text-sm font-medium">
                  New Password
                </label>
                <Input
                  id="new-password"
                  type="password"
                  autoComplete="new-password"
                  required
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  disabled={isBusy}
                />
              </div>
              <div className="space-y-2">
                <label htmlFor="confirm-new-password" className="text-sm font-medium">
                  Confirm New Password
                </label>
                <Input
                  id="confirm-new-password"
                  type="password"
                  autoComplete="new-password"
                  required
                  value={confirmPassword}
                  onChange={(event) => setConfirmPassword(event.target.value)}
                  disabled={isBusy}
                />
              </div>
              <Button type="submit" className="w-full" size="lg" disabled={isBusy}>
                {isBusy ? <LoaderCircle className="size-4 animate-spin" aria-hidden="true" /> : null}
                Update Password
                {!isBusy ? <ArrowRight className="size-4" aria-hidden="true" /> : null}
              </Button>
            </form>
          ) : null}

          <p className="text-sm text-muted-foreground">
            Remembered your password?{' '}
            <Link to="/login" className="font-medium text-primary underline-offset-4 hover:underline">
              Return to Login
            </Link>
          </p>
        </div>
      </section>
    </div>
  )
}
