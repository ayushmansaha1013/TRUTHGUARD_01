import { useEffect, useRef } from 'react'

/**
 * Hero3DFallback — pure-CSS 3D hero.
 *
 * Used when WebGL is unavailable, the GPU is a software rasteriser, or the user
 * has requested reduced motion. It still looks intentional (conic-gradient
 * orbital rings + a layered shield in real CSS 3D space), so nobody sees a
 * "broken" hero — they just see a calmer one.
 *
 * With reduced motion the animation-duration override in index.css freezes the
 * spins automatically; the pointer tilt is disabled here explicitly.
 */
export default function Hero3DFallback({ className = '' }) {
  const ref = useRef(null)

  useEffect(() => {
    const el = ref.current
    if (!el) return undefined
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return undefined
    if (window.matchMedia('(pointer: coarse)').matches) return undefined

    let raf = 0
    const onMove = (e) => {
      cancelAnimationFrame(raf)
      raf = requestAnimationFrame(() => {
        const r = el.getBoundingClientRect()
        const px = (e.clientX - r.left) / r.width - 0.5
        const py = (e.clientY - r.top) / r.height - 0.5
        el.style.setProperty('--tilt-x', `${(-py * 14).toFixed(2)}deg`)
        el.style.setProperty('--tilt-y', `${(px * 18).toFixed(2)}deg`)
      })
    }
    window.addEventListener('pointermove', onMove, { passive: true })
    return () => {
      window.removeEventListener('pointermove', onMove)
      cancelAnimationFrame(raf)
    }
  }, [])

  return (
    <div
      ref={ref}
      className={`hero3d-fallback w-full h-full grid place-items-center ${className}`}
      aria-hidden="true"
      data-testid="hero-css"
    >
      <div className="hero3d-stage">
        <div className="hero3d-ring hero3d-ring--1" />
        <div className="hero3d-ring hero3d-ring--2" />
        <div className="hero3d-ring hero3d-ring--3" />
        <div className="hero3d-core">
          <svg viewBox="0 0 64 64" className="w-16 h-16 sm:w-20 sm:h-20" fill="none">
            <path
              d="M32 6l20 8v15c0 13.5-8.5 24-20 30C20.5 53 12 42.5 12 29V14z"
              stroke="#64FFDA"
              strokeWidth="2.5"
              strokeLinejoin="round"
              opacity="0.9"
            />
            <path
              d="M32 14l13 5.2v9.6c0 8.7-5.5 15.5-13 19.4-7.5-3.9-13-10.7-13-19.4v-9.6z"
              stroke="#8892B0"
              strokeWidth="1.5"
              strokeLinejoin="round"
              opacity="0.55"
            />
            <path
              d="M23.5 32.5l6.2 6.2L43 25"
              stroke="#64FFDA"
              strokeWidth="3.4"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </div>
        {/* Floating data motes */}
        {Array.from({ length: 14 }).map((_, i) => (
          <span
            key={i}
            className="hero3d-mote"
            style={{
              '--mx': `${8 + ((i * 37) % 84)}%`,
              '--my': `${10 + ((i * 53) % 78)}%`,
              '--md': `${(i % 5) * 0.9}s`,
              '--ms': `${5 + (i % 4)}s`,
            }}
          />
        ))}
      </div>
    </div>
  )
}
