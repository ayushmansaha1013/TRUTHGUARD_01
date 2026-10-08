import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getHealth } from '../services/api.js'
import { useAuth } from '../context/AuthContext.jsx'
import Hero3D from '../components/three/Hero3D.jsx'
import TiltCard from '../components/interactive/TiltCard.jsx'
import SpotlightCard from '../components/interactive/SpotlightCard.jsx'
import ScrollReveal from '../components/interactive/ScrollReveal.jsx'
import MagneticButton from '../components/interactive/MagneticButton.jsx'

/**
 * Landing page.
 *
 * ---------------------------------------------------------------------------
 * HICK'S LAW APPLIED HERE  (response time grows with log₂(n) options)
 * ---------------------------------------------------------------------------
 *  n = 2  Above the fold there is exactly ONE primary action and ONE secondary.
 *         The old design offered 3 equal-weight buttons to a signed-out visitor;
 *         now the signed-out state offers "Create free account" (solid, magnetic,
 *         sheened) + "Sign in" (ghost). Fewer, clearer, faster to choose.
 *  n = 3  Features are three cards, never more — and each card names the exact
 *         endpoint, so there is no ambiguity about which one to click.
 *  n = 3  The security section is a numbered 1-2-3 sequence (order implies a path)
 *         rather than three interchangeable tiles.
 *  n = 1  The health pill is a single glanceable status, not a status table.
 * Every choice on this page is either a single primary action or a set of ≤3
 * visually-ranked options — that is the whole rule, and it is applied on every
 * other screen too (see docs/HICKS_LAW.md).
 */
