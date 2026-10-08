import { useState } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext.jsx'
import { useToast } from '../components/Toast.jsx'
import { ErrorBanner, Spinner } from '../components/ui.jsx'
import AuthLayout from '../components/AuthLayout.jsx'
import MagneticButton from '../components/interactive/MagneticButton.jsx'
import ScrollReveal from '../components/interactive/ScrollReveal.jsx'
import { friendlyAuthError } from './Login.jsx'

/**
 * Signup page — Supabase Auth + role selection (Part A.1 / Part B.1).
 *
 * HOW THE ROLE IS PERSISTED (Part B.3):
 *   1. supabase.auth.signUp() creates the auth.users row and passes the chosen
 *      role in `options.data` (raw_user_meta_data).
 *   2. The Postgres trigger `on_auth_user_created -> handle_new_user()` fires and
 *      inserts the matching `profiles` row, preferring the meta_data role and
 *      defaulting to 'student'.
 *   3. The client then calls the SECURITY DEFINER function `set_my_role(role)`
 *      which sets the role exactly once (guarded by `profiles.role_locked`).
 *
 * SECURITY — LEAST PRIVILEGE BY DEFAULT:
 *   If anything goes wrong, the user is a STUDENT. Privilege is never granted by
 *   failure. The client also whitelists the role value ('educator' | 'student')
 *   before sending it, so a tampered form post cannot inject an arbitrary string
 *   into an enum-checked column.
 *
 * ---------------------------------------------------------------------------
 * HICK'S LAW APPLIED HERE — the single biggest win in the app
 * ---------------------------------------------------------------------------
 * Hick's Law: decision time ≈ a + b·log₂(n). Cutting n is worth more than any
 * amount of visual polish, so this form was reduced from FOUR decisions to TWO:
 *
 *   BEFORE (n = 4)                          AFTER (n = 2)
 *   1. email                                1. email
 *   2. password                             2. role  (default pre-selected)
 *   3. confirm password   ← REMOVED
 *   4. role
 *
 * Why removing "confirm password" is the right call, not a shortcut:
 *   • Password VISIBILITY is a better error-prevention mechanism than password
 *     DUPLICATION. The confirm field exists only because the field is masked;
 *     give the user a Show toggle and the reason for the second field disappears.
 *     (This is why Google, GitHub and Supabase's own dashboard dropped it.)
 *   • Every extra field multiplies abandonment. A masked retype is the highest-
 *     friction field in any signup form, and its failure mode (mismatch) is
 *     100% recoverable by simply remembering the password later.
 *   • We compensate with a live strength meter and an explicit minimum, so the
 *     user gets *immediate* feedback instead of a server round-trip.
 *   Supabase still enforces the minimum length server-side; nothing about
 *   password security is weakened — bcrypt hashing and transport encryption are
 *   untouched.
 *
 * The role selector pre-selects "Student" (the least-privileged and statistically
 * most common choice), so the modal case requires ZERO interaction: the user only
 * engages with it when they are an educator.
 */
