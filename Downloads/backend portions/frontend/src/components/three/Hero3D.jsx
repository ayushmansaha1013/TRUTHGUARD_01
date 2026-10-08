import { useEffect, useRef, useState } from 'react'
import {
  cappedPixelRatio,
  detectWebGL,
  isCoarsePointer,
  onReducedMotionChange,
  prefersReducedMotion,
} from '../../utils/webgl.js'
import Hero3DFallback from './Hero3DFallback.jsx'

/**
 * ===========================================================================
 * Hero3D — the WebGL centrepiece (Three.js)
 * ===========================================================================
 * A slowly rotating wireframe icosahedron ("the shield") wrapped in two orbital
 * rings and a 2,000-point particle field, lit in the TruthGuard palette. It
 * parallaxes toward the pointer, drifts on scroll, and can be pulsed red by the
 * scanner when a deepfake is found.
 *
 * ENGINEERING DECISIONS THAT MATTER (all of these are demo/report talking points):
 *
 *  1. LAZY LOADING — `three` is imported dynamically inside the effect, so the
 *     ~150 kB gzipped library never lands in the initial bundle. Users who never
 *     see the hero (deep links to /scanner) never download it.
 *
 *  2. GRACEFUL DEGRADATION — if WebGL is unavailable, or the GPU is a software
 *     rasteriser, we render <Hero3DFallback/> (pure CSS 3D) instead. No black hole.
 *
 *  3. prefers-reduced-motion — WCAG 2.2.2. When set, we skip WebGL entirely and
 *     show the static fallback; we also re-check live, because users can toggle it.
 *
 *  4. VISIBILITY-BASED RENDERING — the rAF loop is paused when the canvas scrolls
 *     out of view (IntersectionObserver) and when the tab is hidden
 *     (visibilitychange). A hidden animation loop is wasted battery and heat.
 *
 *  5. POINTER PASSIVITY — we never move the camera from a pointer event handler.
 *     We store the target and lerp toward it inside the loop, so motion stays
 *     smooth at any pointer sampling rate (125 Hz mice, 240 Hz trackpads).
 *
 *  6. FULL DISPOSAL — geometries, materials, the renderer and its canvas are all
 *     released on unmount. Skipping this is the #1 cause of GPU memory leaks in
 *     React + Three apps, and React StrictMode mounts effects twice in dev, so a
 *     leak here would be immediately visible.
 * ===========================================================================
 */

const PALETTE = {
  teal: 0x64ffda,
  slate: 0x8892b0,
  danger: 0xff4d4d,
  navy: 0x0a192f,
}

