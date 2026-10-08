import { useState } from 'react'
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext.jsx'
import { useToast } from '../components/Toast.jsx'
import { ErrorBanner, Spinner } from '../components/ui.jsx'
import AuthLayout from '../components/AuthLayout.jsx'

/**
 * Login page — Supabase Auth (email + password).
 *
 * SECURITY NOTES (Part B.3):
 *  - We never handle, hash or store the password ourselves; it goes straight to
 *    Supabase Auth over TLS and comes back as a session. No password in state
 *    beyond this component, no password in localStorage, no password in logs.
 *  - Error messages are deliberately generic. We surface Supabase's own message
 *    but never confirm whether an email address exists (that would be an account
 *    enumeration oracle). "Invalid login credentials" covers both cases.
 *  - The submit button is disabled while a request is in flight, which prevents
 *    double-submit (and double rate-limit hits on the auth endpoint).
 *
 * HICK'S LAW: this form is already at the minimum — n = 1 real decision ("sign
 * in"), with two data fields. We deliberately did NOT add social/OAuth buttons or
 * a "remember me" toggle, because each extra option multiplies decision time by
 * log₂(n) and none of them help a student reach the scanner faster. The one
 * addition is a Show/Hide toggle, which *removes* friction rather than adding a
 * choice (it is why the signup form needs no confirm-password field).
 */
export default function Login() {
  const { signIn, isAuthenticated, isEducator } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const toast = useToast()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  // Already signed in? Don't show the login form.
  if (isAuthenticated) {
    const from = location.state?.from
    return <Navigate to={from ?? (isEducator ? '/dashboard' : '/scanner')} replace />
  }

  async function handleSubmit(e) {
    e.preventDefault()
    setError(null)

    // Minimal client-side validation (Part C.2): instant feedback, no round trip.
    if (!email.trim() || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) {
      setError({ message: 'Please enter a valid email address.' })
      return
    }
    if (password.length < 6) {
      setError({ message: 'Password must be at least 6 characters.' })
      return
    }

    setBusy(true)
    try {
      await signIn(email, password)
      toast.success('Signed in securely. Session token active.')
      const from = location.state?.from
      navigate(from ?? (isEducator ? '/dashboard' : '/scanner'), { replace: true })
    } catch (err) {
      // Supabase returns "Invalid login credentials" for both unknown email and
      // wrong password — we keep that ambiguity, it prevents enumeration.
      setError({ message: friendlyAuthError(err) })
    } finally {
      setBusy(false)
    }
  }

  return (
    <AuthLayout
      title="Welcome back"
      subtitle="Sign in to scan images and verify claims."
      footer={
        <p className="text-sm text-ink-muted text-center">
          New to TruthGuard?{' '}
          <Link to="/signup" className="text-teal hover:underline">
            Create an account
          </Link>
        </p>
      }
    >
      <form onSubmit={handleSubmit} noValidate className="space-y-4">
        <ErrorBanner error={error} onDismiss={() => setError(null)} />

        <div>
          <label className="label" htmlFor="email">
            Email address
          </label>
          <input
            id="email"
            name="email"
            type="email"
            className="input"
            placeholder="you@college.edu"
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            maxLength={254}
          />
        </div>

        <div>
          <label className="label" htmlFor="password">
            Password
          </label>
          <div className="relative">
            <input
              id="password"
              name="password"
              type={showPassword ? 'text' : 'password'}
              className="input pr-20"
              placeholder="••••••••"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              minLength={6}
              maxLength={128}
            />
            <button
              type="button"
              onClick={() => setShowPassword((v) => !v)}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-ink-muted hover:text-teal transition press"
            >
              {showPassword ? 'Hide' : 'Show'}
            </button>
          </div>
        </div>

        <button type="submit" className="btn-solid sheen press w-full !py-3.5" disabled={busy}>
          {busy ? (
            <>
              <Spinner size={16} className="border-navy/30 border-t-navy" /> Verifying credentials…
            </>
          ) : (
            'Sign in'
          )}
        </button>

        <p className="text-[11px] text-ink-muted/80 leading-relaxed">
          Protected by Supabase Auth. Passwords are hashed server-side with bcrypt; this app never
          sees or stores your password in plain text.
        </p>
      </form>
    </AuthLayout>
  )
}

/** Map Supabase auth errors to something a student can act on. */
export function friendlyAuthError(err) {
  const msg = String(err?.message ?? '').toLowerCase()
  if (msg.includes('invalid login credentials')) return 'Incorrect email or password. Please try again.'
  if (msg.includes('email not confirmed'))
    return 'Your email address is not confirmed yet. Check your inbox for the verification link.'
  if (msg.includes('rate limit') || msg.includes('too many requests'))
    return 'Too many attempts. Please wait a minute before trying again.'
  if (msg.includes('already registered') || msg.includes('already been registered'))
    return 'That email is already registered. Try signing in instead.'
  if (msg.includes('password should be at least'))
    return 'That password is too short — Supabase requires at least 6 characters.'
  if (msg.includes('failed to fetch') || msg.includes('fetch'))
    return 'Cannot reach the authentication server. Check your connection and Supabase configuration.'
  return err?.message ?? 'Authentication failed. Please try again.'
}
