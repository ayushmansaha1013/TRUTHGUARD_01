import { useEffect, useRef } from 'react'

/**
 * ScrollProgress — a 2px teal bar at the top of the viewport showing reading
 * progress through the page.
 *
 * WHY (interaction design): it is a continuous, peripheral progress cue. On a
 * long landing page it tells the visitor how much is left without them having to
 * look at the scrollbar — and on a projector it reads clearly from the back of a
 * room.
 *
 * PERFORMANCE: the scroll handler writes only `transform: scaleX()` on a single
 * element, inside a rAF, with `transform-origin: left` and `will-change`. No
 * layout, no paint of the page, one composited layer. A naive implementation
 * that sets `width: %` would re-layout the entire document on every scroll event.
 */
export default function ScrollProgress() {
  const ref = useRef(null)
  const raf = useRef(0)

  useEffect(() => {
    const update = () => {
      raf.current = 0
      const el = ref.current
      if (!el) return
      const doc = document.documentElement
      const max = doc.scrollHeight - doc.clientHeight
      const p = max > 0 ? Math.min(1, Math.max(0, doc.scrollTop / max)) : 0
      el.style.transform = `scaleX(${p})`
      el.style.opacity = p > 0.002 && p < 0.999 ? '1' : '0'
    }
    const onScroll = () => {
      if (!raf.current) raf.current = requestAnimationFrame(update)
    }

    update()
    window.addEventListener('scroll', onScroll, { passive: true })
    window.addEventListener('resize', onScroll, { passive: true })
    return () => {
      window.removeEventListener('scroll', onScroll)
      window.removeEventListener('resize', onScroll)
      cancelAnimationFrame(raf.current)
    }
  }, [])

  return (
    <div
      className="fixed top-0 left-0 right-0 h-[2px] z-[60] pointer-events-none"
      aria-hidden="true"
    >
      <div
        ref={ref}
        className="h-full origin-left scale-x-0 opacity-0 bg-gradient-to-r from-teal via-teal to-ink-muted"
        style={{
          willChange: 'transform, opacity',
          transition: 'opacity 260ms ease',
          boxShadow: '0 0 12px rgba(100,255,218,0.65)',
        }}
      />
    </div>
  )
}
