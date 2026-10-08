import { useEffect, useRef, useState } from 'react'
import { factCheck } from '../services/api.js'
import { logScan } from '../services/scanLog.js'
import { useAuth } from '../context/AuthContext.jsx'
import { useToast } from '../components/Toast.jsx'
import { useRateLimitCooldown } from '../hooks/useRateLimitCooldown.js'
import TiltCard from '../components/interactive/TiltCard.jsx'
import { ErrorBanner, LoadingDots, PageHeader, SafeLink, Spinner, VerdictBadge } from '../components/ui.jsx'
import { validateClaim, truncate, CLAIM_MIN, CLAIM_MAX } from '../utils/validation.js'

/**
 * ---------------------------------------------------------------------------
 * Fact-Checker (Part A.3) — chat-style claim verification
 * ---------------------------------------------------------------------------
 * SECURITY CHECKLIST FOR THIS PAGE:
 *   C.1 JWT   — api.js attaches the Supabase Bearer token to POST /api/v1/fact-check.
 *   C.2 Valid — claim length 10–1000 enforced before submit; control characters
 *                and zero-width characters are stripped so the value written to
 *                scan_logs can't be used for log injection.
 *   C.3 429   — Verify button locks during the cooldown window.
 *   C.5 XSS   — THE MOST IMPORTANT ONE HERE. The explanation and the source list
 *                come from an LLM + web retrieval: fully untrusted content.
 *                  * explanation -> React text child (auto-escaped)
 *                  * sources     -> rendered through <SafeLink/>, which rejects
 *                                   javascript:/data: URLs and adds
 *                                   target="_blank" rel="noopener noreferrer"
 *                  * dangerouslySetInnerHTML is used NOWHERE in the project.
 *                A prompt-injected model response therefore cannot execute script
 *                in a student's browser. The new 3D styling adds no HTML parsing:
 *                every dynamic string still goes through JSX text interpolation.
 *   C.6 Audit — each verified claim is logged (truncated) to scan_logs.
 *
 * ---------------------------------------------------------------------------
 * HICK'S LAW APPLIED HERE
 * ---------------------------------------------------------------------------
 *  n = 1  One primary action in the composer: "Verify". Enter also submits, but
 *         that is an accelerator for the same single choice, not a second option.
 *  n = 2  Two example chips (down from three). Fewer suggestions means faster
 *         selection, and both are clearly different domains so neither is a
 *         near-duplicate that forces a comparison.
 *  n = 1  Each verdict bubble leads with ONE badge. Sources and retrieved context
 *         are progressive disclosures: sources are a visible list (they are the
 *         pedagogical point), but `retrieved_context` — the noisiest data on the
 *         page — is behind a <details> that is closed by default.
 *  Live   The character counter tells you the ONE thing you need to fix
 *         ("4 more characters needed"), never a list of possible problems.
 */
