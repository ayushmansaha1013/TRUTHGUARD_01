import { useCallback, useEffect, useMemo, useState } from 'react'
import { fetchEducatorStats, isFlagged } from '../services/scanLog.js'
import { useAuth } from '../context/AuthContext.jsx'
import { useToast } from '../components/Toast.jsx'
import CountUp from '../components/interactive/CountUp.jsx'
import SpotlightCard from '../components/interactive/SpotlightCard.jsx'
import ScrollReveal from '../components/interactive/ScrollReveal.jsx'
import MagneticButton from '../components/interactive/MagneticButton.jsx'
import { ErrorBanner, PageHeader, Spinner, StatCard, VerdictBadge, EmptyState } from '../components/ui.jsx'

/**
 * ---------------------------------------------------------------------------
 * Educator Dashboard (Part A.4) — EDUCATOR ROLE ONLY
 * ---------------------------------------------------------------------------
 * This component is only ever mounted inside <EducatorRoute>, but note the
 * important detail: even if a student somehow rendered it (e.g. by editing the
 * React tree in DevTools), the data query below would return ZERO rows, because
 * the Supabase RLS policy `educators_select_all_scan_logs` requires
 * profiles.role = 'educator' for any SELECT that isn't `user_id = auth.uid()`,
 * and fetchEducatorStats() additionally re-checks the role before querying.
 *
 *   RBAC layer 1 (this route guard) = UX
 *   RBAC layer 2 (RLS on the query) = the actual security control
 *   RBAC layer 3 (backend JWT role claim) = protects the AI compute itself
 *
 * ---------------------------------------------------------------------------
 * HICK'S LAW APPLIED HERE — the densest screen in the app, so it matters most
 * ---------------------------------------------------------------------------
 * The header used to offer 5 competing controls (7d / 30d / Refresh / Generate
 * Quiz, plus the table's own implicit "everything"). Now:
 *
 *  n = 1  ONE primary action: "Generate Quiz" (solid, magnetic). Refresh is a
 *         quiet icon button — same affordance, far lower visual weight, so it
 *         does not compete.
 *  n = 2  ONE binary choice: This week / 30 days, as a segmented control. Two
 *         options is the theoretical minimum for a range choice (log₂2 = 1 bit).
 *  n = 1  The table shows ONE thing at a time. Instead of adding filter buttons
 *         (which would raise n), the four stat cards ARE the filters: click
 *         "Deepfakes detected" and the table narrows to flagged rows. Direct
 *         manipulation replaces a menu — the number of visible controls stays the
 *         same while capability goes up.
 *  n = 1  Raw submissions live behind a closed <details>, so the flagged table
 *         (the thing an educator actually needs) is the only default view.
 *
 * Every filter has a single obvious way to clear it (the active chip, or "All").
 */
