import { useEffect, useRef, useState } from 'react'
import { prefersReducedMotion } from '../../utils/webgl.js'

/**
 * ConfidenceRing — 3D-looking SVG gauge for the model confidence score.
 *
 * Depth cues, in order of how much they contribute:
 *   1. A dark "track" ring plus a brighter stroke on top  -> the arc reads as a
 *      physical groove with a filled portion.
 *   2. `filter: drop-shadow` in the verdict colour        -> light spill onto the
 *      card, which is what makes it feel lit rather than drawn.
 *   3. A conic sheen behind the ring that rotates slowly  -> suggests a curved,
 *      reflective surface.
 *   4. The number counts up in sync with the arc          -> motion ties the two
 *      together so the eye reads them as one object.
 *
 * The arc is animated with stroke-dashoffset (a compositor-friendly property on
 * SVG in modern browsers) and disabled under reduced motion.
 *
 * ACCESSIBILITY: role="progressbar" with aria-valuenow, plus the numeric value
 * rendered as real text — never colour alone.
 */
export default function ConfidenceRing({
  value,
  verdict,
  size = 180,
  stroke = 12,
  label = 'Model confidence',
  animate = true,
}) {
  const pct = Math.max(0, Math.min(100, Number(value) || 0))
  const reduced = prefersReducedMotion()
  const [shown, setShown] = useState(reduced || !animate ? pct : 0)
  const prev = useRef(0)

  useEffect(() => {
    if (reduced || !animate) {
      prev.current = pct
      setShown(pct)
      return undefined
    }
    const from = prev.current
    const start = performance.now()
    const duration = 1100
    let raf = 0
    const tick = (now) => {
      const p = Math.min(1, (now - start) / duration)
      const eased = 1 - Math.pow(1 - p, 4) // ease-out quartic: fast start, soft land
      setShown(from + (pct - from) * eased)
      if (p < 1) raf = requestAnimationFrame(tick)
      else prev.current = pct
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [pct, animate, reduced])

  const r = (size - stroke) / 2
  const c = 2 * Math.PI * r
  const offset = c * (1 - shown / 100)
  const color = colorFor(verdict)

  return (
    <div
      className="confidence-ring"
      style={{ width: size, height: size, '--ring-color': color }}
      role="progressbar"
      aria-valuenow={Number(pct.toFixed(1))}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label={label}
    >
      <span className="confidence-ring__sheen" aria-hidden="true" />
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="confidence-ring__svg">
        <defs>
          <linearGradient id={`ring-grad-${size}`} x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor={color} stopOpacity="1" />
            <stop offset="100%" stopColor={color} stopOpacity="0.45" />
          </linearGradient>
        </defs>

        {/* groove */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke="#0A192F"
          strokeWidth={stroke}
          opacity="0.95"
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke="#233554"
          strokeWidth={stroke - 4}
          opacity="0.8"
        />

        {/* filled arc — rotated -90deg so it starts at 12 o'clock */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={`url(#ring-grad-${size})`}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={c}
          strokeDashoffset={offset}
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
          className="confidence-ring__arc"
        />
      </svg>

      <div className="confidence-ring__center">
        <span className="confidence-ring__value tabular-nums">{shown.toFixed(1)}</span>
        <span className="confidence-ring__unit">%</span>
        <span className="confidence-ring__label">{label}</span>
      </div>
    </div>
  )
}

function colorFor(verdict) {
  const v = String(verdict ?? '').toLowerCase()
  if (v.includes('fake') || v === 'false' || v.includes('misleading')) return '#FF4D4D'
  if (v.includes('real') || v === 'true' || v.includes('genuine')) return '#4ADE80'
  if (v.includes('uncertain') || v.includes('unverified') || v.includes('mixed')) return '#FFD166'
  return '#64FFDA'
}
