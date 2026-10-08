import { Link } from 'react-router-dom'

/** Shared two-column shell for /login and /signup. */
export default function AuthLayout({ title, subtitle, children, footer }) {
  return (
    <div className="min-h-screen grid lg:grid-cols-2">
      {/* Left: brand / value proposition */}
      <div className="hidden lg:flex flex-col justify-between p-12 border-r border-navy-border bg-navy-card/30 backdrop-blur-xl relative overflow-hidden">
        {/* Decorative depth field. pointer-events:none so it can never block a click. */}
        <div
          className="absolute -left-24 top-1/3 w-[26rem] h-[26rem] rounded-full pointer-events-none"
          style={{ background: 'radial-gradient(circle, rgba(100,255,218,0.14), transparent 65%)', filter: 'blur(60px)' }}
          aria-hidden="true"
        />
        <Link to="/" className="flex items-center gap-2 group w-fit">
          <span className="w-9 h-9 grid place-items-center rounded-lg border border-teal/30 bg-teal/10 text-teal font-bold text-lg group-hover:bg-teal/20 transition">
            T
          </span>
          <span className="font-display font-semibold text-lg">
            Truth<span className="text-teal">Guard</span> AI
          </span>
        </Link>

        <div className="max-w-md">
          <h2 className="font-display text-3xl font-semibold leading-snug">
            Media literacy is a <span className="text-teal">security skill</span>.
          </h2>
          <p className="text-ink-muted mt-4 leading-relaxed">
            Synthetic media is now cheap to produce and expensive to detect. TruthGuard AI gives
            students a working detector and gives educators the analytics to teach the lesson behind
            every verdict.
          </p>
          <ul className="mt-6 space-y-3 text-sm">
            {[
              'Deepfake image detection with calibrated confidence',
              'Claim verification with cited, clickable sources',
              'Role-based dashboards for classroom debriefs',
            ].map((item) => (
              <li key={item} className="flex gap-3 text-ink-muted">
                <span className="text-teal mt-0.5">✓</span>
                <span>{item}</span>
              </li>
            ))}
          </ul>
        </div>

        <p className="text-xs text-ink-muted/70">
          Aligned with UN Sustainable Development Goal 4 (Quality Education) and Goal 16 (Peace,
          Justice and Strong Institutions).
        </p>
      </div>

      {/* Right: the form */}
      <div className="flex items-center justify-center p-6 sm:p-12">
        <div className="w-full max-w-md animate-fade-up relative">
          <Link to="/" className="lg:hidden flex items-center gap-2 mb-8 w-fit">
            <span className="w-8 h-8 grid place-items-center rounded-lg border border-teal/30 bg-teal/10 text-teal font-bold">
              T
            </span>
            <span className="font-display font-semibold">
              Truth<span className="text-teal">Guard</span> AI
            </span>
          </Link>

          <div className="glass glass-edge p-6 sm:p-8 shadow-glow">
            <h1 className="font-display text-2xl font-semibold">{title}</h1>
            {subtitle && <p className="text-sm text-ink-muted mt-1 mb-6">{subtitle}</p>}
            {children}
          </div>

          {footer && <div className="mt-6">{footer}</div>}
        </div>
      </div>
    </div>
  )
}