export default function EducatorDashboard() {
  const { user, role } = useAuth()
  const toast = useToast()

  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [range, setRange] = useState(7)
  const [filter, setFilter] = useState('flagged') // 'flagged' | 'images' | 'text' | 'all'

  const load = useCallback(async (days) => {
    setLoading(true)
    setError(null)
    try {
      const data = await fetchEducatorStats({ days, limit: 25 })
      setStats(data)
    } catch (err) {
      // A student hitting this query gets 0 rows (not an error). An actual error
      // almost always means the SQL script hasn't been run in Supabase yet.
      setError({
        status: 0,
        message:
          err?.message?.includes('does not exist') || err?.code === '42P01'
            ? 'Database objects are missing. Run supabase/schema.sql in the Supabase SQL Editor (see README step 3).'
            : err?.message ?? 'Could not load analytics.',
      })
      setStats(null)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load(range)
  }, [load, range])

  // "Generate Quiz" is an intentional stub for this milestone (Part A.4).
  function handleGenerateQuiz() {
    toast.info('Quiz generation coming soon — media-literacy questions built from your class scans.')
  }

  const t = stats?.totals

  /** The table's contents are derived from the active stat-card filter. */
  const rows = useMemo(() => {
    const all = stats?.rows ?? []
    switch (filter) {
      case 'images':
        return all.filter((r) => r.content_type === 'image')
      case 'text':
        return all.filter((r) => r.content_type === 'text')
      case 'all':
        return all
      case 'flagged':
      default:
        return all.filter(isFlagged)
    }
  }, [stats, filter])

  const visible = rows.slice(0, 25)

  const FILTERS = [
    { id: 'flagged', label: 'Deepfakes / false claims', count: t?.deepfakesDetected ?? 0 },
    { id: 'images', label: 'Image scans', count: t?.imageScans ?? 0 },
    { id: 'text', label: 'Claim checks', count: t?.textChecks ?? 0 },
    { id: 'all', label: 'All submissions', count: t?.totalScans ?? 0 },
  ]

  return (
    <div className="max-w-6xl mx-auto px-4 py-8 sm:py-10">
      <PageHeader
        title="Educator Dashboard"
        subtitle={`Class-wide media-literacy analytics for the last ${range} days. Signed in as ${user?.email ?? '—'} (${role}).`}
      >
        <div className="flex flex-wrap items-center gap-2">
          {/* n = 2 segmented control */}
          <div
            className="flex rounded-lg border border-navy-border overflow-hidden glass"
            role="group"
            aria-label="Date range"
          >
            {[7, 30].map((d) => (
              <button
                key={d}
                type="button"
                onClick={() => setRange(d)}
                aria-pressed={range === d}
                className={`press px-3.5 py-2 text-xs transition ${
                  range === d ? 'bg-teal/15 text-teal' : 'text-ink-muted hover:text-ink'
                }`}
              >
                {d === 7 ? 'This week' : '30 days'}
              </button>
            ))}
          </div>

          {/* Refresh = quiet icon button so it does not compete with the primary */}
          <button
            type="button"
            onClick={() => load(range)}
            disabled={loading}
            title="Refresh analytics"
            aria-label="Refresh analytics"
            className="press w-10 h-10 grid place-items-center rounded-lg border border-navy-border glass text-ink-muted hover:text-teal hover:border-teal/40 transition disabled:opacity-50"
          >
            {loading ? <Spinner size={15} /> : '↻'}
          </button>

          {/* n = 1 primary action */}
          <MagneticButton className="btn-primary press text-sm" strength={7} onClick={handleGenerateQuiz}>
            ✨ Generate Quiz
          </MagneticButton>
        </div>
      </PageHeader>

      {error && (
        <div className="mb-5">
          <ErrorBanner error={error} onDismiss={() => setError(null)} />
        </div>
      )}

      {/* ------------------- Stat cards = filters (direct manipulation) ------- */}
      <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {loading && !stats
          ? Array.from({ length: 4 }).map((_, i) => <SkeletonCard key={i} />)
          : [
              {
                key: 'all',
                label: `Total scans (${range === 7 ? 'this week' : '30 days'})`,
                value: t?.totalScans ?? 0,
                decimals: 0,
                sub: `${t?.imageScans ?? 0} images · ${t?.textChecks ?? 0} claims`,
                icon: '📊',
                accent: 'teal',
              },
              {
                key: 'flagged',
                label: 'Deepfakes / false claims',
                value: t?.deepfakesDetected ?? 0,
                decimals: 0,
                sub: t?.totalScans
                  ? `${Math.round((t.deepfakesDetected / t.totalScans) * 100)}% of submissions flagged`
                  : 'No submissions yet',
                icon: '🚨',
                accent: 'danger',
              },
              {
                key: 'confidence',
                label: 'Average confidence',
                value: t?.avgConfidence ?? 0,
                decimals: 1,
                suffix: '%',
                sub: 'Mean model confidence across all submissions',
                icon: '🎯',
                accent: 'warn',
              },
              {
                key: 'users',
                label: 'Active users',
                value: t?.uniqueUsers ?? 0,
                decimals: 0,
                sub: 'Distinct accounts that submitted content',
                icon: '👥',
                accent: 'teal',
              },
            ].map((card, i) => {
              const clickable = card.key === 'all' || card.key === 'flagged'
              const active = filter === card.key
              return (
                <ScrollReveal key={card.key} delay={i * 70} y={18}>
                  <SpotlightCard
                    className={`h-full transition duration-200 ${
                      clickable ? 'cursor-pointer' : ''
                    } ${active ? 'ring-2 ring-teal/50' : ''}`}
                    onClick={clickable ? () => setFilter(card.key) : undefined}
                    role={clickable ? 'button' : undefined}
                    tabIndex={clickable ? 0 : undefined}
                    aria-pressed={clickable ? active : undefined}
                    onKeyDown={
                      clickable
                        ? (e) => {
                            if (e.key === 'Enter' || e.key === ' ') {
                              e.preventDefault()
                              setFilter(card.key)
                            }
                          }
                        : undefined
                    }
                  >
                    <StatCard
                      label={card.label}
                      value={<CountUp value={card.value} decimals={card.decimals} suffix={card.suffix ?? ''} />}
                      sub={card.sub}
                      accent={card.accent}
                      icon={card.icon}
                      bare
                    />
                  </SpotlightCard>
                </ScrollReveal>
              )
            })}
      </div>

      {/* ------------------------ Table + its filter chips --------------------- */}
      <section className="glass glass-edge mt-6 overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-3 px-5 py-4 border-b border-navy-border">
          <div>
            <h2 className="font-display text-lg font-semibold">
              {filter === 'flagged'
                ? 'Recent flagged content'
                : filter === 'images'
                  ? 'Image scans'
                  : filter === 'text'
                    ? 'Claim checks'
                    : 'All submissions'}
            </h2>
            <p className="text-xs text-ink-muted mt-0.5">
              Every row is an entry in the immutable{' '}
              <code className="font-mono text-teal/80">scan_logs</code> audit trail.
            </p>
          </div>

          {/* Filter chips: the current selection is always visible and clearable
              in one click, so the table never feels mysteriously short. */}
          <div className="flex flex-wrap gap-1.5">
            {FILTERS.map((f) => (
              <button
                key={f.id}
                type="button"
                onClick={() => setFilter(f.id)}
                aria-pressed={filter === f.id}
                className={`press text-[11px] rounded-full px-3 py-1.5 border transition ${
                  filter === f.id
                    ? 'border-teal/50 bg-teal/15 text-teal'
                    : 'border-navy-border text-ink-muted hover:text-ink hover:border-ink-muted/40'
                }`}
              >
                {f.label}
                <span className="ml-1.5 font-mono opacity-70">{f.count}</span>
              </button>
            ))}
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-[10px] uppercase tracking-wider text-ink-muted border-b border-navy-border bg-navy/40">
                <th className="px-5 py-3 font-medium">Timestamp</th>
                <th className="px-5 py-3 font-medium">Type</th>
                <th className="px-5 py-3 font-medium">Input summary</th>
                <th className="px-5 py-3 font-medium">Verdict</th>
                <th className="px-5 py-3 font-medium">Risk score</th>
                <th className="px-5 py-3 font-medium">Submitted by</th>
              </tr>
            </thead>
            <tbody>
              {loading && !stats && (
                <tr>
                  <td colSpan={6} className="px-5 py-12 text-center text-ink-muted">
                    <Spinner size={20} className="mx-auto mb-3" />
                    Loading analytics…
                  </td>
                </tr>
              )}

              {!loading && visible.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-5 py-10">
                    <EmptyState
                      icon="🗂️"
                      title={
                        filter === 'flagged'
                          ? 'Nothing flagged in this period'
                          : 'No submissions in this view'
                      }
                      hint="Once students scan images or check claims, submissions appear here automatically."
                    />
                  </td>
                </tr>
              )}

              {visible.map((row, i) => (
                <tr
                  key={row.id}
                  className="border-b border-navy-border/60 hover:bg-teal/[0.04] transition-colors duration-150 bubble-in"
                  style={{ animationDelay: `${Math.min(i * 28, 420)}ms` }}
                >
                  <td className="px-5 py-3 whitespace-nowrap text-ink-muted font-mono text-xs">
                    {formatTimestamp(row.timestamp)}
                  </td>
                  <td className="px-5 py-3">
                    <span className="text-xs px-2 py-1 rounded border border-navy-border text-ink-muted bg-navy/50">
                      {row.content_type === 'image' ? '🖼️ Image' : '💬 Text'}
                    </span>
                  </td>
                  <td className="px-5 py-3 max-w-[280px] truncate text-ink" title={row.input_summary}>
                    {/* SECURITY (C.5): user-supplied summary rendered as escaped text. */}
                    {row.input_summary ?? '—'}
                  </td>
                  <td className="px-5 py-3">
                    <VerdictBadge verdict={row.verdict} />
                  </td>
                  <td className="px-5 py-3">
                    <RiskBar score={row.confidence_score} flagged={isFlagged(row)} />
                  </td>
                  <td className="px-5 py-3 text-ink-muted text-xs">
                    {row.user_email ? maskEmail(row.user_email) : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {!loading && (stats?.rows?.length ?? 0) > 0 && (
          <div className="px-5 py-3 text-[11px] text-ink-muted/80 border-t border-navy-border flex flex-wrap gap-x-2 justify-between">
            <span>
              Showing {visible.length} of {rows.length} in this view · {stats.rows.length} total in range
            </span>
            <span>Emails are masked in the UI; full addresses remain in the audit table.</span>
          </div>
        )}
      </section>

      {/* -------------------------- Teaching prompt -------------------------- */}
      <ScrollReveal y={20}>
        <section className="glass p-5 mt-6">
          <h3 className="font-display font-semibold">Classroom debrief prompt</h3>
          <p className="text-sm text-ink-muted mt-2 leading-relaxed">
            Ask students why a model can be{' '}
            {t?.avgConfidence ? `${t.avgConfidence.toFixed(0)}%` : 'highly'} confident and still be
            wrong. Then have them open two cited sources from the Fact Checker and compare the framing.
            Detection tools are a starting point for critical thinking, not a replacement for it.
          </p>
        </section>
      </ScrollReveal>
    </div>
  )
}

/* --------------------------------- helpers -------------------------------- */

function SkeletonCard() {
  return (
    <div className="glass p-5 animate-pulse">
      <div className="h-3 w-24 rounded bg-navy-border/70" />
      <div className="h-8 w-16 rounded bg-navy-border/70 mt-3" />
      <div className="h-2.5 w-32 rounded bg-navy-border/50 mt-3" />
    </div>
  )
}

/** Risk score = model confidence, coloured by whether the content was flagged. */
function RiskBar({ score, flagged }) {
  const value = typeof score === 'number' ? Math.max(0, Math.min(100, score)) : null
  if (value === null) return <span className="text-xs text-ink-muted">n/a</span>
  return (
    <div className="flex items-center gap-2 min-w-[120px]">
      <div className="flex-1 h-2 rounded-full bg-navy border border-navy-border overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-700 ease-out ${
            flagged ? 'bg-danger shadow-[0_0_10px_rgba(255,77,77,0.6)]' : 'bg-teal'
          }`}
          style={{ width: `${value}%` }}
        />
      </div>
      <span className={`text-xs tabular-nums ${flagged ? 'text-danger' : 'text-ink-muted'}`}>
        {value.toFixed(0)}
      </span>
    </div>
  )
}

function formatTimestamp(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return String(iso)
  return d.toLocaleString(undefined, {
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  })
}

/**
 * Partial email masking.
 * WHY: the dashboard is frequently projected onto a classroom screen. Showing
 * full student emails leaks personal data to the whole room — a data-minimisation
 * control (GDPR-style), and a nice point for the security section of the report.
 */
function maskEmail(email) {
  const [name, domain] = String(email).split('@')
  if (!domain) return email
  const visible = name.slice(0, 2)
  return `${visible}${'•'.repeat(Math.max(1, name.length - 2))}@${domain}`
}
