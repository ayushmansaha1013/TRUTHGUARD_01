import { Spinner } from './ui.jsx'

/** Shown while Supabase restores the session on page load. */
export default function FullPageLoader({ label = 'Loading…' }) {
  return (
    <div className="min-h-screen grid place-items-center px-4">
      <div className="text-center">
        <div className="mx-auto w-16 h-16 grid place-items-center rounded-card border border-teal/30 bg-teal/10 mb-4">
          <Spinner size={28} />
        </div>
        <p className="font-display text-lg text-ink">TruthGuard AI</p>
        <p className="text-sm text-ink-muted mt-1">{label}</p>
      </div>
    </div>
  )
}