export default function FactChecker() {
  const { user } = useAuth()
  const toast = useToast()
  const { locked, remainingSeconds } = useRateLimitCooldown()

  const [messages, setMessages] = useState([
    {
      id: 'welcome',
      role: 'assistant',
      kind: 'info',
      text: 'Paste a claim and press Verify. I will retrieve evidence, give you a verdict, and cite the sources so you can check my work.',
    },
  ])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [apiError, setApiError] = useState(null)
  const scrollRef = useRef(null)
  const inputRef = useRef(null)

  // Auto-scroll to the newest message.
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages, busy])

  const chars = input.trim().length
  const tooShort = chars > 0 && chars < CLAIM_MIN
  const tooLong = chars > CLAIM_MAX
  const disabled = busy || locked || chars === 0 || tooLong

  async function handleVerify(e) {
    e?.preventDefault()
    setApiError(null)

    // Part C.2 — validate + sanitise before sending.
    const check = validateClaim(input)
    if (!check.ok) {
      setApiError({ message: check.error })
      return
    }
    const claim = check.value

    const userMsg = { id: `u-${Date.now()}`, role: 'user', kind: 'claim', text: claim }
    setMessages((m) => [...m, userMsg])
    setInput('')
    setBusy(true)

    try {
      const data = await factCheck(claim)
      setMessages((m) => [...m, { id: `a-${Date.now()}`, role: 'assistant', kind: 'verdict', data, claim }])
      toast.success(`Fact-check complete in ${(data?.checked_in_ms ?? 0).toLocaleString()} ms.`)

      // Part B.5 / C.6 — audit trail. We store a truncated claim, never the whole
      // transcript, keeping the log table small and privacy-respecting.
      await logScan({
        contentType: 'text',
        inputSummary: truncate(claim, 180),
        verdict: data?.verdict ?? 'Unverified',
        // The fact-check endpoint has no numeric confidence; derive a display
        // score from the verdict so the dashboard average stays meaningful.
        confidenceScore: verdictToScore(data?.verdict),
        userId: user?.id ?? null,
      })
    } catch (err) {
      setApiError(err)
      setMessages((m) => [
        ...m,
        {
          id: `e-${Date.now()}`,
          role: 'assistant',
          kind: 'error',
          text: err?.message ?? 'Fact-check failed. Please try again.',
        },
      ])
      if (err?.status === 429) toast.warn('Rate limited — please wait before the next claim.')
    } finally {
      setBusy(false)
      inputRef.current?.focus()
    }
  }

  return (
    <div className="max-w-4xl mx-auto px-4 py-8 sm:py-10 flex flex-col">
      <PageHeader
        title="Claim Fact-Checker"
        subtitle="Retrieval-augmented verification with cited sources. Always open the sources — that is the lesson."
      >
        <span className="text-[11px] text-ink-muted border border-navy-border rounded-full px-3 py-1.5 glass">
          {CLAIM_MIN}–{CLAIM_MAX} characters
        </span>
      </PageHeader>

      {apiError && (
        <div className="mb-4">
          <ErrorBanner error={apiError} onDismiss={() => setApiError(null)} />
        </div>
      )}

      {/* ------------------------------ Chat log ------------------------------ */}
      {/* A plain element (not SpotlightCard) because we need a ref for the
          auto-scroll; the glass + edge treatment gives the same look. */}
      <div
        ref={scrollRef}
        className="glass glass-edge flex-1 overflow-y-auto p-4 sm:p-5 space-y-4 min-h-[320px] max-h-[56vh]"
      >
        {messages.map((m) => (
          <Message key={m.id} message={m} />
        ))}

        {busy && (
          <div className="flex justify-start bubble-in">
            <div className="rounded-card rounded-bl-sm bg-navy/80 border border-teal/20 px-4 py-3 max-w-[85%] backdrop-blur-sm">
              <LoadingDots label="Analyzing sources" />
              <div className="mt-3 space-y-2">
                <div className="h-2.5 w-56 rounded bg-navy-border/70 animate-pulse" />
                <div className="h-2.5 w-40 rounded bg-navy-border/50 animate-pulse" />
              </div>
              <div className="scanline mt-3" style={{ width: 120 }} />
            </div>
          </div>
        )}
      </div>

      {/* ------------------------------ Composer ------------------------------ */}
      <form onSubmit={handleVerify} className="mt-4">
        <div className="glass glass-edge p-3 flex flex-col sm:flex-row gap-3">
          <textarea
            ref={inputRef}
            rows={2}
            className="input flex-1 resize-none !bg-navy/60"
            placeholder="e.g. “Voting by mail dramatically increases election fraud.”"
            value={input}
            maxLength={CLAIM_MAX + 100}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              // Enter sends, Shift+Enter inserts a newline (chat-app convention).
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                if (!disabled) handleVerify(e)
              }
            }}
            disabled={busy}
            aria-label="Claim to fact-check"
          />
          <button type="submit" className="btn-solid press sheen sm:self-end !py-3.5" disabled={disabled}>
            {busy ? (
              <>
                <Spinner size={16} className="border-navy/30 border-t-navy" /> Checking
              </>
            ) : locked ? (
              <>Wait {remainingSeconds}s…</>
            ) : (
              <>✔ Verify</>
            )}
          </button>
        </div>

        <div className="flex flex-wrap items-center justify-between gap-2 mt-2 px-1">
          {/* ONE message: the single next thing the user must know. */}
          <p
            className={`text-xs ${tooLong ? 'text-danger' : tooShort ? 'text-warn' : 'text-ink-muted'}`}
            aria-live="polite"
          >
            {tooLong
              ? `Too long — trim ${chars - CLAIM_MAX} character${chars - CLAIM_MAX === 1 ? '' : 's'}.`
              : tooShort
                ? `${CLAIM_MIN - chars} more character${CLAIM_MIN - chars === 1 ? '' : 's'} needed.`
                : locked
                  ? `Rate-limit cooldown: ${remainingSeconds}s remaining.`
                  : `${chars}/${CLAIM_MAX} · Enter to send`}
          </p>

          {/* n = 2 suggestions. Both distinct domains, so no comparison cost. */}
          <div className="flex gap-2">
            {EXAMPLES.map((ex) => (
              <button
                key={ex}
                type="button"
                onClick={() => setInput(ex)}
                disabled={busy}
                className="press text-[11px] text-ink-muted border border-navy-border rounded-full px-2.5 py-1 hover:text-teal hover:border-teal/40 transition disabled:opacity-40 bg-navy/50"
              >
                {truncate(ex, 30)}
              </button>
            ))}
          </div>
        </div>
      </form>
    </div>
  )
}

/* ------------------------------- messages ------------------------------- */

