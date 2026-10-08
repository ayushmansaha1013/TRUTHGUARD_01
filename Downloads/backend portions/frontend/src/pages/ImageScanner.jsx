import { useEffect, useRef, useState } from 'react'
import { detectImage } from '../services/api.js'
import { logScan } from '../services/scanLog.js'
import { useAuth } from '../context/AuthContext.jsx'
import { useToast } from '../components/Toast.jsx'
import { useRateLimitCooldown } from '../hooks/useRateLimitCooldown.js'
import FileDropzone from '../components/FileDropzone.jsx'
import VerdictFlip from '../components/interactive/VerdictFlip.jsx'
import Hero3D from '../components/three/Hero3D.jsx'
import ConfidenceRing from '../components/interactive/ConfidenceRing.jsx'
import SpotlightCard from '../components/interactive/SpotlightCard.jsx'
import ScrollReveal from '../components/interactive/ScrollReveal.jsx'
import { ErrorBanner, PageHeader, Spinner, VerdictBadge } from '../components/ui.jsx'
import { validateImageFile } from '../utils/validation.js'

/**
 * ---------------------------------------------------------------------------
 * Image Scanner (Part A.2) — 3D interactive build
 * ---------------------------------------------------------------------------
 * Flow: pick file -> client-side validation -> POST /api/v1/detect-image with
 *       the Supabase JWT -> the verdict card FLIPS over to reveal the result ->
 *       an audit row is written to Supabase `scan_logs`.
 *
 * SECURITY CHECKLIST FOR THIS PAGE (unchanged by the visual work):
 *   C.1 JWT   — api.js attaches `Authorization: Bearer <supabase jwt>` automatically.
 *   C.2 Valid — MIME + 8 MB enforced before upload (validateImageFile).
 *   C.3 429   — submit button locks for the cooldown window after a rate limit.
 *   C.5 XSS   — filename/verdict rendered as escaped text; no dangerouslySetInnerHTML;
 *                the preview is a blob: URL, never injected markup.
 *   C.6 Audit — every successful detection is logged with user_id + timestamp.
 *
 * ---------------------------------------------------------------------------
 * HICK'S LAW APPLIED HERE
 * ---------------------------------------------------------------------------
 *  n = 1  There is exactly ONE action button while a file is selected. "New scan"
 *         was moved *inside* the result card, where it is only offered once a
 *         result exists — it never competes with "Analyse image".
 *  n = 1  The result leads with a single verdict + one ring gauge. The four raw
 *         model fields (raw_label, fake_probability, is_fake, ms) are collapsed
 *         behind a <details> disclosure, so the first read is one number, not five.
 *  n ≤ 5  The session strip shows at most five recent chips and is read-only —
 *         feedback, not a menu.
 *  State  The button label is the only thing that changes (Analyse / Analysing…
 *         Ns / Please wait Ns), so the user never has to re-read it.
 */
