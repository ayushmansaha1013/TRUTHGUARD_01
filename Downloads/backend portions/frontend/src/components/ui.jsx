/**
 * Small presentational primitives shared across pages.
 *
 * SECURITY (Part C.5 — XSS prevention), applies to this whole file:
 *   Every dynamic value below is rendered as a React text child or inside a
 *   quoted JSX attribute. React escapes both, so AI-generated strings
 *   (verdicts, explanations, filenames, source titles) can never be interpreted
 *   as HTML. `dangerouslySetInnerHTML` is used NOWHERE in this project
 *   (verified by the grep in README -> Security Audit).
 *   The single escaping blind spot — `href` — is handled by <SafeLink/>, which
 *   allow-lists http/https and refuses `javascript:` / `data:` URLs.
 */

export function Spinner({ size = 20, className = '' }) {
  return (
    <span
      className={`inline-block rounded-full border-2 border-teal/25 border-t-teal animate-spin ${className}`}
      style={{ width: size, height: size }}
      aria-hidden="true"
    />
  )
}

export function LoadingDots({ label = 'Analyzing sources' }) {
  return (
    <span className="inline-flex items-center gap-2 text-ink-muted">
      <Spinner size={16} />
      <span>{label}</span>
      <span className="inline-flex gap-1">
        <span className="dot-1 animate-blink">•</span>
        <span className="dot-2 animate-blink">•</span>
        <span className="dot-3 animate-blink">•</span>
      </span>
    </span>
  )
}

const TONES = {
  fake: 'bg-danger/15 text-danger border-danger/40',
  real: 'bg-safe/15 text-safe border-safe/40',
  uncertain: 'bg-warn/15 text-warn border-warn/40',
  neutral: 'bg-teal/10 text-teal border-teal/30',
}

/**
 * Verdict badge. Tone is derived from the verdict STRING returned by the model,
 * so the mapping lives in one place and works for both features:
 *   "Likely Fake" / "False"      -> red
 *   "Likely Real" / "True"       -> green
 *   "Uncertain" / "Unverified"   -> yellow
 */
export function VerdictBadge({ verdict, size = 'md' }) {
  const tone = toneFor(verdict)
  const sizing = size === 'lg' ? 'text-base px-4 py-2' : 'text-xs px-2.5 py-1'
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border font-semibold uppercase tracking-wide ${sizing} ${TONES[tone]}`}
    >
      <span className="w-1.5 h-1.5 rounded-full bg-current" />
      {verdict || 'Unknown'}
    </span>
  )
}

export function toneFor(verdict) {
  const v = String(verdict ?? '').toLowerCase()
  if (v.includes('fake') || v === 'false' || v.includes('debunked') || v.includes('misleading')) return 'fake'
  if (v.includes('real') || v === 'true' || v.includes('genuine') || v.includes('authentic')) return 'real'
  if (v.includes('uncertain') || v.includes('unverified') || v.includes('mixed') || v.includes('unknown'))
    return 'uncertain'
  return 'neutral'
}

export function barColorFor(verdict) {
  const tone = toneFor(verdict)
  return tone === 'fake' ? 'bg-danger' : tone === 'real' ? 'bg-safe' : tone === 'uncertain' ? 'bg-warn' : 'bg-teal'
}

/**
 * Confidence gauge: an accessible progress bar + numeric readout.
 * `confidence` is a 0–100 number from the backend; we clamp it so a malformed
 * response can never blow out the layout.
 */
export function ConfidenceGauge({ confidence, verdict, label = 'Model confidence' }) {
  const pct = Math.max(0, Math.min(100, Number(confidence) || 0))
  return (
    <div>
      <div className="flex items-baseline justify-between mb-2">
        <span className="text-sm text-ink-muted">{label}</span>
        <span className="font-display text-2xl font-semibold text-ink tabular-nums">{pct.toFixed(1)}%</span>
      </div>
      <div
        className="h-3 w-full rounded-full bg-navy border border-navy-border overflow-hidden"
        role="progressbar"
        aria-valuenow={Number(pct.toFixed(1))}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={label}
      >
        <div
          className={`h-full rounded-full transition-all duration-700 ease-out ${barColorFor(verdict)}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <div className="flex justify-between text-[10px] text-ink-muted/70 mt-1">
        <span>0%</span>
        <span>50%</span>
        <span>100%</span>
      </div>
    </div>
  )
}

