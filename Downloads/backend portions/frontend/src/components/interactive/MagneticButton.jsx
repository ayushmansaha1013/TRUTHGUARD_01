import { useCallback, useRef } from 'react'
import { isCoarsePointer, prefersReducedMotion } from '../../utils/webgl.js'

/**
 * MagneticButton — the button drifts slightly toward the cursor as you approach.
 *
 * WHY IT FEELS "EXPENSIVE": the element responds to you before you commit to the
 * click, which reads as a physical object rather than a painted rectangle.
 *
 * CONSTRAINTS RESPECTED:
 *  - Translation is capped (`strength` px) so the button can never move out from
 *    under the cursor — that would be actively hostile, and would break Fitts's
 *    Law rather than exploit it.
 *  - The label counter-translates at half the rate, creating a subtle parallax
 *    inside the button (real depth cue, ~2 lines of CSS).
 *  - Disabled for touch and reduced-motion users.
 *  - Only `transform` is animated; no layout thrash.
 */
export default function MagneticButton({
  children,
  className = '',
  strength = 12,
  as: Tag = 'button',
  type = 'button',
  disabled = false,
  ...rest
}) {
  const ref = useRef(null)
  const labelRef = useRef(null)
  const raf = useRef(0)

  const reset = useCallback(() => {
    cancelAnimationFrame(raf.current)
    const el = ref.current
    if (el) {
      el.style.transition = 'transform 480ms cubic-bezier(0.16, 1, 0.3, 1)'
      el.style.transform = 'translate3d(0,0,0)'
    }
    if (labelRef.current) {
      labelRef.current.style.transition = 'transform 480ms cubic-bezier(0.16, 1, 0.3, 1)'
      labelRef.current.style.transform = 'translate3d(0,0,0)'
    }
  }, [])

  const onPointerMove = useCallback(
    (e) => {
      // A disabled control must not move: drifting a dead button toward the
      // cursor implies it is clickable, which is worse than no effect at all.
      if (disabled || prefersReducedMotion() || isCoarsePointer()) return
      const el = ref.current
      if (!el) return
      const r = el.getBoundingClientRect()
      const nx = (e.clientX - (r.left + r.width / 2)) / (r.width / 2)
      const ny = (e.clientY - (r.top + r.height / 2)) / (r.height / 2)

      cancelAnimationFrame(raf.current)
      raf.current = requestAnimationFrame(() => {
        el.style.transition = 'transform 120ms linear'
        el.style.transform = `translate3d(${(nx * strength).toFixed(2)}px, ${(ny * strength * 0.6).toFixed(2)}px, 0)`
        if (labelRef.current) {
          labelRef.current.style.transition = 'transform 120ms linear'
          labelRef.current.style.transform = `translate3d(${(nx * strength * 0.45).toFixed(2)}px, ${(
            ny *
            strength *
            0.3
          ).toFixed(2)}px, 0)`
        }
      })
    },
    [strength],
  )

  return (
    <Tag
      ref={ref}
      type={Tag === 'button' ? type : undefined}
      className={`magnetic ${className}`}
      disabled={Tag === 'button' ? disabled : undefined}
      aria-disabled={Tag !== 'button' && disabled ? true : undefined}
      onPointerMove={onPointerMove}
      onPointerLeave={reset}
      onBlur={reset}
      {...rest}
    >
      <span ref={labelRef} className="magnetic-label">
        {children}
      </span>
    </Tag>
  )
}
