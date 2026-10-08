import { useEffect, useRef, useState } from 'react'
import { prefersReducedMotion } from '../../utils/webgl.js'

/**
 * VerdictFlip — a real 3D card flip for the scanner verdict.
 *
 * THE INTERACTION STORY (this is the moment the demo is judged on):
 *   Before the result exists the card sits face-down showing an engraved shield
 *   and "Awaiting analysis". While the model runs it flips onto its edge and
 *   spins (a "computing" state you can *see*). When the verdict arrives it
 *   rotates onto its front face, colour-shifted to match the verdict.
 *
 * CSS 3D MECHANICS:
 *   .flip-viewport  { perspective }                 <- the viewer
 *   .flip-card      { transform-style: preserve-3d } <- keeps children in 3D
 *   .flip-face      { backface-visibility: hidden }  <- hides the reverse side
 *   .flip-face--back{ transform: rotateY(180deg) }   <- pre-rotated so it is
 *                                                       hidden until the parent
 *                                                       rotates 180deg
 *   Without `preserve-3d` the two faces would be flattened into one plane and
 *   you would see the mirrored text of the back face through the front.
 *
 * Reduced motion: the card cross-fades instead of rotating.
 */
export default function VerdictFlip({ state, children, className = '', height = '34rem' }) {
  // state: 'idle' | 'scanning' | 'done'
  const [mounted, setMounted] = useState(false)
  const prev = useRef(state)

  useEffect(() => {
    // Let the initial face paint before transitioning, otherwise the very first
    // render animates from a default transform and looks like a glitch.
    const id = requestAnimationFrame(() => setMounted(true))
    return () => cancelAnimationFrame(id)
  }, [])

  useEffect(() => {
    prev.current = state
  }, [state])

  const reduced = prefersReducedMotion()

  const rotation =
    state === 'done' ? 180 : state === 'scanning' ? 90 : 0

  return (
    <div className={`flip-viewport ${className}`} data-state={state} style={{ '--flip-h': height }}>
      <div
        className={`flip-card ${mounted && !reduced ? 'flip-card--animated' : ''} ${
          reduced ? 'flip-card--reduced' : ''
        }`}
        // `data-spinning` drives the mid-flip rocking keyframes in 3d.css, so the
        // card visibly "computes" on its edge instead of sitting still at 90°.
        data-spinning={state === 'scanning' ? 'true' : 'false'}
        style={{
          transform: reduced
            ? undefined
            : `rotateY(${rotation}deg)${state === 'scanning' ? ' translateZ(24px)' : ''}`,
        }}
        aria-live="polite"
      >
        {/* FRONT (idle) */}
        <div className="flip-face flip-face--front" data-visible={state === 'idle'}>
          <div className="flex flex-col items-center justify-center h-full text-center px-6 py-10">
            <span className="flip-shield" aria-hidden="true">
              <svg viewBox="0 0 64 64" className="w-14 h-14" fill="none">
                <path
                  d="M32 6l20 8v15c0 13.5-8.5 24-20 30C20.5 53 12 42.5 12 29V14z"
                  stroke="currentColor"
                  strokeWidth="2.5"
                  strokeLinejoin="round"
                />
              </svg>
            </span>
            <p className="font-display text-lg mt-4 text-ink">Awaiting analysis</p>
            <p className="text-xs text-ink-muted mt-2 max-w-[15rem] leading-relaxed">
              Your verdict card will flip over when the model returns a result.
            </p>
          </div>
        </div>

        {/* EDGE (scanning) — a thin lit plane, reads as the card mid-rotation */}
        <div className="flip-face flip-face--edge" data-visible={state === 'scanning'}>
          <div className="flex flex-col items-center justify-center h-full gap-4 px-6">
            <div className="scanline" aria-hidden="true" />
            <p className="text-sm text-teal font-medium">Running inference…</p>
            <p className="text-[11px] text-ink-muted text-center max-w-[16rem]">
              Uploading securely, then the vision model classifies the image.
            </p>
          </div>
        </div>

        {/* BACK (result) — pre-rotated 180° so it faces us once the card flips */}
        <div className="flip-face flip-face--back" data-visible={state === 'done'}>
          {children}
        </div>
      </div>
    </div>
  )
}