function Message({ message }) {
  if (message.role === 'user') {
    return (
      <div className="flex justify-end bubble-in">
        <div className="rounded-card rounded-br-sm bg-teal/10 border border-teal/25 px-4 py-3 max-w-[85%] backdrop-blur-sm">
          <p className="text-[10px] uppercase tracking-wider text-teal/80 mb-1">Your claim</p>
          {/* Untrusted-ish (user's own) text -> escaped by React automatically. */}
          <p className="text-ink whitespace-pre-wrap break-words">{message.text}</p>
        </div>
      </div>
    )
  }

  if (message.kind === 'info') {
    return (
      <div className="flex justify-start">
        <div className="rounded-card rounded-bl-sm bg-navy/70 border border-navy-border px-4 py-3 max-w-[85%]">
          <p className="text-sm text-ink-muted">{message.text}</p>
        </div>
      </div>
    )
  }

  if (message.kind === 'error') {
    return (
      <div className="flex justify-start bubble-in">
        <div className="rounded-card rounded-bl-sm bg-danger/10 border border-danger/40 px-4 py-3 max-w-[85%]">
          <p className="text-xs text-danger font-semibold mb-1">Verification failed</p>
          <p className="text-sm text-ink/90">{message.text}</p>
        </div>
      </div>
    )
  }

  // kind === 'verdict' — gets the full 3D tilt treatment: it is the payload.
  const { data } = message
  const sources = Array.isArray(data?.sources) ? data.sources.filter(Boolean) : []
  const context = Array.isArray(data?.retrieved_context) ? data.retrieved_context : []

  return (
    <div className="flex justify-start bubble-in">
      <TiltCard max={5} depth={18} glare={false} className="max-w-[92%] w-full sm:w-auto">
        <div className="rounded-card rounded-bl-sm glass glass-edge px-4 py-4 tilt-inner">
          {/* ONE badge = one thing to read first. */}
          <div className="flex flex-wrap items-center gap-3">
            <span className="tilt-float" style={{ '--tz': '14px' }}>
              <VerdictBadge verdict={data?.verdict ?? 'Unverified'} />
            </span>
            {typeof data?.checked_in_ms === 'number' && (
              <span className="text-[11px] text-ink-muted font-mono">
                {(data.checked_in_ms / 1000).toFixed(2)}s
              </span>
            )}
          </div>

          {/* SECURITY (C.5): AI-generated prose rendered as an escaped text node. */}
          {data?.explanation && (
            <p className="text-sm text-ink/90 mt-3 leading-relaxed whitespace-pre-wrap break-words">
              {data.explanation}
            </p>
          )}

          {sources.length > 0 && (
            <div className="mt-4 pt-3 border-t border-navy-border">
              <p className="text-[10px] uppercase tracking-wider text-ink-muted mb-2">
                Sources ({sources.length}) — open at least one
              </p>
              <ul className="space-y-1.5">
                {sources.map((src, i) => (
                  <li key={`${src}-${i}`} className="text-sm flex gap-2 group">
                    <span className="text-teal/60 font-mono text-xs mt-0.5">{i + 1}.</span>
                    {/* SECURITY (C.5): SafeLink allow-lists http/https and applies
                        rel="noopener noreferrer" to prevent tab-nabbing. */}
                    <SafeLink href={src} className="group-hover:text-ink transition" />
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Progressive disclosure: the noisiest data on the page is hidden
              behind a closed <details>, so it never competes with the verdict. */}
          {context.length > 0 && (
            <details className="group mt-3">
              <summary className="text-[11px] text-ink-muted cursor-pointer hover:text-teal transition list-none flex items-center gap-2">
                <span className="text-teal transition-transform duration-200 group-open:rotate-90">›</span>
                Retrieved context ({context.length} passages)
              </summary>
              <ul className="mt-2 space-y-2">
                {context.slice(0, 5).map((ctx, i) => (
                  <li
                    key={i}
                    className="text-xs text-ink-muted bg-navy/60 border border-navy-border rounded p-2.5"
                  >
                    {/* context entries may be strings or objects -> stringify safely */}
                    {typeof ctx === 'string' ? truncate(ctx, 320) : truncate(JSON.stringify(ctx), 320)}
                  </li>
                ))}
              </ul>
            </details>
          )}
        </div>
      </TiltCard>
    </div>
  )
}

/**
 * Map a categorical verdict to a 0–100 "risk/confidence" number so the
 * educator dashboard's average-confidence stat still works for text checks.
 * (The fact-check endpoint does not return a numeric confidence.)
 */
function verdictToScore(verdict) {
  const v = String(verdict ?? '').toLowerCase()
  if (v === 'false') return 92
  if (v.includes('mostly false') || v.includes('misleading')) return 78
  if (v === 'true') return 90
  if (v.includes('mostly true')) return 80
  if (v.includes('mixed') || v.includes('partly')) return 60
  return 45 // unverified / unknown
}

const EXAMPLES = [
  'Vaccines cause autism according to a 1998 study',
  'The Eiffel Tower was built in 1889 for the World Fair',
]
