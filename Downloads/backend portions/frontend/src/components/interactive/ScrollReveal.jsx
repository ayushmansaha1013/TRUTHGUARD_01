import { useEffect, useRef, useState } from 'react'
import { prefersReducedMotion } from '../../utils/webgl.js'

/**
 * ScrollReveal — elements fade/rise into place as they enter the viewport.
 *
 * Implementation notes:
 *  - One shared IntersectionObserver per element, disconnected after the first
 *    intersection (reveal once, then stop observing — no repeated work).
 *  - `rootMargin` starts the animation slightly before the element is fully
 *    visible, so it never feels like it "pops" in after you've already read it.
 *  - Reduced-motion users get the final state immediately with no transition.
 *  - The fallback if IntersectionObserver is missing is to just show everything.
 */
export default function ScrollReveal({
  children,
  delay = 0,
  y = 22,
  x = 0,
  scale = 1,
  duration = 620,
  className = '',
  as: Tag = 'div',
  once = true,
  ...rest
}) {
  const ref = useRef(null)
  const [shown, setShown] = useState(() => prefersReducedMotion())

  useEffect(() => {
    if (shown && once) return undefined
    const el = ref.current
    if (!el) return undefined
    if (typeof IntersectionObserver === 'undefined') {
      setShown(true)
      return undefined
    }

    const io = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            setShown(true)
            if (once) io.disconnect()
          } else if (!once) {
            setShown(false)
          }
        })
      },
      { threshold: 0.12, rootMargin: '0px 0px -8% 0px' },
    )
    io.observe(el)
    return () => io.disconnect()
  }, [once, shown])

  const reduced = prefersReducedMotion()
  const style = reduced
    ? undefined
    : {
        transitionDelay: `${delay}ms`,
        transitionDuration: `${duration}ms`,
        '--rv-y': `${y}px`,
        '--rv-x': `${x}px`,
        '--rv-s': scale,
      }

  return (
    <Tag
      ref={ref}
      className={`reveal ${shown ? 'reveal--in' : ''} ${className}`}
      style={style}
      aria-hidden={false}
      {...rest}
    >
      {children}
    </Tag>
  )
}