export default function Hero3D({ pulse = 0, className = '' }) {
  const mountRef = useRef(null)
  const pulseRef = useRef(0)
  const apiRef = useRef(null)
  const [mode, setMode] = useState('deciding') // 'webgl' | 'css' | 'deciding'

  // A non-zero `pulse` prop triggers a red shockwave through the scene.
  useEffect(() => {
    if (!pulse) return
    pulseRef.current = 1
    apiRef.current?.pulse?.()
  }, [pulse])

  useEffect(() => {
    const reduced = prefersReducedMotion()
    const supported = !reduced && detectWebGL()
    setMode(supported ? 'webgl' : 'css')
    if (!supported) return undefined

    let disposed = false
    let raf = 0
    let renderer, scene, camera, shield, rings, points, core
    let inView = true
    let visibleTab = true

    const pointer = { x: 0, y: 0, tx: 0, ty: 0 }
    let scrollY = 0
    let pulseEnergy = 0
    let clock
    // Scratch objects reused every frame: allocating a new THREE.Color 60x/second
    // is exactly the kind of thing that causes GC stutter in animation loops.
    let scratchDanger = null
    let scratchCore = null

    /* ------------------------------ pointer ------------------------------ */
    // Coarse pointers (phones) get no parallax: there is no hover, and tilting on
    // touch-drag fights the page scroll.
    const onPointerMove = (e) => {
      if (isCoarsePointer()) return
      pointer.tx = (e.clientX / window.innerWidth) * 2 - 1
      pointer.ty = -((e.clientY / window.innerHeight) * 2 - 1)
    }
    const onScroll = () => {
      scrollY = window.scrollY || 0
    }
    const onVisibility = () => {
      visibleTab = !document.hidden
    }

    /* --------------------------- reduced motion --------------------------- */
    const offMotion = onReducedMotionChange((reduce) => {
      if (reduce) teardown()
    })

    /* ------------------------------- teardown ------------------------------ */
    function teardown() {
      if (disposed) return
      disposed = true
      cancelAnimationFrame(raf)
      window.removeEventListener('pointermove', onPointerMove)
      window.removeEventListener('scroll', onScroll, { passive: true })
      window.removeEventListener('resize', onResize)
      document.removeEventListener('visibilitychange', onVisibility)
      observer?.disconnect()
      offMotion()

      // Dispose every GPU resource we created, then drop the canvas.
      scene?.traverse((obj) => {
        obj.geometry?.dispose?.()
        const mat = obj.material
        if (Array.isArray(mat)) mat.forEach((m) => m?.dispose?.())
        else mat?.dispose?.()
      })
      renderer?.dispose?.()
      renderer?.forceContextLoss?.()
      if (renderer?.domElement?.parentNode) {
        renderer.domElement.parentNode.removeChild(renderer.domElement)
      }
      apiRef.current = null
    }

    /* -------------------------------- resize ------------------------------- */
    function onResize() {
      const el = mountRef.current
      if (!el || !renderer || !camera) return
      const w = el.clientWidth
      const h = el.clientHeight
      renderer.setSize(w, h, false)
      camera.aspect = w / Math.max(1, h)
      camera.updateProjectionMatrix()
    }

    let observer = null

    ;(async () => {
      // 1) LAZY IMPORT — keeps `three` out of the initial bundle.
      const THREE = await import('three')
      if (disposed || !mountRef.current) return

      clock = new THREE.Clock()
      const el = mountRef.current
      const w = el.clientWidth
      const h = el.clientHeight

      /* ------------------------------- scene ------------------------------- */
      scene = new THREE.Scene()
      scene.fog = new THREE.FogExp2(PALETTE.navy, 0.055)

      camera = new THREE.PerspectiveCamera(45, w / Math.max(1, h), 0.1, 100)
      camera.position.set(0, 0, 9)

      renderer = new THREE.WebGLRenderer({
        antialias: true,
        alpha: true, // transparent so the CSS gradient shows through
        powerPreference: 'high-performance',
      })
      renderer.setPixelRatio(cappedPixelRatio(2))
      renderer.setSize(w, h, false)
      renderer.setClearColor(0x000000, 0)
      renderer.domElement.style.width = '100%'
      renderer.domElement.style.height = '100%'
      renderer.domElement.style.display = 'block'
      // The canvas is decorative: hide it from assistive tech and from tab order.
      renderer.domElement.setAttribute('aria-hidden', 'true')
      el.appendChild(renderer.domElement)

      /* --------------------- the shield (wireframe icosahedron) ------------- */
      const shieldGroup = new THREE.Group()
      scene.add(shieldGroup)

      const outerGeo = new THREE.IcosahedronGeometry(2.15, 1)
      const outerMat = new THREE.MeshBasicMaterial({
        color: PALETTE.teal,
        wireframe: true,
        transparent: true,
        opacity: 0.32,
      })
      shield = new THREE.Mesh(outerGeo, outerMat)
      shieldGroup.add(shield)

      const innerGeo = new THREE.IcosahedronGeometry(1.45, 0)
      const innerMat = new THREE.MeshBasicMaterial({
        color: PALETTE.slate,
        wireframe: true,
        transparent: true,
        opacity: 0.22,
      })
      const inner = new THREE.Mesh(innerGeo, innerMat)
      shieldGroup.add(inner)

      // A solid dark core gives the wireframe something to occlude, which is what
      // makes it read as a 3D object rather than a flat line drawing.
      const coreGeo = new THREE.IcosahedronGeometry(1.02, 2)
      const coreMat = new THREE.MeshBasicMaterial({
        color: 0x112240,
        transparent: true,
        opacity: 0.92,
      })
      core = new THREE.Mesh(coreGeo, coreMat)
      shieldGroup.add(core)

      /* ------------------------------ orbit rings --------------------------- */
      rings = new THREE.Group()
      const ringSpecs = [
        { r: 2.95, tube: 0.012, color: PALETTE.teal, opacity: 0.5, rot: [Math.PI / 2.3, 0, 0], speed: 0.28 },
        { r: 3.45, tube: 0.008, color: PALETTE.slate, opacity: 0.35, rot: [Math.PI / 1.7, 0.6, 0], speed: -0.19 },
      ]
      ringSpecs.forEach((s) => {
        const geo = new THREE.TorusGeometry(s.r, s.tube, 8, 160)
        const mat = new THREE.MeshBasicMaterial({
          color: s.color,
          transparent: true,
          opacity: s.opacity,
        })
        const mesh = new THREE.Mesh(geo, mat)
        mesh.rotation.set(...s.rot)
        mesh.userData.speed = s.speed
        rings.add(mesh)
      })
      scene.add(rings)

      /* ---------------------------- particle field -------------------------- */
      // A single Points object = one draw call for 2,000 particles. Creating 2,000
      // meshes instead would be a classic beginner performance mistake.
      const COUNT = 2000
      const positions = new Float32Array(COUNT * 3)
      const colors = new Float32Array(COUNT * 3)
      const cTeal = new THREE.Color(PALETTE.teal)
      const cSlate = new THREE.Color(PALETTE.slate)
      const tmp = new THREE.Color()
      scratchDanger = new THREE.Color(PALETTE.danger)
      scratchCore = new THREE.Color(0x2a1020)

      for (let i = 0; i < COUNT; i++) {
        // Distribute in a spherical shell so the field has depth, not a flat disc.
        const radius = 4.5 + Math.random() * 9
        const theta = Math.random() * Math.PI * 2
        const phi = Math.acos(2 * Math.random() - 1)
        positions[i * 3] = radius * Math.sin(phi) * Math.cos(theta)
        positions[i * 3 + 1] = radius * Math.sin(phi) * Math.sin(theta)
        positions[i * 3 + 2] = radius * Math.cos(phi)

        tmp.copy(Math.random() > 0.72 ? cTeal : cSlate)
        colors[i * 3] = tmp.r
        colors[i * 3 + 1] = tmp.g
        colors[i * 3 + 2] = tmp.b
      }

      const pGeo = new THREE.BufferGeometry()
      pGeo.setAttribute('position', new THREE.BufferAttribute(positions, 3))
      pGeo.setAttribute('color', new THREE.BufferAttribute(colors, 3))
      const pMat = new THREE.PointsMaterial({
        size: 0.045,
        vertexColors: true,
        transparent: true,
        opacity: 0.75,
        depthWrite: false, // avoids ugly sorting artefacts on additive-ish particles
        sizeAttenuation: true,
      })
      points = new THREE.Points(pGeo, pMat)
      scene.add(points)

      /* ------------------------------ observers ----------------------------- */
      observer = new IntersectionObserver(
        (entries) => {
          inView = entries[0]?.isIntersecting ?? true
        },
        { threshold: 0 },
      )
      observer.observe(el)

      window.addEventListener('pointermove', onPointerMove, { passive: true })
      window.addEventListener('scroll', onScroll, { passive: true })
      window.addEventListener('resize', onResize)
      document.addEventListener('visibilitychange', onVisibility)
      onResize()

      /* -------------------------------- loop -------------------------------- */
      function frame() {
        raf = requestAnimationFrame(frame)
        if (disposed) return
        // Skip rendering entirely when nobody can see it.
        if (!inView || !visibleTab) return

        const t = clock.getElapsedTime()

        // Lerp the pointer target -> smooth, frame-rate independent easing.
        pointer.x += (pointer.tx - pointer.x) * 0.045
        pointer.y += (pointer.ty - pointer.y) * 0.045

        // Decay the "threat pulse" energy so a detection flashes red then settles.
        pulseEnergy *= 0.955
        if (pulseEnergy < 0.001) pulseEnergy = 0

        shieldGroup.rotation.y = t * 0.18 + pointer.x * 0.55
        shieldGroup.rotation.x = Math.sin(t * 0.22) * 0.14 - pointer.y * 0.4
        shieldGroup.position.y = Math.sin(t * 0.6) * 0.12

        inner.rotation.y = -t * 0.34
        inner.rotation.z = t * 0.12
        core.rotation.y = t * 0.1

        rings.children.forEach((ring) => {
          ring.rotation.z += ring.userData.speed * 0.006
        })
        rings.rotation.y = t * 0.05 + pointer.x * 0.25
        rings.rotation.x = -pointer.y * 0.2

        points.rotation.y = t * 0.014
        points.rotation.x = pointer.y * 0.05

        // Pulse response: expand slightly, brighten, and shift toward danger red.
        const scale = 1 + pulseEnergy * 0.16
        shieldGroup.scale.setScalar(scale)
        outerMat.opacity = 0.32 + pulseEnergy * 0.5
        outerMat.color.copy(cTeal).lerp(scratchDanger, pulseEnergy)
        coreMat.color.setHex(0x112240).lerp(scratchCore, pulseEnergy * 0.8)

        // Scroll parallax: the whole rig recedes and drifts up as you scroll.
        const scrollFactor = Math.min(scrollY / 700, 1)
        camera.position.y = -scrollFactor * 1.5 + pointer.y * 0.35
        camera.position.x = pointer.x * 0.45
        camera.position.z = 9 + scrollFactor * 2.2
        camera.lookAt(0, -scrollFactor * 0.4, 0)

        renderer.render(scene, camera)
      }
      frame()

      /* ------------------------- imperative pulse API ------------------------ */
      apiRef.current = {
        pulse() {
          pulseEnergy = 1
        },
      }
      // If a pulse was requested while the lazy `three` import was still in
      // flight, honour it now instead of dropping it.
      if (pulseRef.current) pulseEnergy = 1
    })()

    return teardown
    // `pulse` is handled by its own effect; this one builds the scene once,
    // after `mode` has been decided.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode])

  if (mode === 'deciding') {
    return <div className={`w-full h-full ${className}`} aria-hidden="true" />
  }

  if (mode === 'css') {
    return <Hero3DFallback className={className} />
  }

  return (
    <div
      ref={mountRef}
      className={`w-full h-full ${className}`}
      aria-hidden="true"
      data-testid="hero-webgl"
    />
  )
}
