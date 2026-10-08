import { Navigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext.jsx'

/**
 * ---------------------------------------------------------------------------
 * EducatorRoute — Part B.4 (role-based route protection)
 * ---------------------------------------------------------------------------
 * Wraps the Educator Dashboard. Renders it only when the *server-side* profile
 * row says role = 'educator'; otherwise redirects to a 403 Access Denied page.
 *
 * WHY THE ROLE COMES FROM `profiles`, NOT FROM THE CLIENT:
 *   `useAuth().role` is populated by a SELECT on the profiles table using the
 *   user's own JWT. A student cannot change that value without a DB write, and
 *   the profiles RLS policy allows updating your own row — which is why the
 *   database also carries a trigger (`enforce_role_immutable`) that ignores any
 *   client-side attempt to change `role` after signup. Role assignment is
 *   therefore effectively write-once from the browser.
 *
 * WHY A 403 PAGE INSTEAD OF A SILENT REDIRECT:
 *   Explicit denial is better security hygiene than pretending the feature does
 *   not exist — the user learns their account type is wrong, and the attempt is
 *   visible/auditable rather than mysterious. (Note: we do NOT leak *why* beyond
 *   the role requirement, and we never render another user's data on this page.)
 *
 * DEFENCE IN DEPTH: even if this component were deleted, the dashboard's data
 * query would return zero rows for a student because of the RLS policy
 * `educators_select_all_scan_logs`. Layer 1 failing must never expose data.
 */
export default function EducatorRoute({ children }) {
  const { isEducator, loading } = useAuth()

  if (loading) return null

  if (!isEducator) {
    return <Navigate to="/403" replace state={{ tried: 'Educator Dashboard' }} />
  }

  return children
}
