import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import Signup, { passwordStrength } from './Signup.jsx'

/**
 * ---------------------------------------------------------------------------
 * Hick's Law regression tests for the signup form.
 * ---------------------------------------------------------------------------
 * These lock in a *design decision* as code, so a future teammate cannot quietly
 * re-add fields and push the decision count back up. If someone adds a "confirm
 * password" input, this suite fails with an explanation.
 */

vi.mock('../context/AuthContext.jsx', () => ({
  useAuth: () => ({
    signUp: vi.fn(),
    isAuthenticated: false,
    role: null,
    loading: false,
  }),
}))
vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal()
  return { ...actual, useNavigate: () => vi.fn() }
})
vi.mock('../components/Toast.jsx', () => ({
  useToast: () => ({ success: vi.fn(), error: vi.fn(), info: vi.fn(), warn: vi.fn(), toast: vi.fn() }),
}))

function renderSignup() {
  return render(
    <MemoryRouter>
      <Signup />
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('Signup form — decision count (Hick\'s Law)', () => {
  it('asks for exactly TWO pieces of text input: email and password', () => {
    renderSignup()
    const textInputs = screen
      .queryAllByRole('textbox')
      .concat(
        Array.from(document.querySelectorAll('input[type="password"], input[type="text"]')).filter(
          (el) => el.getAttribute('aria-label') !== null || el.type === 'password',
        ),
      )
    // Deduplicate by element identity.
    const unique = new Set(textInputs)
    expect(unique.size).toBe(2)
  })

  it('has NO confirm-password field (visibility toggle replaces duplication)', () => {
    renderSignup()
    const passwordFields = document.querySelectorAll('input[type="password"], input#su-password')
    expect(passwordFields.length).toBe(1)
    expect(screen.queryByLabelText(/confirm password/i)).toBeNull()
    // ...and offers a Show/Hide toggle instead, which is the compensating control.
    expect(screen.getByRole('button', { name: /show/i })).toBeTruthy()
  })

  it('offers exactly TWO role options, with the least-privileged one pre-selected', () => {
    renderSignup()
    const radios = screen.queryAllByRole('radio')
    expect(radios).toHaveLength(2)
    const student = radios.find((r) => r.value === 'student')
    const educator = radios.find((r) => r.value === 'educator')
    expect(student.checked).toBe(true) // default = least privilege, zero interaction
    expect(educator.checked).toBe(false)
  })

  it('has exactly ONE submit control', () => {
    renderSignup()
    const submits = Array.from(document.querySelectorAll('button[type="submit"]'))
    expect(submits).toHaveLength(1)
  })
})

describe('passwordStrength — live feedback that replaces the confirm field', () => {
  it('scores an empty password as weak, not as an error', () => {
    expect(passwordStrength('').label).toBe('Weak')
    expect(passwordStrength('').pct).toBe(20)
  })

  it('rises monotonically with length and character variety', () => {
    const scores = [
      passwordStrength('abcdef').pct,
      passwordStrength('abcdefghij').pct,
      passwordStrength('Abcdefghij').pct,
      passwordStrength('Abcdefghij1').pct,
      passwordStrength('Abcdefghij1!').pct,
    ]
    expect(scores).toEqual([...scores].sort((a, b) => a - b))
    expect(scores[scores.length - 1]).toBe(100)
  })

  it('never exceeds 100% width (cannot blow out the meter)', () => {
    expect(passwordStrength('A1!'.repeat(80)).pct).toBeLessThanOrEqual(100)
  })
})
