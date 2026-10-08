import { Link } from 'react-router-dom'

/** 404 — generic, discloses nothing about the route table. */
export default function NotFound() {
  return (
    <div className="max-w-xl mx-auto px-4 py-24 text-center">
      <p className="font-mono text-sm text-teal">404</p>
      <h1 className="font-display text-3xl font-semibold mt-2">Page not found</h1>
      <p className="text-sm text-ink-muted mt-3">
        That route does not exist in TruthGuard AI.
      </p>
      <div className="flex gap-3 justify-center mt-7">
        <Link to="/" className="btn-primary press">
          Back to home
        </Link>
        <Link to="/scanner" className="btn-ghost press">
          Image Scanner
        </Link>
      </div>
    </div>
  )
}
