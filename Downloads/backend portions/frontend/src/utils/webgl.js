/**
 * Capability detection for the 3D layer.
 *
 * WHY THIS EXISTS (accessibility + resilience, not just polish):
 *   A WebGL scene that fails to initialise leaves a black hole in the hero. So we
 *   detect support up front and render a CSS-only 3D fallback instead. We also
 *   honour `prefers-reduced-motion`, which is a WCAG 2.2.2 requirement: users who
 *   ask the OS to reduce motion must not get a spinning particle field.
 */

/** True when the browser can create a WebGL context. */
export function detectWebGL() {
  try {
    const canvas = document.createElement('canvas')
    const gl =
      canvas.getContext('webgl2') ||
      canvas.getContext('webgl') ||
      canvas.getContext('experimental-webgl')
    if (!gl) return false
    // Some virtualised GPUs report a context but cannot render; a tiny sanity
    // check on the renderer string catches the worst offenders.
    const debug = gl.getExtension('WEBGL_debug_renderer_info')
    const renderer = debug ? String(gl.getParameter(debug.UNMASKED_RENDERER_WEBGL)) : ''
    if (/SwiftShader|llvmpipe|Software/i.test(renderer)) return false // software rasteriser = too slow
    // Lose the probe context immediately so we don't hold a GPU slot.
    gl.getExtension('WEBGL_lose_context')?.loseContext()
    return true
  } catch {
    return false
  }
}

/** True when the user has asked the OS to minimise motion. */
export function prefersReducedMotion() {
  if (typeof window === 'undefined' || !window.matchMedia) return false
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

/** Live subscription to the reduced-motion preference (users can toggle it mid-session). */
export function onReducedMotionChange(cb) {
  if (typeof window === 'undefined' || !window.matchMedia) return () => {}
  const mq = window.matchMedia('(prefers-reduced-motion: reduce)')
  const handler = (e) => cb(e.matches)
  mq.addEventListener?.('change', handler)
  return () => mq.removeEventListener?.('change', handler)
}

/** Coarse pointer (touch device) — we disable hover-only effects there. */
export function isCoarsePointer() {
  if (typeof window === 'undefined' || !window.matchMedia) return false
  return window.matchMedia('(pointer: coarse)').matches
}

/** Device pixel ratio, capped: 3x retina phones would otherwise render 9x the pixels. */
export function cappedPixelRatio(max = 2) {
  if (typeof window === 'undefined') return 1
  return Math.min(window.devicePixelRatio || 1, max)
}
