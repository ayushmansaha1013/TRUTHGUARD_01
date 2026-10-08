import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

import ProtectedRoute from './ProtectedRoute.jsx'
import EducatorRoute from './EducatorRoute.jsx'

/**
 * ---------------------------------------------------------------------------
 * RBAC layer-1 tests (Part B.4)
 * ---------------------------------------------------------------------------
 * These prove the exact behaviours the marking rubric asks about:
 *   1. an unauthenticated visitor is redirected to /login
 *   2. a STUDENT is redirected away from the educator dashboard to /403
 *   3. an EDUCATOR is allowed through
 *
 * `useAuth` is mocked because these tests target the GUARD LOGIC, not Supabase.
 * (Supabase RLS — the authoritative layer — is tested with SQL, see
 *  docs/TESTING_CHECKLIST.md §3.4 and §4.)
 */
vi.mock('../context/AuthContext.jsx', () => ({
  useAuth: vi.fn(),
}))
const { useAuth } = await import('../context/AuthContext.jsx')

function renderAt(path, element) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/login" element={<div>LOGIN PAGE</div>} />
        <Route path="/403" element={<div>ACCESS DENIED PAGE</div>} />
        <Route path="/dashboard" element={element} />
        <Route path="/scanner" element={<div>SCANNER PAGE</div>} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('ProtectedRoute — authentication gate', () => {
  it('redirects an unauthenticated visitor to /login', () => {
    useAuth.mockReturnValue({ isAuthenticated: false, loading: false })
    renderAt('/dashboard', <ProtectedRoute><div>SECRET DASHBOARD</div></ProtectedRoute>)

    expect(screen.getByText('LOGIN PAGE')).toBeTruthy()
    expect(screen.queryByText('SECRET DASHBOARD')).toBeNull()
  })

  it('renders children for an authenticated visitor', () => {
    useAuth.mockReturnValue({ isAuthenticated: true, loading: false })
    renderAt('/dashboard', <ProtectedRoute><div>SECRET DASHBOARD</div></ProtectedRoute>)

    expect(screen.getByText('SECRET DASHBOARD')).toBeTruthy()
    expect(screen.queryByText('LOGIN PAGE')).toBeNull()
  })

  it('fails CLOSED: renders nothing while the session is still loading', () => {
    useAuth.mockReturnValue({ isAuthenticated: false, loading: true })
    const { container } = renderAt(
      '/dashboard',
      <ProtectedRoute><div>SECRET DASHBOARD</div></ProtectedRoute>,
    )

    expect(screen.queryByText('SECRET DASHBOARD')).toBeNull()
    expect(screen.queryByText('LOGIN PAGE')).toBeNull()
    expect(container.textContent).toBe('')
  })
})

describe('EducatorRoute — role gate', () => {
  const wrap = (
    <ProtectedRoute>
      <EducatorRoute>
        <div>SECRET DASHBOARD</div>
      </EducatorRoute>
    </ProtectedRoute>
  )

  it('redirects a STUDENT to the 403 Access Denied page', () => {
    useAuth.mockReturnValue({ isAuthenticated: true, isEducator: false, role: 'student', loading: false })
    renderAt('/dashboard', wrap)

    expect(screen.getByText('ACCESS DENIED PAGE')).toBeTruthy()
    expect(screen.queryByText('SECRET DASHBOARD')).toBeNull()
  })

  it('renders the dashboard for an EDUCATOR', () => {
    useAuth.mockReturnValue({ isAuthenticated: true, isEducator: true, role: 'educator', loading: false })
    renderAt('/dashboard', wrap)

    expect(screen.getByText('SECRET DASHBOARD')).toBeTruthy()
    expect(screen.queryByText('ACCESS DENIED PAGE')).toBeNull()
  })

  it('redirects to /login BEFORE /403 when the user is anonymous (authn precedes authz)', () => {
    useAuth.mockReturnValue({ isAuthenticated: false, isEducator: false, role: null, loading: false })
    renderAt('/dashboard', wrap)

    expect(screen.getByText('LOGIN PAGE')).toBeTruthy()
    expect(screen.queryByText('ACCESS DENIED PAGE')).toBeNull()
  })

  it('treats an unknown/undefined role as NOT an educator (least privilege)', () => {
    useAuth.mockReturnValue({ isAuthenticated: true, isEducator: false, role: undefined, loading: false })
    renderAt('/dashboard', wrap)

    expect(screen.getByText('ACCESS DENIED PAGE')).toBeTruthy()
  })
})
