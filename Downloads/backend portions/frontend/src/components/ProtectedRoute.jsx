import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from '../context/AuthContext.jsx'

/**
 * ---------------------------------------------------------------------------
 * ProtectedRoute — Part B.4 (layer 1 of the 3-layer RBAC model)
 * ---------------------------------------------------------------------------
 * Blocks every route that requires an authenticated Supabase session.
 *
 * HOW IT WORKS:
 *   - No session  -> <Navigate to="/login"> with the original path saved in
 *                    `state.from`, so after a successful sign-in the user lands
 *                    back where they were trying to go (nice UX, and it proves
 *                    the guard actually intercepted the request).
 *   - Session     -> render children.
 *
 * SECURITY — READ THIS FOR THE REPORT:
 *   This is an *access-control UX* layer only. A React route guard runs in the
 *   browser and can be bypassed in seconds (curl, Postman, DevTools). It exists
 *   so honest users never see a half-rendered authenticated page. The real
 *   boundary is:
 *     layer 2 — Supabase RLS policies (the DB refuses rows you may not see), and
 *     layer 3 — the FastAPI JWT middleware (the AI refuses unauthenticated calls).
 *   Also note we fail CLOSED: `loading` is handled by App.jsx, and if the auth
 *   state is somehow undefined we redirect rather than render.
 */
export default function ProtectedRoute({ children }) {
  const { isAuthenticated, loading } = useAuth()
  const location = useLocation()

  if (loading) return null // App.jsx already shows a full-page loader

  if (!isAuthenticated) {
    return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />
  }

  return children
}
