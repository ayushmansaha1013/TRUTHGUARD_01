import { useRef } from 'react'

/**
 * SpotlightCard — a border/light that tracks the pointer around the card edge.
 *
 * This is the "Linear/Vercel" look: a soft radial highlight follows the cursor
 * across a glass panel. Implemented with a single CSS custom property pair
 * (--mx/--my) driving a radial-gradient overlay, so the effect costs one paint
 * of a pseudo-element and zero layout.
 *
 * Uses pointer coordinates relative to the CARD, which is what makes a grid of
 * these feel like one continuous light source moving between panels.
 */
export default function SpotlightCard({ children, className = '', radius = 320, ...rest }) {
  const ref = useRef(null)
  const raf = useRef(0)

  function onPointerMove(e) {
    const el = ref.current
    if (!el) return
    const rect = el.getBoundingClientRect()
    const x = e.clientX - rect.left
    const y = e.clientY - rect.top
    cancelAnimationFrame(raf.current)
    raf.current = requestAnimationFrame(() => {
      el.style.setProperty('--mx', `${x}px`)
      el.style.setProperty('--my', `${y}px`)
      el.style.setProperty('--spot-o', '1')
    })
  }

  function onPointerLeave() {
    const el = ref.current
    if (!el) return
    cancelAnimationFrame(raf.current)
    el.style.setProperty('--spot-o', '0')
  }

  return (
    <div
      ref={ref}
      className={`spotlight ${className}`}
      style={{ '--spot-r': `${radius}px` }}
      onPointerMove={onPointerMove}
      onPointerLeave={onPointerLeave}
      {...rest}
    >
      {children}
    </div>
  )
}