export default function Signup() {
  const { signUp, isAuthenticated } = useAuth()
  const navigate = useNavigate()
  const toast = useToast()

  const [form, setForm] = useState({ email: '', password: '', role: 'student' })
  const [showPassword, setShowPassword] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [needsConfirmation, setNeedsConfirmation] = useState(false)

  if (isAuthenticated) return <Navigate to={form.role === 'educator' ? '/dashboard' : '/scanner'} replace />

  if (needsConfirmation) {
    return (
      <AuthLayout title="Check your inbox" subtitle="One more step before you can sign in.">
        <div className="glass p-5 text-sm text-ink-muted leading-relaxed">
          We sent a confirmation link to <span className="text-teal">{form.email}</span>. Click it,
          then return here and sign in. Your role has been saved as{' '}
          <span className="text-teal">{form.role}</span>.
          <p className="mt-3 text-xs">
            Tip for the demo: in Supabase → Authentication → Providers → Email you can turn off
            “Confirm email” so sign-up creates a session immediately.
          </p>
        </div>
        <Link to="/login" className="btn-primary press w-full mt-4">
          Go to sign in
        </Link>
      </AuthLayout>
    )
  }

  const strength = passwordStrength(form.password)
  const passwordReady = form.password.length >= 6

  function update(field) {
    return (e) => setForm((f) => ({ ...f, [field]: e.target.value }))
  }

  async function handleSubmit(e) {
    e.preventDefault()
    setError(null)

    // ---- Client-side validation (Part C.2) ----
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email.trim())) {
      setError({ message: 'Please enter a valid email address.' })
      return
    }
    if (form.password.length < 6) {
      setError({ message: 'Password must be at least 6 characters.' })
      return
    }
    if (!['student', 'educator'].includes(form.role)) {
      setError({ message: 'Please choose a valid account type.' })
      return
    }

    setBusy(true)
    try {
      const result = await signUp(form.email, form.password, form.role)
      if (result?.needsEmailConfirmation) {
        setNeedsConfirmation(true)
        return
      }
      toast.success(`Account created as ${form.role}. Welcome to TruthGuard AI.`)
      navigate(form.role === 'educator' ? '/dashboard' : '/scanner', { replace: true })
    } catch (err) {
      setError({ message: friendlyAuthError(err) })
    } finally {
      setBusy(false)
    }
  }

  return (
    <AuthLayout
      title="Create your account"
      subtitle="Two fields. Takes about ten seconds."
      footer={
        <p className="text-sm text-ink-muted text-center">
          Already have an account?{' '}
          <Link to="/login" className="text-teal hover:underline">
            Sign in
          </Link>
        </p>
      }
    >
      <ScrollReveal y={14}>
        <form onSubmit={handleSubmit} noValidate className="space-y-5">
          <ErrorBanner error={error} onDismiss={() => setError(null)} />

          {/* ------------------------- Decision 1: email ------------------------- */}
          <div>
            <label className="label" htmlFor="su-email">
              Email address
            </label>
            <input
              id="su-email"
              type="email"
              className="input"
              placeholder="you@college.edu"
              autoComplete="email"
              value={form.email}
              onChange={update('email')}
              required
              maxLength={254}
            />
          </div>

          {/* ------------------------ Decision 2: password ----------------------- */}
          <div>
            <label className="label" htmlFor="su-password">
              Password
            </label>
            <div className="relative">
              <input
                id="su-password"
                type={showPassword ? 'text' : 'password'}
                className="input pr-20"
                placeholder="At least 6 characters"
                autoComplete="new-password"
                value={form.password}
                onChange={update('password')}
                required
                minLength={6}
                maxLength={128}
                aria-describedby="pw-strength"
              />
              <button
                type="button"
                onClick={() => setShowPassword((v) => !v)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-ink-muted hover:text-teal transition press"
                aria-pressed={showPassword}
              >
                {showPassword ? 'Hide' : 'Show'}
              </button>
            </div>

            {/* Live feedback replaces the confirm-password field: the user can
                SEE what they typed, so there is nothing to re-type. */}
            <div id="pw-strength" className="flex items-center gap-2 mt-2">
              <div className="flex-1 h-1.5 rounded-full bg-navy border border-navy-border overflow-hidden">
                <div
                  className={`h-full transition-all duration-500 ease-out ${strength.color}`}
                  style={{ width: `${strength.pct}%` }}
                />
              </div>
              <span className={`text-[11px] w-16 text-right ${passwordReady ? 'text-ink-muted' : 'text-warn'}`}>
                {form.password ? strength.label : '6+ chars'}
              </span>
            </div>
          </div>

          {/* --------------------- Role: pre-selected default --------------------- */}
          <fieldset>
            <legend className="label">
              I am a… <span className="text-ink-muted/60">(Student is pre-selected)</span>
            </legend>
            <div className="grid grid-cols-2 gap-3">
              {ROLES.map((r) => {
                const active = form.role === r.value
                return (
                  <label
                    key={r.value}
                    className={`cursor-pointer rounded-xl border p-4 transition duration-200 press ${
                      active
                        ? 'border-teal bg-teal/10 shadow-glow scale-[1.015]'
                        : 'border-navy-border glass hover:border-ink-muted/40'
                    }`}
                  >
                    <input
                      type="radio"
                      name="role"
                      value={r.value}
                      checked={active}
                      onChange={update('role')}
                      className="sr-only"
                    />
                    <span className="flex items-center gap-2">
                      <span className="text-lg">{r.icon}</span>
                      <span className={`font-medium ${active ? 'text-teal' : 'text-ink'}`}>{r.label}</span>
                      {active && <span className="ml-auto text-teal text-xs">✓</span>}
                    </span>
                    <span className="block text-[11px] text-ink-muted mt-1.5 leading-snug">{r.hint}</span>
                  </label>
                )
              })}
            </div>
            <p className="text-[11px] text-ink-muted/80 mt-2.5 leading-relaxed">
              Educators additionally see class-wide analytics. That permission is enforced in
              PostgreSQL (Row Level Security), not just in the UI — and role changes are write-once.
            </p>
          </fieldset>

          <MagneticButton type="submit" className="btn-solid sheen press w-full !py-3.5" strength={6} disabled={busy}>
            {busy ? (
              <>
                <Spinner size={16} className="border-navy/30 border-t-navy" /> Creating account…
              </>
            ) : (
              <>Create account →</>
            )}
          </MagneticButton>
        </form>
      </ScrollReveal>
    </AuthLayout>
  )
}

const ROLES = [
  { value: 'student', label: 'Student', icon: '🎒', hint: 'Scan images, verify claims, see your own history.' },
  { value: 'educator', label: 'Educator', icon: '🎓', hint: 'Everything a student can do, plus class-wide analytics.' },
]

/** Very small password-strength heuristic — UX nudge only, not a policy engine. */
export function passwordStrength(pw) {
  const len = pw.length
  let score = 0
  if (len >= 6) score++
  if (len >= 10) score++
  if (/[A-Z]/.test(pw) && /[a-z]/.test(pw)) score++
  if (/\d/.test(pw)) score++
  if (/[^A-Za-z0-9]/.test(pw)) score++

  if (score <= 1) return { pct: 20, label: 'Weak', color: 'bg-danger' }
  if (score === 2) return { pct: 40, label: 'Fair', color: 'bg-warn' }
  if (score === 3) return { pct: 65, label: 'Good', color: 'bg-teal' }
  if (score === 4) return { pct: 85, label: 'Strong', color: 'bg-safe' }
  return { pct: 100, label: 'Excellent', color: 'bg-safe' }
}
