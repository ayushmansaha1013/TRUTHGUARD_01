import { Route, Routes, useLocation } from 'react-router-dom'
import { useAuth } from './context/AuthContext.jsx'

import AmbientBackground from './components/AmbientBackground.jsx'
import ScrollProgress from './components/ScrollProgress.jsx'
import Navbar from './components/Navbar.jsx'
import FullPageLoader from './components/FullPageLoader.jsx'
import ProtectedRoute from './components/ProtectedRoute.jsx'
import EducatorRoute from './components/EducatorRoute.jsx'

import Landing from './pages/Landing.jsx'
import Login from './pages/Login.jsx'
import Signup from './pages/Signup.jsx'
import ImageScanner from './pages/ImageScanner.jsx'
import FactChecker from './pages/FactChecker.jsx'
import EducatorDashboard from './pages/EducatorDashboard.jsx'
import AccessDenied from './pages/AccessDenied.jsx'
import NotFound from './pages/NotFound.jsx'

/**
 * App shell + route table.
 *
 * SECURITY (Part C.7 — RBAC layer 1 of 3, "Frontend route protection"):
 *   Public    : /, /login, /signup
 *   Auth only : /scanner, /fact-checker          -> <ProtectedRoute>
 *   Educator  : /dashboard                       -> <ProtectedRoute><EducatorRoute>
 *
 * IMPORTANT for the report: hiding a route in React is a UX convenience, NOT a
 * security boundary — anyone can call an API directly. The real enforcement is
 * Supabase Row Level Security (layer 2) and the backend JWT role-claim check
 * (layer 3). Frontend routing only stops honest users from seeing UI they have
 * no business using.
 *
 * Z-ORDER CONTRACT for the 3D layer:
 *   0   AmbientBackground (fixed, pointer-events:none, purely decorative)
 *   10  page content      (relative, so it paints above the background)
 *   40  Navbar            (sticky glass)
 *   50  toasts            (in Toast.jsx)
 *   60  ScrollProgress    (fixed hairline, pointer-events:none)
 * Keeping the decorative layer at pointer-events:none is what guarantees a
 * blurred aurora blob can never swallow a click on a button beneath it.
 */
export default function App() {
  const { loading } = useAuth()
  const location = useLocation()

  // While Supabase restores the session from storage we render a loader,
  // so a refresh on /scanner never flashes the login page.
  if (loading) return <FullPageLoader label="Restoring your secure session…" />

  const isAuthPage = ['/login', '/signup'].includes(location.pathname)

  return (
    <div className="relative min-h-screen flex flex-col">
      <AmbientBackground />
      <ScrollProgress />

      {!isAuthPage && <Navbar />}

      <main className="relative z-10 flex-1">
        <Routes>
          {/* ---------- Public ---------- */}
          <Route path="/" element={<Landing />} />
          <Route path="/login" element={<Login />} />
          <Route path="/signup" element={<Signup />} />

          {/* ---------- Authenticated (any role) ---------- */}
          <Route
            path="/scanner"
            element={
              <ProtectedRoute>
                <ImageScanner />
              </ProtectedRoute>
            }
          />
          <Route
            path="/fact-checker"
            element={
              <ProtectedRoute>
                <FactChecker />
              </ProtectedRoute>
            }
          />

          {/* ---------- Educator only ---------- */}
          <Route
            path="/dashboard"
            element={
              <ProtectedRoute>
                <EducatorRoute>
                  <EducatorDashboard />
                </EducatorRoute>
              </ProtectedRoute>
            }
          />
          <Route path="/403" element={<AccessDenied />} />

          {/* ---------- Fallback ---------- */}
          <Route path="*" element={<NotFound />} />
        </Routes>
      </main>

      <footer className="relative z-10 border-t border-navy-border/60 mt-10 backdrop-blur-sm bg-navy/40">
        <div className="max-w-6xl mx-auto px-4 py-5 text-xs text-ink-muted flex flex-wrap gap-2 justify-between">
          <span>
            TruthGuard AI · Software Engineering project · UN SDG 4 (Quality Education) &amp; SDG 16
            (Peace, Justice &amp; Strong Institutions)
          </span>
          <span className="text-ink-muted/70">AI verdicts are probabilistic — always verify with primary sources.</span>
        </div>
      </footer>
    </div>
  )
}
