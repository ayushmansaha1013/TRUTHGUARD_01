import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { SafeLink, VerdictBadge, ConfidenceGauge, toneFor } from './ui.jsx'

/** XSS-prevention and design-system assertions (Part C.5 + Part A design spec). */

describe('SafeLink — untrusted AI-returned URLs (Part C.5)', () => {
  it('renders https sources as a link with rel="noopener noreferrer"', () => {
    render(<SafeLink href="https://www.reuters.com/world/2024" />)
    const a = screen.getByRole('link')
    expect(a.getAttribute('href')).toBe('https://www.reuters.com/world/2024')
    expect(a.getAttribute('target')).toBe('_blank')
    expect(a.getAttribute('rel')).toContain('noopener')
    expect(a.getAttribute('rel')).toContain('noreferrer')
  })

  it('renders a javascript: URL as INERT TEXT, not a clickable link', () => {
    const { container } = render(
      <SafeLink href="javascript:alert(document.cookie)" />,
    )
    expect(container.querySelector('a')).toBeNull()          // no anchor at all
    expect(container.textContent).toContain('javascript:')   // shown as escaped text
  })

  it('renders a data: URL as inert text', () => {
    const { container } = render(<SafeLink href="data:text/html,<script>alert(1)</script>" />)
    expect(container.querySelector('a')).toBeNull()
  })

  it('escapes markup in the URL text instead of interpreting it', () => {
    const { container } = render(<SafeLink href="<img src=x onerror=alert(1)>" />)
    expect(container.querySelector('img')).toBeNull()
    expect(container.innerHTML).not.toContain('<img')
    expect(container.textContent).toContain('<img src=x onerror=alert(1)>')
  })
})

describe('VerdictBadge — colour coding per the design spec (Part A)', () => {
  it('maps Likely Fake / False to the danger tone (red)', () => {
    expect(toneFor('Likely Fake')).toBe('fake')
    expect(toneFor('False')).toBe('fake')
    expect(toneFor('Misleading')).toBe('fake')
  })

  it('maps Likely Real / True to the safe tone (green)', () => {
    expect(toneFor('Likely Real')).toBe('real')
    expect(toneFor('True')).toBe('real')
  })

  it('maps Uncertain / Unverified to the warning tone (yellow)', () => {
    expect(toneFor('Uncertain')).toBe('uncertain')
    expect(toneFor('Unverified')).toBe('uncertain')
  })

  it('never relies on colour alone — the verdict text is always rendered', () => {
    render(<VerdictBadge verdict="Likely Fake" />)
    expect(screen.getByText('Likely Fake')).toBeTruthy()
  })
})

describe('ConfidenceGauge', () => {
  it('exposes an accessible progressbar with the right value', () => {
    render(<ConfidenceGauge confidence={94.2} verdict="Likely Fake" />)
    const bar = screen.getByRole('progressbar')
    expect(bar.getAttribute('aria-valuenow')).toBe('94.2')
    expect(screen.getByText('94.2%')).toBeTruthy()
  })

  it('clamps out-of-range values so a malformed response cannot break the layout', () => {
    render(<ConfidenceGauge confidence={9999} verdict="Likely Fake" />)
    expect(screen.getByRole('progressbar').getAttribute('aria-valuenow')).toBe('100')
  })

  it('handles a missing/non-numeric confidence gracefully', () => {
    render(<ConfidenceGauge confidence={undefined} verdict="Uncertain" />)
    expect(screen.getByRole('progressbar').getAttribute('aria-valuenow')).toBe('0')
  })
})
