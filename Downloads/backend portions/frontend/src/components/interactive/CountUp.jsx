import { useEffect, useRef, useState } from 'react'
import { prefersReducedMotion } from '../../utils/webgl.js'

/**
 * CountUp — animates a number from its previous value to the new one.
 *
 * Uses requestAnimationFrame with an ease-out cubic and, critically, animates
 * FROM the previously rendered value (not always from 0), so switching the
 * dashboard range from 7 → 30 days tweens instead of restarting.
 *
 * Reduced motion: jump straight to the final value.
 * Formatting is delegated to `Intl.NumberFormat` so locale digit grouping is
 * correct rather than hand-rolled.
 */
export default function CountUp({
  value,
  decimals = 0,
  duration = 900,
  prefix = '',
  suffix = '',
  className = '',
}) {
  const target = Number.isFinite(Number(value)) ? Number(value) : 0
  const [display, setDisplay] = useState(() => (prefersReducedMotion() ? target : 0))
  const fromRef = useRef(prefersReducedMotion() ? target : 0)
  const rafRef = useRef(0)

  useEffect(() => {
    if (prefersReducedMotion()) {
      fromRef.current = target
      setDisplay(target)
      return undefined
    }

    const from = fromRef.current
    const delta = target - from
    if (Math.abs(delta) < 1e-6) {
      setDisplay(target)
      return undefined
    }

    const start = performance.now()
    const fmt = new Intl.NumberFormat(undefined, {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals,
    })

    const tick = (now) => {
      const p = Math.min(1, (now - start) / duration)
      const eased = 1 - Math.pow(1 - p, 3) // ease-out cubic
      const current = from + delta * eased
      setDisplay(current)
      // Store as a formatted string only at the end to keep the final value exact.
      if (p < 1) {
        rafRef.current = requestAnimationFrame(tick)
      } else {
        fromRef.current = target
        setDisplay(target)
      }
      // `fmt` is used by the render below via decimals; keep reference honest:
      void fmt
    }
    rafRef.current = requestAnimationFrame(tick)

    return () => cancelAnimationFrame(rafRef.current)
  }, [target, duration, decimals])

  const formatted = new Intl.NumberFormat(undefined, {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(display)

  return (
    <span className={`tabular-nums ${className}`}>
      {prefix}
      {formatted}
      {suffix}
    </span>
  )
}