export default function ImageScanner() {
  const { user } = useAuth()
  const toast = useToast()
  const { locked, remainingSeconds } = useRateLimitCooldown()

  const [file, setFile] = useState(null)
  const [validationError, setValidationError] = useState(null)
  const [result, setResult] = useState(null)
  const [apiError, setApiError] = useState(null)
  const [busy, setBusy] = useState(false)
  const [elapsed, setElapsed] = useState(0)
  const [history, setHistory] = useState([])

  // Drives the "threat pulse" in the WebGL hero when a fake is found.
  const [pulse, setPulse] = useState(0)

  const timerRef = useRef(null)
  useEffect(() => {
    if (!busy) return undefined
    setElapsed(0)
    timerRef.current = setInterval(() => setElapsed((s) => s + 1), 1000)
    return () => clearInterval(timerRef.current)
  }, [busy])

  useEffect(() => {
    if (file && validationError) setValidationError(null)
  }, [file, validationError])

  const disabled = busy || locked
  const flipState = busy ? 'scanning' : result ? 'done' : 'idle'

  async function handleAnalyse() {
    setApiError(null)
    setResult(null)

    // Part C.2 — validate again at submit time (defence in depth: the file could
    // have been swapped via DevTools between selection and submission).
    const check = validateImageFile(file)
    if (!check.ok) {
      setValidationError(check.error)
      return
    }

    setBusy(true)
    try {
      const data = await detectImage(file)
      setResult(data)
      toast.success(`Analysis complete in ${(data?.analyzed_in_ms ?? 0).toLocaleString()} ms.`)

      // A "fake" verdict pulses the hero scene red — feedback you feel, not just read.
      if (data?.is_fake) setPulse((p) => p + 1)

      setHistory((h) =>
        [{ id: Date.now(), verdict: data?.verdict, confidence: data?.confidence }, ...h].slice(0, 5),
      )

      // Part B.5 / C.6 — audit trail + dashboard analytics.
      // Failure here must never destroy a good result, so logScan swallows errors.
      await logScan({
        contentType: 'image',
        inputSummary: file.name, // filename only: we do NOT store the image bytes
        verdict: data?.verdict ?? 'Unknown',
        confidenceScore: typeof data?.confidence === 'number' ? data.confidence : null,
        userId: user?.id ?? null,
      })
    } catch (err) {
      setApiError(err)
      if (err?.status === 429) {
        toast.warn('Rate limited — the button is locked for a few seconds to protect the service.')
      } else {
        toast.error(err?.message ?? 'Detection failed.')
      }
    } finally {
      setBusy(false)
    }
  }

  function reset() {
    setResult(null)
    setFile(null)
    setApiError(null)
    setValidationError(null)
  }

  return (
    <div className="max-w-6xl mx-auto px-4 py-8 sm:py-10">
      <PageHeader
        title="Deepfake Image Scanner"
        subtitle="Upload a photo and the vision model estimates whether it is authentic or AI-generated / manipulated."
      />

      <div className="grid lg:grid-cols-5 gap-5">
        {/* ------------------------- Left: input ------------------------- */}
        <section className="lg:col-span-3 space-y-4">
          <ScrollReveal y={18}>
            <SpotlightCard className="glass glass-edge p-5">
              <FileDropzone file={file} onFileChange={setFile} onError={setValidationError} disabled={busy} />

              {validationError && (
                <div className="mt-3">
                  <ErrorBanner error={{ message: validationError }} onDismiss={() => setValidationError(null)} />
                </div>
              )}

              {/* ONE primary action. Its label is the only thing that changes. */}
              <div className="mt-4 flex flex-wrap items-center gap-3">
                <button
                  type="button"
                  className="btn-solid press sheen flex-1 sm:flex-none sm:min-w-[240px] !py-3.5"
                  onClick={handleAnalyse}
                  disabled={disabled || !file}
                >
                  {busy ? (
                    <>
                      <Spinner size={16} className="border-navy/30 border-t-navy" />
                      Analysing… {elapsed}s
                    </>
                  ) : locked ? (
                    <>Please wait {remainingSeconds}s…</>
                  ) : (
                    <>🔍 Analyse image</>
                  )}
                </button>

                {!file && !busy && (
                  <span className="text-xs text-ink-muted">Choose an image to enable analysis.</span>
                )}
              </div>

              {locked && (
                <p className="text-xs text-warn mt-3">
                  Cooldown active after a rate-limit response. This protects the shared GPU service
                  from request spam.
                </p>
              )}
            </SpotlightCard>
          </ScrollReveal>

          {apiError && <ErrorBanner error={apiError} onDismiss={() => setApiError(null)} />}

          {/* Session history: read-only feedback strip, max 5 chips. */}
          {history.length > 0 && (
            <ScrollReveal y={14}>
              <div className="glass p-4">
                <div className="flex items-center justify-between gap-3 mb-3">
                  <p className="text-[11px] uppercase tracking-wider text-ink-muted">This session</p>
                  <p className="text-[11px] text-ink-muted/70">
                    {history.length} of max 5 shown · also written to your audit log
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  {history.map((h, i) => (
                    <span
                      key={h.id}
                      className="inline-flex items-center gap-2 text-[11px] rounded-full border border-navy-border bg-navy/70 px-3 py-1.5 bubble-in"
                      style={{ animationDelay: `${i * 45}ms` }}
                    >
                      <VerdictBadge verdict={h.verdict} />
                      <span className="font-mono text-ink-muted tabular-nums">
                        {typeof h.confidence === 'number' ? `${h.confidence.toFixed(1)}%` : '—'}
                      </span>
                    </span>
                  ))}
                </div>
              </div>
            </ScrollReveal>
          )}
        </section>

        {/* ------------------- Right: the 3D verdict card ------------------- */}
        <section className="lg:col-span-2">
          <div className="lg:sticky lg:top-24 relative">
            {/* A compact WebGL orb sits behind the verdict card. When the model
                flags a deepfake it pulses red — the same scene code as the hero,
                so `three` is already in the lazy chunk (no second download).
                Falls back to the CSS 3D stage on touch / reduced-motion / no GPU. */}
            <div
              className="absolute -inset-6 -z-10 opacity-70 pointer-events-none select-none"
              aria-hidden="true"
            >
              <Hero3D pulse={pulse} />
            </div>

            <VerdictFlip state={flipState} height="36rem">
              {/* ---- BACK FACE: the revealed result ---- */}
              <div className="h-full flex flex-col p-6 overflow-y-auto">
                <div className="flex items-start justify-between gap-3">
                  <VerdictBadge verdict={result?.verdict} size="lg" />
                  {typeof result?.analyzed_in_ms === 'number' && (
                    <span className="text-[11px] text-ink-muted font-mono shrink-0">
                      {(result.analyzed_in_ms / 1000).toFixed(2)}s
                    </span>
                  )}
                </div>

                {/* Single focal number — Hick's Law: one thing to read first. */}
                <div className="my-6 grid place-items-center">
                  <ConfidenceRing value={result?.confidence} verdict={result?.verdict} size={188} />
                </div>

                {/* Raw model output, collapsed: available, not competing. */}
                <details className="group rounded-lg border border-navy-border bg-navy/60 px-4 py-3">
                  <summary className="cursor-pointer text-xs text-ink-muted hover:text-teal transition list-none flex items-center justify-between gap-2">
                    <span>Raw model output</span>
                    <span className="text-teal transition-transform duration-200 group-open:rotate-90">›</span>
                  </summary>
                  <dl className="text-sm space-y-2 mt-3 pt-3 border-t border-navy-border">
                    <Row label="Raw label" value={result?.raw_label ?? '—'} mono />
                    <Row
                      label="Fake probability"
                      value={
                        typeof result?.fake_probability === 'number'
                          ? result.fake_probability.toFixed(3)
                          : '—'
                      }
                      mono
                    />
                    <Row label="Flagged as fake" value={result?.is_fake ? 'Yes' : 'No'} />
                    <Row label="Inference time" value={`${result?.analyzed_in_ms ?? '—'} ms`} mono />
                  </dl>
                </details>

                <p className="text-[11px] text-ink-muted/80 leading-relaxed mt-4">
                  A probabilistic estimate from a single model, not a definitive judgement. Logged to
                  your audit trail for classroom review.
                </p>

                {/* Reset lives HERE, not in the header: it only exists once there
                    is something to reset, so it never competes with "Analyse". */}
                <button type="button" className="btn-ghost press w-full mt-4 text-sm" onClick={reset}>
                  ↺ Scan another image
                </button>
              </div>
            </VerdictFlip>
          </div>
        </section>
      </div>
    </div>
  )
}

function Row({ label, value, mono }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <dt className="text-ink-muted">{label}</dt>
      <dd className={`text-ink truncate ${mono ? 'font-mono text-xs' : ''}`}>{value}</dd>
    </div>
  )
}