export function ErrorBanner({ error, onDismiss }) {
  if (!error) return null
  const status = error?.status ? `HTTP ${error.status}` : 'Error'
  return (
    <div
      className="rounded-card border border-danger/40 bg-danger/10 px-4 py-3 text-sm animate-fade-up"
      role="alert"
    >
      <div className="flex items-start gap-3">
        <span className="text-danger font-bold mt-0.5">⚠</span>
        <div className="flex-1">
          <p className="text-danger font-medium">{status}</p>
          <p className="text-ink/90 mt-0.5">{error?.message ?? String(error)}</p>
          {error?.status === 429 && (
            <p className="text-ink-muted text-xs mt-1">
              The service is protecting itself from overload. The button stays locked for a few seconds.
            </p>
          )}
        </div>
        {onDismiss && (
          <button type="button" onClick={onDismiss} className="text-ink-muted hover:text-ink transition" aria-label="Dismiss">
            ✕
          </button>
        )}
      </div>
    </div>
  )
}

/**
 * SafeLink — the ONLY way this app renders an external anchor.
 *
 * SECURITY (Part C.5): AI-returned source URLs are untrusted input. React's
 * escaping does not protect against `href="javascript:alert(document.cookie)"`
 * because that is a *valid* URL, not markup. So we:
 *   1. allow-list the protocol (http/https only) — anything else renders as inert text;
 *   2. add target="_blank" + rel="noopener noreferrer", which prevents
 *      tab-nabbing (the opened page getting a reference to `window.opener` and
 *      redirecting our tab) and stops Referer leakage to third parties.
 */
export function SafeLink({ href, children, className = '' }) {
  const url = normaliseUrl(href)
  if (!url) {
    // Not a safe URL -> show the raw string as escaped text, never clickable.
    return <span className="text-ink-muted break-all">{String(href)}</span>
  }
  return (
    <a
      href={url}
      target="_blank"
      rel="noopener noreferrer nofollow"
      className={`text-teal hover:underline break-all ${className}`}
    >
      {children ?? prettyUrl(url)}
    </a>
  )
}

function normaliseUrl(raw) {
  try {
    const u = new URL(String(raw ?? '').trim())
    if (u.protocol !== 'http:' && u.protocol !== 'https:') return null
    return u.toString()
  } catch {
    return null
  }
}

export function prettyUrl(raw) {
  try {
    const u = new URL(String(raw))
    return u.hostname.replace(/^www\./, '') + (u.pathname !== '/' ? u.pathname : '')
  } catch {
    return String(raw)
  }
}

/**
 * StatCard — dashboard metric tile.
 * `bare` strips the card chrome so it can be nested inside <SpotlightCard>
 * (which supplies the glass surface and the pointer-tracking light) without
 * doubling up borders and backgrounds.
 */
export function StatCard({ label, value, sub, accent = 'teal', icon, bare = false }) {
  const accentText = accent === 'danger' ? 'text-danger' : accent === 'warn' ? 'text-warn' : 'text-teal'
  return (
    <div className={bare ? 'p-5 h-full' : 'card p-5 hover:border-teal/30 transition duration-200'}>
      <div className="flex items-start justify-between gap-3">
        <p className="text-xs uppercase tracking-wider text-ink-muted">{label}</p>
        {icon && <span className={`text-lg ${accentText}`}>{icon}</span>}
      </div>
      <p className={`font-display text-3xl font-semibold mt-2 tabular-nums ${accentText}`}>{value}</p>
      {sub && <p className="text-xs text-ink-muted mt-1">{sub}</p>}
    </div>
  )
}

export function EmptyState({ title, hint, icon = '🔍' }) {
  return (
    <div className="glass p-10 text-center">
      <div className="text-3xl mb-3">{icon}</div>
      <p className="text-ink font-medium">{title}</p>
      {hint && <p className="text-sm text-ink-muted mt-1">{hint}</p>}
    </div>
  )
}

export function PageHeader({ title, subtitle, children }) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-4 mb-6">
      <div>
        <h1 className="font-display text-2xl sm:text-3xl font-semibold text-ink">{title}</h1>
        {subtitle && <p className="text-ink-muted text-sm mt-1 max-w-2xl">{subtitle}</p>}
      </div>
      {children}
    </div>
  )
}

export function KeyHint({ children }) {
  return (
    <kbd className="px-1.5 py-0.5 rounded border border-navy-border bg-navy text-ink-muted text-[11px] font-mono">
      {children}
    </kbd>
  )
}
