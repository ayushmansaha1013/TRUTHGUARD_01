/**
 * AmbientBackground — the fixed, decorative depth layer behind the whole app.
 *
 * Three ingredients:
 *   1. `.bg-grid`    a repeating-linear-gradient rotated in 3D → a receding floor
 *   2. `.bg-aurora`  two large blurred radial fields that drift slowly
 *   3. `.bg-noise`   an inline SVG turbulence texture at 4% opacity (a data URI,
 *                    so it needs no network request and works in the sandboxed
 *                    in-app preview)
 *
 * `position: fixed; pointer-events: none` — it can never intercept a click, and
 * it never forces a repaint of the content above it.
 *
 * The whole thing is `aria-hidden`: it conveys no information, so screen readers
 * skip it entirely.
 */
export default function AmbientBackground() {
  return (
    <div className="bg-stage" aria-hidden="true">
      <div className="bg-aurora bg-aurora--a" />
      <div className="bg-aurora bg-aurora--b" />
      <div className="bg-grid" />
      <div className="bg-noise" />
    </div>
  )
}
