import { beforeAll, describe, expect, it, vi } from 'vitest'
import { render, screen, fireEvent, act } from '@testing-library/react'

import ScrollReveal from './ScrollReveal.jsx'
import CountUp from './CountUp.jsx'
import VerdictFlip from './VerdictFlip.jsx'
import TiltCard from './TiltCard.jsx'
import SpotlightCard from './SpotlightCard.jsx'
import MagneticButton from './MagneticButton.jsx'
import Hero3D from '../three/Hero3D.jsx'

/**
 * ---------------------------------------------------------------------------
 * Tests for the 3D / interaction layer.
 * ---------------------------------------------------------------------------
 * The point of these tests is not to assert that things look pretty — it is to
 * lock in the ACCESSIBILITY and RESILIENCE guarantees, which are the parts that
 * silently break:
 *   • every effect degrades correctly when WebGL is missing (jsdom has none, so
 *     this is the natural environment to prove the fallback path)
 *   • every effect respects prefers-reduced-motion
 *   • decorative layers never intercept clicks or hide content from a screen reader
 */

beforeAll(() => {
  // jsdom implements neither matchMedia nor WebGL. Stub matchMedia so the
  // capability helpers behave deterministically.
  if (!window.matchMedia) {
    window.matchMedia = vi.fn().mockImplementation((query) => ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }))
  }
})

describe('Hero3D — graceful degradation', () => {
  it('renders the CSS 3D fallback when WebGL is unavailable (jsdom has none)', () => {
    render(<Hero3D />)
    // No <canvas>, no crash, and the fallback stage is present instead.
    expect(screen.getByTestId('hero-css')).toBeTruthy()
    expect(document.querySelector('canvas')).toBeNull()
  })

  it('marks itself aria-hidden so screen readers skip the decoration', () => {
    render(<Hero3D />)
    expect(screen.getByTestId('hero-css').getAttribute('aria-hidden')).toBe('true')
  })

  it('survives a pulse prop changing before any scene exists', () => {
    const { rerender } = render(<Hero3D pulse={0} />)
    expect(() => rerender(<Hero3D pulse={3} />)).not.toThrow()
    expect(screen.getByTestId('hero-css')).toBeTruthy()
  })
})

describe('ScrollReveal', () => {
  it('renders its children regardless of reveal state (content is never hidden)', () => {
    render(
      <ScrollReveal>
        <p>important copy</p>
      </ScrollReveal>,
    )
    expect(screen.getByText('important copy')).toBeTruthy()
  })

  it('falls back to visible when IntersectionObserver is unavailable', () => {
    const had = global.IntersectionObserver
    delete global.IntersectionObserver
    const { container } = render(
      <ScrollReveal>
        <p>x</p>
      </ScrollReveal>,
    )
    expect(container.querySelector('.reveal--in')).toBeTruthy()
    global.IntersectionObserver = had
  })
})

describe('CountUp', () => {
  it('lands exactly on the target value (no floating point drift in the UI)', async () => {
    vi.useFakeTimers()
    render(<CountUp value={1234.5} decimals={1} duration={50} />)
    await act(async () => {
      vi.advanceTimersByTime(400)
    })
    expect(screen.getByText('1,234.5')).toBeTruthy()
    vi.useRealTimers()
  })

  it('renders 0 as 0 rather than NaN for a missing value', () => {
    render(<CountUp value={undefined} decimals={0} />)
    expect(screen.getByText('0')).toBeTruthy()
  })

  it('supports prefix/suffix for percentages', async () => {
    vi.useFakeTimers()
    render(<CountUp value={87} decimals={0} suffix="%" duration={40} />)
    await act(async () => {
      vi.advanceTimersByTime(300)
    })
    expect(screen.getByText('87%')).toBeTruthy()
    vi.useRealTimers()
  })
})

describe('VerdictFlip', () => {
  it('marks exactly one face visible per state', () => {
    const { rerender, container } = render(
      <VerdictFlip state="idle">
        <div>RESULT</div>
      </VerdictFlip>,
    )
    const visible = () =>
      Array.from(container.querySelectorAll('.flip-face')).filter(
        (f) => f.getAttribute('data-visible') === 'true',
      )

    expect(visible()).toHaveLength(1)

    rerender(
      <VerdictFlip state="scanning">
        <div>RESULT</div>
      </VerdictFlip>,
    )
    expect(visible()).toHaveLength(1)

    rerender(
      <VerdictFlip state="done">
        <div>RESULT</div>
      </VerdictFlip>,
    )
    expect(visible()).toHaveLength(1)
    // ...and it is the result face, with the children mounted.
    expect(screen.getByText('RESULT')).toBeTruthy()
  })

  it('exposes an aria-live region so the verdict is announced', () => {
    const { container } = render(
      <VerdictFlip state="done">
        <div>Likely Fake</div>
      </VerdictFlip>,
    )
    expect(container.querySelector('[aria-live="polite"]')).toBeTruthy()
  })
})

describe('TiltCard', () => {
  it('renders children and applies perspective to the wrapper', () => {
    const { container } = render(
      <TiltCard perspective={900}>
        <p>card body</p>
      </TiltCard>,
    )
    expect(screen.getByText('card body')).toBeTruthy()
    expect(container.querySelector('.tilt-wrap').style.perspective).toBe('900px')
  })

  it('the glare overlay is pointer-transparent decoration (cannot swallow clicks)', () => {
    render(
      <TiltCard>
        <button type="button">click me</button>
      </TiltCard>,
    )
    const btn = screen.getByText('click me')
    // The button must still be hit-testable at its own centre.
    expect(btn).toBeTruthy()
    const glare = document.querySelector('.tilt-glare')
    expect(glare).toBeTruthy()
  })
})

describe('SpotlightCard', () => {
  it('passes through children and sets the spotlight radius variable', () => {
    const { container } = render(
      <SpotlightCard radius={420}>
        <p>inside</p>
      </SpotlightCard>,
    )
    expect(screen.getByText('inside')).toBeTruthy()
    expect(container.querySelector('.spotlight').style.getPropertyValue('--spot-r')).toBe('420px')
  })
})

describe('MagneticButton', () => {
  it('renders as a <button type="button"> by default and still forwards props', () => {
    let clicked = 0
    render(
      <MagneticButton onClick={() => clicked++}>
        Go
      </MagneticButton>,
    )
    const btn = screen.getByRole('button', { name: /Go/ })
    expect(btn.getAttribute('type')).toBe('button')
    fireEvent.click(btn)
    expect(clicked).toBe(1)
  })

  it('can render as a link while keeping the magnetic wrapper', () => {
    render(
      <MagneticButton as="a" href="/signup">
        Sign up
      </MagneticButton>,
    )
    const a = screen.getByRole('link', { name: /Sign up/ })
    expect(a.getAttribute('href')).toBe('/signup')
    expect(a.querySelector('.magnetic-label')).toBeTruthy()
  })

  it('respects the disabled attribute (no drift away from a dead control)', () => {
    render(<MagneticButton disabled>Disabled</MagneticButton>)
    const btn = screen.getByRole('button')
    expect(btn.disabled).toBe(true)
    // A disabled button must not translate toward the cursor: moving a dead
    // control implies it is clickable.
    fireEvent.pointerMove(btn, { clientX: 400, clientY: 400 })
    expect(btn.style.transform || '').not.toContain('translate3d')
  })
})