export default function Landing() {
  const { isAuthenticated, isEducator } = useAuth()
  const [health, setHealth] = useState({ state: 'checking' })

  useEffect(() => {
    let alive = true
    getHealth()
      .then((data) => alive && setHealth({ state: 'ok', data }))
      .catch((err) => alive && setHealth({ state: 'error', message: err?.message }))
    return () => {
      alive = false
    }
  }, [])

  return (
    <div className="max-w-6xl mx-auto px-4">
      {/* ================================ HERO ================================ */}
      <section className="pt-10 pb-12 sm:pt-16">
        <div className="grid lg:grid-cols-2 gap-8 items-center min-h-[70vh]">
          {/* ---- copy column ---- */}
          <div>
            <ScrollReveal>
              <span className="inline-flex items-center gap-2 text-[11px] uppercase tracking-[0.18em] text-teal border border-teal/30 bg-teal/10 rounded-full px-3.5 py-1.5 backdrop-blur-sm">
                <span className="relative flex h-1.5 w-1.5">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-teal opacity-70" />
                  <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-teal" />
                </span>
                Civic education · UN SDG 4 &amp; SDG 16
              </span>
            </ScrollReveal>

            <ScrollReveal delay={80}>
              <h1 className="font-display text-[2.6rem] leading-[1.06] sm:text-6xl lg:text-[4.1rem] font-bold mt-6">
                Spot the <span className="text-gradient">fake.</span>
                <br />
                Verify the claim.
              </h1>
            </ScrollReveal>

            <ScrollReveal delay={150}>
              <p className="text-ink-muted text-base sm:text-lg mt-5 max-w-xl leading-relaxed">
                TruthGuard AI is a deepfake and misinformation detection platform built for
                classrooms. Upload an image to test whether it was generated or manipulated, or
                fact-check a claim against retrieved evidence — then teach the media-literacy
                lesson behind the result.
              </p>
            </ScrollReveal>

            {/* Hick's Law: ONE primary action. Everything else is visually secondary. */}
            <ScrollReveal delay={220}>
              <div className="flex flex-wrap items-center gap-3 mt-8">
                {isAuthenticated ? (
                  <>
                    <MagneticButton className="btn-solid sheen press !px-7 !py-3.5" as={Link} to="/scanner">
                      Open Image Scanner →
                    </MagneticButton>
                    <Link to="/fact-checker" className="btn-ghost press">
                      Fact Checker
                    </Link>
                    {isEducator && (
                      <Link to="/dashboard" className="nav-link">
                        Dashboard
                      </Link>
                    )}
                  </>
                ) : (
                  <>
                    <MagneticButton className="btn-solid sheen press !px-7 !py-3.5" as={Link} to="/signup">
                      Create free account
                    </MagneticButton>
                    <Link to="/login" className="btn-ghost press">
                      I already have one
                    </Link>
                  </>
                )}
              </div>
            </ScrollReveal>

            <ScrollReveal delay={290}>
              <HealthPill health={health} />
            </ScrollReveal>
          </div>

          {/* ---- 3D column ---- */}
          <ScrollReveal delay={120} scale={0.96} y={0}>
            <div className="relative h-[380px] sm:h-[460px] lg:h-[540px]">
              <Hero3D className="absolute inset-0" />
              {/* Floating glass stat chips — translateZ depth over the WebGL scene */}
              <FloatingChip className="left-0 top-[16%]" delay="0s">
                <span className="text-danger">●</span> Likely Fake
                <span className="text-ink-muted font-mono">94.2%</span>
              </FloatingChip>
              <FloatingChip className="right-0 top-[46%]" delay="1.4s">
                <span className="text-safe">●</span> Claim verified
                <span className="text-ink-muted font-mono">3 sources</span>
              </FloatingChip>
              <FloatingChip className="left-[6%] bottom-[12%]" delay="2.6s">
                <span className="text-teal">●</span> JWT secured
                <span className="text-ink-muted font-mono">RLS on</span>
              </FloatingChip>
            </div>
          </ScrollReveal>
        </div>
      </section>

      {/* ============================== FEATURES ============================== */}
      <section className="pb-16">
        <ScrollReveal>
          <SectionHeading
            eyebrow="Three tools"
            title="Everything a media-literacy lesson needs"
            subtitle="Pick one — each card is a single, unambiguous entry point."
          />
        </ScrollReveal>

        <div className="grid md:grid-cols-3 gap-4 mt-8">
          {FEATURES.map((f, i) => (
            <ScrollReveal key={f.title} delay={i * 90} y={26}>
              <TiltCard max={7} depth={26} className="h-full">
                <SpotlightCard className="glass glass-edge h-full p-6 flex flex-col">
                  <div className="tilt-float">
                    <div className="w-12 h-12 grid place-items-center rounded-xl bg-teal/10 border border-teal/25 text-2xl shadow-glow">
                      {f.icon}
                    </div>
                  </div>
                  <h3 className="font-display text-lg font-semibold mt-5">{f.title}</h3>
                  <p className="text-sm text-ink-muted mt-2 leading-relaxed flex-1">{f.body}</p>
                  <div className="mt-5 flex items-center justify-between gap-2">
                    <code className="text-[10px] font-mono text-teal/75 truncate">{f.tag}</code>
                    <Link
                      to={f.to}
                      className="text-xs text-teal hover:text-ink transition whitespace-nowrap press"
                    >
                      Open →
                    </Link>
                  </div>
                </SpotlightCard>
              </TiltCard>
            </ScrollReveal>
          ))}
        </div>
      </section>

      {/* ============================== SECURITY ============================== */}
      <section className="pb-16">
        <ScrollReveal>
          <SectionHeading
            eyebrow="Security engineering"
            title="Access control at three independent layers"
            subtitle="Numbered, because they are layers — not alternatives. Each one fails safely on its own."
          />
        </ScrollReveal>

        <div className="grid md:grid-cols-3 gap-4 mt-8">
          {LAYERS.map((l, i) => (
            <ScrollReveal key={l.title} delay={i * 100} y={24}>
              <SpotlightCard className="glass p-5 h-full relative overflow-hidden">
                <span className="absolute -right-3 -top-6 font-display text-[5.5rem] font-bold text-teal/[0.07] select-none leading-none">
                  {i + 1}
                </span>
                <p className="text-[11px] font-mono text-teal tracking-widest relative">LAYER {i + 1}</p>
                <p className="font-display font-semibold mt-2 relative">{l.title}</p>
                <p className="text-xs text-ink-muted mt-2 leading-relaxed relative">{l.body}</p>
                <p className="text-[10px] font-mono text-ink-muted/60 mt-4 relative">{l.where}</p>
              </SpotlightCard>
            </ScrollReveal>
          ))}
        </div>
      </section>

      {/* ================================ CTA ================================= */}
      <ScrollReveal y={26}>
        <section className="pb-20">
          <div className="glass glass-edge p-8 sm:p-12 text-center relative overflow-hidden">
            <div className="absolute inset-0 bg-[radial-gradient(600px_circle_at_50%_0%,rgba(100,255,218,0.12),transparent_65%)] pointer-events-none" />
            <h2 className="font-display text-2xl sm:text-4xl font-semibold relative">
              Ready to teach the <span className="text-gradient">difference</span>?
            </h2>
            <p className="text-sm text-ink-muted mt-3 max-w-lg mx-auto relative">
              Two accounts, one SQL script, and a live detector. Free for students and educators.
            </p>
            <div className="mt-7 flex flex-wrap justify-center gap-3 relative">
              {isAuthenticated ? (
                <MagneticButton className="btn-solid sheen press !px-7" as={Link} to="/scanner">
                  Start scanning →
                </MagneticButton>
              ) : (
                <MagneticButton className="btn-solid sheen press !px-7" as={Link} to="/signup">
                  Create free account
                </MagneticButton>
              )}
            </div>
          </div>
        </section>
      </ScrollReveal>
    </div>
  )
}

