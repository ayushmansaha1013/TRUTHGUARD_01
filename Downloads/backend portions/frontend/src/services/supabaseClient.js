import { createClient } from '@supabase/supabase-js'

/**
 * ---------------------------------------------------------------------------
 * Supabase client (PostgreSQL + Auth) — Part B.3
 * ---------------------------------------------------------------------------
 * SECURITY (Part C.4 — Secure Environment Variables):
 *   Credentials come from VITE_-prefixed env vars, never hardcoded.
 *   The ANON key is intentionally public: it identifies the project, it does not
 *   authorise data access. Authorisation is enforced by Row Level Security
 *   policies in Postgres (see ../supabase/schema.sql). That is why an anon key
 *   in a browser bundle is safe while a `service_role` key never would be.
 *
 * SECURITY (Part B.3 — "don't manually store tokens in localStorage"):
 *   We use Supabase's built-in session manager. The JWT lives in the
 *   `sb-<project-ref>-auth-token` storage entry, is refreshed automatically
 *   before it expires, and we NEVER copy it into our own localStorage keys,
 *   cookies, or component state. Fewer copies of a bearer token = fewer places
 *   for it to leak (XSS, shared machines, accidental git commits).
 *
 * persistSession : keep the user logged in across refreshes (managed by Supabase)
 * autoRefreshToken: silently renew the JWT before expiry (~1h default)
 * detectSessionInUrl: handle the OAuth / "confirm your email" magic link redirect
 */
// RUNTIME CONFIG, then BUILD-TIME ENV.
// WHY: Vite substitutes VITE_* values when the bundle is built, so a prebuilt
// folder uploaded to a static host (Netlify Drop) is frozen to whatever the
// environment said on the build machine — including, typically, nothing at all.
// public/config.js is fetched by the browser at runtime, so the same dist/ can be
// pointed at any Supabase project by editing three lines in one file. Build-time
// values still work and still take second place.
// Both of these are PUBLIC by design: the URL identifies the project, and the
// anon key is the deliberately-limited client key. RLS, not secrecy, is what
// protects the data — which is exactly why these two are safe here but a
// service_role key would never be.
const runtime = (typeof window !== 'undefined' && window.__TRUTHGUARD__) || {}

const supabaseUrl = runtime.supabaseUrl || import.meta.env.VITE_SUPABASE_URL
const supabaseAnonKey = runtime.supabaseAnonKey || import.meta.env.VITE_SUPABASE_ANON_KEY

export const DEMO_MODE =
  String(runtime.demoMode ?? import.meta.env.VITE_DEMO_MODE ?? 'false') === 'true'

export const supabaseReady = Boolean(supabaseUrl && supabaseAnonKey && !DEMO_MODE)

if (!supabaseReady && !DEMO_MODE) {
  // Fail loudly during development instead of silently rendering a broken app.
  // eslint-disable-next-line no-console
  console.error(
    '[TruthGuard] Supabase is not configured.\n' +
      '  On a static host (Netlify Drop): set supabaseUrl + supabaseAnonKey in /config.js.\n' +
      '  Locally or on a Git-connected host: set VITE_SUPABASE_URL + VITE_SUPABASE_ANON_KEY\n' +
      '  in frontend/.env and rebuild. Set demoMode: true in config.js for a no-auth demo.',
  )
}

/**
 * In DEMO_MODE (no Supabase project yet) we return a stub that mimics the tiny
 * slice of the supabase-js API the app uses. Everything else — UI, routing,
 * RBAC guards — behaves identically, so the demo still shows the full product.
 * The stub is clearly marked; it is removed automatically once real env vars
 * are supplied.
 */
function createDemoStub() {
  const memory = { user: null, profile: null, logs: [] }
  const emptyChain = {
    select: () => emptyChain,
    eq: () => emptyChain,
    gte: () => emptyChain,
    order: () => emptyChain,
    limit: () => emptyChain,
    single: async () => ({ data: memory.profile, error: null }),
    maybeSingle: async () => ({ data: memory.profile, error: null }),
    insert: async (row) => {
      memory.logs.unshift({ ...row, id: memory.logs.length + 1, user_email: 'demo@truthguard.ai' })
      return { data: row, error: null }
    },
    then: async () => ({ data: memory.logs, error: null }),
  }
  return {
    __demo: true,
    auth: {
      getSession: async () => ({ data: { session: null }, error: null }),
      getUser: async () => ({ data: { user: null }, error: null }),
      onAuthStateChange: (cb) => {
        cb('SIGNED_IN', { user: { id: 'demo-user', email: 'demo@truthguard.ai' } })
        return { data: { subscription: { unsubscribe() {} } } }
      },
      signInWithPassword: async () => ({ data: { user: null, session: null }, error: null }),
      signUp: async () => ({ data: { user: null, session: null }, error: null }),
      signOut: async () => ({ error: null }),
    },
    from: () => emptyChain,
    rpc: async () => ({ data: true, error: null }),
  }
}

export const supabase = supabaseReady
  ? createClient(supabaseUrl, supabaseAnonKey, {
      auth: {
        persistSession: true,
        autoRefreshToken: true,
        detectSessionInUrl: true,
        storageKey: 'truthguard-auth-token', // namespaced so it can't collide with other apps on the origin
      },
      global: {
        headers: {
          // Helps attribute traffic in Supabase logs; harmless and non-secret.
          'X-Client-Info': 'truthguard-ai-frontend/1.0.0',
        },
      },
    })
  : createDemoStub()

export default supabase
