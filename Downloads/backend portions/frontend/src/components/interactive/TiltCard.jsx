import { useCallback, useRef } from 'react'
import { isCoarsePointer, prefersReducedMotion } from '../../utils/webgl.js'

/**
 * TiltCard — CSS 3D perspective tilt that follows the pointer.
 *
 * HOW THE 3D WORKS:
 *   The wrapper carries `perspective` (the viewer's distance from the z=0 plane)
 *   and the inner element is rotated with `rotateX/rotateY`. Because a child
 *   translated on Z inside a perspective container is scaled by the projection,
 *   `--tz` gives genuine depth: the badge really is floating in front of the card.
 *
 * PERFORMANCE (this is the part most tutorials get wrong):
 *   - `pointermove` fires up to 240×/sec on modern trackpads. We never touch the
 *     DOM inside the handler; we write to a rAF-scheduled frame instead, so at
 *     most one style recalculation happens per displayed frame.
 *   - We only animate `transform` (and a custom property feeding a gradient).
 *     Never `top/left/width/box-shadow-spread` — those trigger layout and paint.
 *   - `transform-style: preserve-3d` + `will-change: transform` promote the card
 *     to its own compositor layer.
 *   - `mouseleave` resets with a CSS transition instead of a snap.
 *
 * ACCESSIBILITY:
 *   Disabled for coarse pointers (no hover on touch) and for reduced-motion
 *   users. The card remains fully usable and readable — tilt is decoration.
 */
export default function TiltCard({
  children,
  className = '',
  max = 9, // degrees of rotation
  depth = 34, // px of Z-translation for the floating layer
  glare = true,
  scale = 1.015,
  perspective = 900,
  as: Tag = 'div',
  ...rest
}) {
  const innerRef = useRef(null)
  const rafRef = useRef(0)

  const enabled = () => !prefersReducedMotion() && !isCoarsePointer()

  const onPointerMove = useCallback(
    (e) => {
      if (!enabled()) return
      const el = innerRef.current
      if (!el) return
      const rect = el.getBoundingClientRect()
      // Normalise to -0.5..0.5 from the card centre.
      const nx = (e.clientX - rect.left) / rect.width - 0.5
      const ny = (e.clientY - rect.top) / rect.height - 0.5

      cancelAnimationFrame(rafRef.current)
      rafRef.current = requestAnimationFrame(() => {
        el.style.transition = 'transform 90ms linear'
        el.style.transform =
          `rotateX(${(-ny * max).toFixed(2)}deg) rotateY(${(nx * max).toFixed(2)}deg) scale3d(${scale},${scale},1)`
        el.style.setProperty('--gx', `${((nx + 0.5) * 100).toFixed(1)}%`)
        el.style.setProperty('--gy', `${((ny + 0.5) * 100).toFixed(1)}%`)
        el.style.setProperty('--glare-o', '1')
      })
    },
    [max, scale],
  )

  const onPointerLeave = useCallback(() => {
    const el = innerRef.current
    if (!el) return
    cancelAnimationFrame(rafRef.current)
    el.style.transition = 'transform 520ms cubic-bezier(0.16, 1, 0.3, 1)'
    el.style.transform = 'rotateX(0deg) rotateY(0deg) scale3d(1,1,1)'
    el.style.setProperty('--glare-o', '0')
  }, [])

  return (
    <Tag
      className={`tilt-wrap ${className}`}
      style={{ perspective: `${perspective}px` }}
      onPointerMove={onPointerMove}
      onPointerLeave={onPointerLeave}
      {...rest}
    >
      <div ref={innerRef} className="tilt-inner" style={{ '--tz': `${depth}px` }}>
        {children}
        {glare && <span className="tilt-glare" aria-hidden="true" />}
      </div>
    </Tag>
  )
}
