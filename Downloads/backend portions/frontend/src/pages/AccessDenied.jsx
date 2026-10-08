import { Link, useLocation } from 'react-router-dom'
import { useAuth } from '../context/AuthContext.jsx'

/**
 * 403 Access Denied (Part B.4).
 * Shown when a signed-in STUDENT tries to open /dashboard.
 *
 * SECURITY: this page reveals only the minimum — that the requested area needs an
 * educator role. It does not echo query strings, does not display other users'
 * data, and does not hint at what the dashboard contains beyond a generic
 * description. Information disclosure on error pages is a real (if minor) leak.
 */
export default function AccessDenied() {
  const { user, role } = useAuth()
  const location = useLocation()
  const tried = location.state?.tried ?? 'this area'

  return (
    <div className="max-w-xl mx-auto px-4 py-20 text-center">
      <div className="glass glass-edge p-10 animate-fade-up shadow-glow">
        <div className="mx-auto w-16 h-16 grid place-items-center rounded-full border border-danger/40 bg-danger/10 text-3xl">
          🔒
        </div>
        <p className="mt-6 font-mono text-sm text-danger">403 · ACCESS DENIED</p>
        <h1 className="font-display text-2xl font-semibold mt-2">Educator role required</h1>
        <p className="text-sm text-ink-muted mt-3 leading-relaxed">
          <span className="text-ink">{tried}</span> is restricted to accounts with the{' '}
          <span className="text-teal">educator</span> role, because it aggregates submissions from the
          whole class.
        </p>
        <p className="text-xs text-ink-muted/80 mt-3">
          Signed in as <span className="text-ink">{user?.email ?? 'unknown'}</span> · role:{' '}
          <span className="text-ink">{role ?? 'none'}</span>
        </p>

        <div className="flex flex-wrap gap-3 justify-center mt-7">
          <Link to="/scanner" className="btn-primary press">
            Go to Image Scanner
          </Link>
          <Link to="/fact-checker" className="btn-ghost press">
            Fact Checker
          </Link>
        </div>

        <p className="text-[11px] text-ink-muted/70 mt-6 leading-relaxed">
          This restriction is enforced at three layers: the React route guard you just hit, PostgreSQL
          Row Level Security on <code className="font-mono">scan_logs</code>, and the backend JWT role
          check. Bypassing this page would still return zero rows.
        </p>
      </div>
    </div>
  )
}
