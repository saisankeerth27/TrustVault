import { useEffect, useRef, useState } from 'react'
import { ArrowLeft, ArrowRight, LoaderCircle, ShieldCheck } from 'lucide-react'
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom'
import { z } from 'zod'
import { useAuth } from '@/auth/useAuth'
import { AuthLoadingScreen } from '@/components/AuthLoadingScreen'
import { BrandMark } from '@/components/BrandMark'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { getApiErrorMessage } from '@/services/api'
import { requestOtpLogin } from '@/services/auth'

const OTP_LENGTH = 8
const emailSchema = z.string().trim().email('Enter a valid email address.')

function otpError(error) {
  return getApiErrorMessage(error)
}

function otpRetryAfter(error) {
  if (error?.response?.status !== 429) return 0
  const retryAfter = Number.parseInt(error.response.headers?.['retry-after'], 10)
  return Number.isSafeInteger(retryAfter) && retryAfter > 0 ? retryAfter : 60
}

export function OtpLoginPage() {
  const { status, verifyLoginOtp } = useAuth()
  const location = useLocation()
  const navigate = useNavigate()

  const [step, setStep] = useState('email')
  const [email, setEmail] = useState('')
  const [codeDigits, setCodeDigits] = useState(Array(OTP_LENGTH).fill(''))
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [isBusy, setIsBusy] = useState(false)
  const [cooldown, setCooldown] = useState(0)
  const codeInputs = useRef([])
  const code = codeDigits.join('')

  useEffect(() => {
    if (cooldown <= 0) return undefined
    const timer = window.setTimeout(() => setCooldown((c) => c - 1), 1000)
    return () => window.clearTimeout(timer)
  }, [cooldown])

  if (status === 'loading') return <AuthLoadingScreen />
  if (status === 'authenticated') return <Navigate to="/dashboard" replace />

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
      await requestOtpLogin(normalizedEmail)
      setEmail(normalizedEmail)
      setCodeDigits(Array(OTP_LENGTH).fill(''))
      setStep('code')
      setCooldown(60)
      setMessage(
        'If an account is registered for this email, a one-time code has been sent.',
      )
    } catch (requestError) {
      const retryAfter = otpRetryAfter(requestError)
      if (retryAfter) setCooldown(retryAfter)
      setError(otpError(requestError))
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
      await requestOtpLogin(email)
      setCooldown(60)
      setMessage(
        'If an account is registered for this email, a one-time code has been sent.',
      )
    } catch (requestError) {
      const retryAfter = otpRetryAfter(requestError)
      if (retryAfter) setCooldown(retryAfter)
      setError(otpError(requestError))
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
    if (isBusy) return
    setIsBusy(true)
    try {
      await verifyLoginOtp(email, code)
      navigate('/dashboard', { replace: true })
    } catch (verifyError) {
      setError(otpError(verifyError))
      setIsBusy(false)
    }
  }

  function updateCodeFromInput(index, value) {
    const digits = value.replace(/[^0-9]/g, '')
    if (!digits) {
      if (!value) {
        setCodeDigits((current) =>
          current.map((digit, i) => (i === index ? '' : digit)),
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
        current.map((digit, i) => (i === index - 1 ? '' : digit)),
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

  function returnToEmail() {
    setError('')
    setMessage('')
    setCodeDigits(Array(OTP_LENGTH).fill(''))
    setStep('email')
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
        <div className="relative max-w-md space-y-4">
          <p className="text-xs font-semibold uppercase tracking-[0.24em] text-white/70">
            Passwordless sign-in
          </p>
          <p className="text-3xl font-semibold leading-tight tracking-tight">
            Sign in without a password
          </p>
          <p className="text-sm leading-6 text-white/80">
            Enter your registered email address and we'll send you a one-time
            code. No password required.
          </p>
        </div>
        <p className="relative text-xs text-white/60">
          One-time codes expire quickly and can only be used once. Codes are only
          sent to registered TrustVault accounts.
        </p>
      </section>

      <section className="flex min-h-screen items-center justify-center px-4 py-12 sm:px-8">
        <div className="w-full max-w-md space-y-8">
          <div className="lg:hidden">
            <BrandMark to="/login" />
          </div>
          <div className="space-y-2">
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-primary">
              Passwordless sign-in
            </p>
            <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">
              {step === 'email' ? 'Sign in with OTP' : 'Enter Your Code'}
            </h1>
            <p className="text-sm leading-6 text-muted-foreground">
              {step === 'email'
                ? 'Enter your registered email address to receive a one-time sign-in code.'
                : `Enter the eight-digit code sent to ${email}.`}
            </p>
          </div>

          {error ? (
            <div role="alert" className="rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">
              {error}
              {error.toLowerCase().includes('not registered') ? (
                <p className="mt-2">
                  <Link to="/register" className="underline font-medium">
                    Create Account
                  </Link>
                </p>
              ) : null}
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
                <label htmlFor="otp-login-email" className="text-sm font-medium">
                  Email address
                </label>
                <Input
                  id="otp-login-email"
                  type="email"
                  autoComplete="email"
                  autoCapitalize="none"
                  spellCheck={false}
                  placeholder="you@example.com"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  disabled={isBusy}
                />
              </div>
              <Button
                type="submit"
                className="w-full"
                size="lg"
                disabled={isBusy || cooldown > 0}
              >
                {isBusy ? (
                  <LoaderCircle className="size-4 animate-spin" aria-hidden="true" />
                ) : null}
                {cooldown > 0 ? `Try again in ${cooldown}s` : (
                  <>
                    Send One-Time Code
                    <ArrowRight className="size-4" aria-hidden="true" />
                  </>
                )}
              </Button>
            </form>
          ) : null}

          {step === 'code' ? (
            <form className="space-y-5" onSubmit={verifyCode} noValidate>
              <div className="space-y-2">
                <p id="otp-login-code-label" className="text-sm font-medium">
                  Eight-digit verification code
                </p>
                <div
                  className="flex justify-between gap-1.5 sm:gap-2"
                  role="group"
                  aria-labelledby="otp-login-code-label"
                  aria-describedby="otp-login-code-help"
                >
                  {codeDigits.map((digit, index) => (
                    <Input
                      key={index}
                      ref={(el) => { codeInputs.current[index] = el }}
                      aria-label={`Sign-in code digit ${index + 1}`}
                      type="text"
                      inputMode="numeric"
                      autoComplete={index === 0 ? 'one-time-code' : 'off'}
                      pattern="[0-9]*"
                      maxLength={OTP_LENGTH}
                      required
                      value={digit}
                      onChange={(e) => updateCodeFromInput(index, e.target.value)}
                      onKeyDown={(e) => handleCodeKeyDown(e, index)}
                      onPaste={(e) => handleCodePaste(e, index)}
                      disabled={isBusy}
                      className="size-9 px-0 text-center text-base font-semibold sm:size-11 sm:text-lg"
                    />
                  ))}
                </div>
                <p id="otp-login-code-help" className="text-xs text-muted-foreground">
                  Sent to {email}
                </p>
              </div>
              <Button
                type="submit"
                className="w-full"
                size="lg"
                disabled={isBusy || code.length !== OTP_LENGTH}
              >
                {isBusy ? (
                  <LoaderCircle className="size-4 animate-spin" aria-hidden="true" />
                ) : null}
                Verify and Sign In
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

          <p className="text-sm text-muted-foreground">
            Have a password?{' '}
            <Link to="/login" className="font-medium text-primary underline-offset-4 hover:underline">
              Sign in with password
            </Link>
          </p>
        </div>
      </section>
    </div>
  )
}
