import { useEffect, useRef, useState } from 'react'
import { ArrowLeft, LoaderCircle, ShieldCheck } from 'lucide-react'
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '@/auth/useAuth'
import { AuthLoadingScreen } from '@/components/AuthLoadingScreen'
import { BrandMark } from '@/components/BrandMark'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { getApiErrorMessage } from '@/services/api'
import { resendEmailConfirmation } from '@/services/auth'

const OTP_LENGTH = 8
const DEFAULT_RESEND_COOLDOWN = 60

export function VerifyAccountPage() {
  const { status, verifySignup } = useAuth()
  const location = useLocation()
  const navigate = useNavigate()

  const email = location.state?.email ?? null
  const accountCreated = location.state?.accountCreated ?? true

  const [codeDigits, setCodeDigits] = useState(Array(OTP_LENGTH).fill(''))
  const [error, setError] = useState('')
  const [message, setMessage] = useState(
    accountCreated
      ? 'We sent an 8-digit verification code and a verification link to your email address. Enter the code below, or click the link in that email to sign in automatically.'
      : 'This email already has an account that is not verified yet. We sent a new 8-digit code and verification link. Enter the code below, or click the link, to finish setting it up.',
  )
  const [isBusy, setIsBusy] = useState(false)
  const [cooldown, setCooldown] = useState(DEFAULT_RESEND_COOLDOWN)
  const codeInputs = useRef([])
  const code = codeDigits.join('')

  useEffect(() => {
    if (cooldown <= 0) return undefined
    const timer = window.setTimeout(() => setCooldown((c) => c - 1), 1000)
    return () => window.clearTimeout(timer)
  }, [cooldown])

  if (status === 'loading') return <AuthLoadingScreen />
  if (status === 'authenticated') return <Navigate to="/dashboard" replace />
  // Guard: must arrive here from registration with an email in state
  if (!email) return <Navigate to="/register" replace />

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
      const result = await verifySignup(email, code)
      if (!result.session) {
        setMessage('Your account has been verified. Sign in to continue.')
        navigate('/login', { replace: true })
        return
      }
      navigate('/dashboard', {
        replace: true,
        state: { registrationMessage: 'Your account has been verified successfully.' },
      })
    } catch (verifyError) {
      setError(getApiErrorMessage(verifyError))
      setIsBusy(false)
    }
  }

  async function resendCode() {
    if (isBusy || cooldown > 0) return
    setError('')
    setMessage('')
    setIsBusy(true)
    try {
      await resendEmailConfirmation(email)
      setCooldown(DEFAULT_RESEND_COOLDOWN)
      setMessage('A new verification code has been requested. Check your inbox and spam folder.')
    } catch (resendError) {
      setError(getApiErrorMessage(resendError))
    } finally {
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
          Enter the eight-digit code sent to your email address, or click the
          verification link in the same email, to verify your new TrustVault
          account. Codes expire and can only be used once.
        </p>
        <p className="relative text-xs text-white/60">
          Your account will have normal user privileges after verification.
        </p>
      </section>

      <section className="flex min-h-screen items-center justify-center px-4 py-12 sm:px-8">
        <div className="w-full max-w-md space-y-8">
          <div className="lg:hidden">
            <BrandMark to="/login" />
          </div>
          <div className="space-y-2">
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-primary">
              Account verification
            </p>
            <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">
              Verify Your Account
            </h1>
            <p className="text-sm leading-6 text-muted-foreground">
              Enter the eight-digit code sent to <strong>{email}</strong>, or
              click the verification link in the same email. Check your spam
              folder if it has not arrived within a few minutes.
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

          <form className="space-y-5" onSubmit={verifyCode} noValidate>
            <div className="space-y-2">
              <p id="verify-code-label" className="text-sm font-medium">
                Eight-digit verification code
              </p>
              <div
                className="flex justify-between gap-1.5 sm:gap-2"
                role="group"
                aria-labelledby="verify-code-label"
                aria-describedby="verify-code-help"
              >
                {codeDigits.map((digit, index) => (
                  <Input
                    key={index}
                    ref={(el) => { codeInputs.current[index] = el }}
                    aria-label={`Verification code digit ${index + 1}`}
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
              <p id="verify-code-help" className="text-xs text-muted-foreground">
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
              Verify Account
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
              <Link
                to="/register"
                className="inline-flex items-center gap-1 text-muted-foreground hover:text-foreground"
              >
                <ArrowLeft className="size-3.5" aria-hidden="true" />
                Back to Register
              </Link>
            </div>
          </form>

          <p className="text-sm text-muted-foreground">
            Already have an account?{' '}
            <Link to="/login" className="font-medium text-primary underline-offset-4 hover:underline">
              Sign in
            </Link>
          </p>
        </div>
      </section>
    </div>
  )
}
