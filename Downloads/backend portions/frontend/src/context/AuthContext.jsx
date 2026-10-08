import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { supabase, DEMO_MODE, supabaseReady } from '../services/supabaseClient.js'

/**
 * ---------------------------------------------------------------------------
 * AuthContext — single source of truth for "who is logged in and what is their role"
 * ---------------------------------------------------------------------------
 * Part B.3 (Authentication Flow) + Part B.4 (Protected Routes).
 *
 * SECURITY NOTES:
 *  - We subscribe to Supabase's onAuthStateChange instead of polling, so token
 *    refresh, sign-in and sign-out all update the UI automatically.
 *  - The ROLE is read from the `profiles` table (server-side truth), never from
 *    localStorage or from anything the user can edit in DevTools. Reading it
 *    from the DB means a user cannot promote themselves to "educator" by
 *    tampering with browser state: the RLS policy for profiles only allows
 *    updating your own row, and role changes are additionally guarded by a
 *    trigger on the DB side.
 *  - We keep NO tokens in this context. Only identity metadata. The JWT stays
 *    inside supabase-js' managed session storage.
 */

const AuthContext = createContext(null)

const DEMO_PROFILE = {
  id: 'demo-user',
  email: 'demo@truthguard.ai',
  role: 'educator', // demo mode shows every screen, including the dashboard
  created_at: new Date().toISOString(),
}

export function AuthProvider({ children }) {
  const [session, setSession] = useState(null)
  const [profile, setProfile] = useState(null)
  const [loading, setLoading] = useState(true)

  const user = session?.user ?? null

  /** Load (or reload) the profile row that carries the RBAC role. */
  const loadProfile = useCallback(async (uid) => {
    if (!uid) {
      setProfile(null)
      return null
    }
    try {
      const { data, error } = await supabase.from('profiles').select('*').eq('id', uid).maybeSingle()
      if (error) {
        // eslint-disable-next-line no-console
        console.warn('[TruthGuard] could not load profile:', error.message)
        // Fall back to a least-privilege profile: treat unknown users as students.
        // SECURITY: fail CLOSED. If we can't prove you're an educator, you aren't one.
        setProfile({ id: uid, role: 'student', email: null })
        return null
      }
      setProfile(data ?? { id: uid, role: 'student', email: null })
      return data
    } catch (err) {
      // eslint-disable-next-line no-console
      console.warn('[TruthGuard] profile load threw:', err?.message)
      setProfile({ id: uid, role: 'student', email: null })
      return null
    }
  }, [])

  /* ---------------- bootstrap + live session subscription ---------------- */
  useEffect(() => {
    if (DEMO_MODE || !supabaseReady) {
      setSession({ user: { id: DEMO_PROFILE.id, email: DEMO_PROFILE.email } })
      setProfile(DEMO_PROFILE)
      setLoading(false)
      return undefined
    }

    let mounted = true

    ;(async () => {
      const { data } = await supabase.auth.getSession()
      if (!mounted) return
      const current = data?.session ?? null
      setSession(current)
      if (current?.user?.id) await loadProfile(current.user.id)
      setLoading(false)
    })()

    const { data: sub } = supabase.auth.onAuthStateChange(async (_event, newSession) => {
      if (!mounted) return
      setSession(newSession)
      if (newSession?.user?.id) {
        await loadProfile(newSession.user.id)
      } else {
        setProfile(null)
      }
      setLoading(false)
    })

    return () => {
      mounted = false
      sub?.subscription?.unsubscribe?.()
    }
  }, [loadProfile])

  /* ------------------------------- actions ------------------------------- */

  const signIn = useCallback(async (email, password) => {
    const { data, error } = await supabase.auth.signInWithPassword({
      email: String(email).trim().toLowerCase(),
      password,
    })
    if (error) throw error
    if (data?.user?.id) await loadProfile(data.user.id)
    return data
  }, [loadProfile])

  /**
   * Sign up + persist the chosen role.
   *
   * Two-step on purpose:
   *  1) supabase.auth.signUp(...) fires the DB trigger `handle_new_user()`,
   *     which inserts the `profiles` row (default role 'student').
   *  2) We then call the SECURITY DEFINER function `set_my_role(p_role)` to
   *     record 'educator' if that's what the user picked.
   *
   * WHY A DB FUNCTION INSTEAD OF A PLAIN UPDATE?
   *  If "Confirm email" is ON in Supabase, signUp() returns no session, so the
   *  caller has no JWT and the RLS policy on profiles would (correctly) reject
   *  the update — leaving every educator stuck as a student until they log in
   *  again. `set_my_role` runs with definer rights but is constrained to
   *  `WHERE id = auth.uid()` and may only be used once (role_locked = false),
   *  so it cannot be abused for privilege escalation.
   */
  const signUp = useCallback(async (email, password, role = 'student') => {
    const cleanEmail = String(email).trim().toLowerCase()
    const safeRole = role === 'educator' ? 'educator' : 'student' // never trust the client value

    const { data, error } = await supabase.auth.signUp({
      email: cleanEmail,
      password,
      options: {
        // Stored in the raw user meta; the trigger can read it as a fallback.
        data: { role: safeRole },
        emailRedirectTo: typeof window !== 'undefined' ? `${window.location.origin}/login` : undefined,
      },
    })
    if (error) throw error

    if (data?.session) {
      setSession(data.session)
      // Prefer the constrained function; fall back to a direct update.
      const { error: rpcErr } = await supabase.rpc('set_my_role', { p_role: safeRole })
      if (rpcErr) {
        await supabase.from('profiles').update({ role: safeRole }).eq('id', data.session.user.id)
      }
      await loadProfile(data.session.user.id)
    } else {
      // Email confirmation required: tell the caller so the UI can show the
      // "check your inbox" screen instead of silently doing nothing.
      return { ...data, needsEmailConfirmation: true }
    }
    return { ...data, needsEmailConfirmation: false }
  }, [loadProfile])

  const signOut = useCallback(async () => {
    // `global` scope revokes the refresh token server-side too, so a stolen
    // session cannot be revived after logout.
    const { error } = await supabase.auth.signOut({ scope: 'global' })
    setSession(null)
    setProfile(null)
    if (error) throw error
  }, [])

  const refreshProfile = useCallback(async () => {
    if (user?.id) await loadProfile(user.id)
  }, [user?.id, loadProfile])

  /* ------------------------------ derived ------------------------------ */
  const role = profile?.role ?? null
  const value = useMemo(
    () => ({
      session,
      user,
      profile,
      role,
      isAuthenticated: Boolean(user),
      isEducator: role === 'educator',
      isStudent: role === 'student',
      loading,
      demoMode: DEMO_MODE || !supabaseReady,
      signIn,
      signUp,
      signOut,
      refreshProfile,
    }),
    [session, user, profile, role, loading, signIn, signUp, signOut, refreshProfile],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth() must be used inside <AuthProvider>')
  return ctx
}

export default AuthContext