/* --------------------------------- pieces --------------------------------- */

function HealthPill({ health }) {
  const tone =
    health.state === 'ok' ? 'bg-safe' : health.state === 'error' ? 'bg-danger' : 'bg-warn animate-pulse'
  const text =
    health.state === 'checking'
      ? 'Checking AI backend health…'
      : health.state === 'ok'
        ? 'AI backend online — detection & fact-check ready'
        : `AI backend unreachable — ${health.message ?? 'check VITE_API_BASE_URL'}`

  return (
    <div className="mt-8 inline-flex items-center gap-3 glass px-4 py-3 text-xs sm:text-sm max-w-full">
      <span className={`w-2.5 h-2.5 rounded-full shrink-0 shadow-[0_0_10px_currentColor] ${tone}`} />
      <span className="text-ink-muted truncate">{text}</span>
    </div>
  )
}

function FloatingChip({ children, className = '', delay = '0s' }) {
  return (
    <div
      className={`absolute glass px-3.5 py-2.5 text-[11px] flex items-center gap-2 whitespace-nowrap chip-float ${className}`}
      style={{ animationDelay: delay }}
    >
      {children}
    </div>
  )
}

function SectionHeading({ eyebrow, title, subtitle }) {
  return (
    <div className="max-w-2xl">
      <p className="text-[11px] font-mono uppercase tracking-[0.2em] text-teal">{eyebrow}</p>
      <h2 className="font-display text-2xl sm:text-3xl font-semibold mt-2">{title}</h2>
      {subtitle && <p className="text-sm text-ink-muted mt-2">{subtitle}</p>}
    </div>
  )
}

const FEATURES = [
  {
    icon: '🖼️',
    title: 'Deepfake Image Scanner',
    body: 'Drag and drop a photo. A fine-tuned vision model returns a verdict plus a calibrated confidence score, typically in 2–5 seconds.',
    tag: 'POST /api/v1/detect-image',
    to: '/scanner',
  },
  {
    icon: '💬',
    title: 'Claim Fact-Checker',
    body: 'Paste a claim into a chat-style interface. The system retrieves supporting context, explains its reasoning, and cites its sources.',
    tag: 'POST /api/v1/fact-check',
    to: '/fact-checker',
  },
  {
    icon: '🎓',
    title: 'Educator Analytics',
    body: 'Weekly scan volume, deepfakes detected, average confidence and a flagged-content table — the raw material for a classroom debrief.',
    tag: 'role = educator',
    to: '/dashboard',
  },
]

const LAYERS = [
  {
    title: 'React route guards',
    body: 'ProtectedRoute and EducatorRoute keep unauthenticated users and students out of educator screens.',
    where: 'components/ProtectedRoute.jsx · EducatorRoute.jsx',
  },
  {
    title: 'Supabase Row Level Security',
    body: 'Postgres itself filters rows: students read only their own logs, educators read all, nobody can rewrite history.',
    where: 'supabase/schema.sql · 6 policies · append-only audit',
  },
  {
    title: 'FastAPI JWT middleware',
    body: 'The AI backend rejects any request without a valid Supabase Bearer token, and can require a role claim.',
    where: 'backend_security/jwt_auth.py · 23/23 checks pass',
  },
]
