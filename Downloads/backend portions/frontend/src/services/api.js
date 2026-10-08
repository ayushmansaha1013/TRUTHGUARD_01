import { supabase, DEMO_MODE } from './supabaseClient.js'
import { ApiError, toApiError } from '../utils/errors.js'

/**
 * ---------------------------------------------------------------------------
 * api.js — the ONLY place that talks to the FastAPI backend
 * ---------------------------------------------------------------------------
 * Every AI call in the app goes through this module. That gives us one spot to:
 *   1. attach the Supabase JWT  (Part C.1 — JWT middleware, client half)
 *   2. apply a timeout + abort  (no hung spinners on cold-starting models)
 *   3. normalise errors         (429 / 502 / 503 / 504 -> friendly messages)
 *   4. enforce client-side rate-limit cooldown after a 429 (Part C.3)
 */

// RUNTIME CONFIG, then BUILD-TIME ENV.
// WHY both, and why runtime wins: Vite substitutes VITE_* values when the bundle
// is built, so a prebuilt `dist/` is frozen to whatever the environment said that
// day — and a static host with no build step (Netlify Drop and friends) gives you
// nowhere to change it afterwards. `public/config.js` is fetched by the browser at
// runtime, so it can be edited and re-uploaded in seconds without a rebuild.
// Build-time stays supported as the normal path for Git-connected hosts.
// The `typeof window` guard keeps this file importable in a non-browser test runner.
const RUNTIME_BASE =
  typeof window !== 'undefined' &&
  window.__TRUTHGUARD__ &&
  typeof window.__TRUTHGUARD__.apiBaseUrl === 'string'
    ? window.__TRUTHGUARD__.apiBaseUrl
    : ''

const API_BASE = (RUNTIME_BASE || import.meta.env.VITE_API_BASE_URL || '').replace(/\/+$/, '')

// DEV-ONLY escape hatch from CORS.
// WHY: the normal setup is VITE_API_BASE_URL=https://<your-render-app>.onrender.com
// plus a matching FRONTEND_ORIGIN on the backend. That is correct for production
// and is what you should demo. But while developing locally the browser sees two
// different origins (5173 and 8000), so every call needs a CORS preflight — and
// if FRONTEND_ORIGIN is misconfigured you get a wall of opaque browser errors.
// Setting VITE_USE_DEV_PROXY=true makes the app call SAME-ORIGIN paths instead,
// which Vite's dev server forwards to the backend (see vite.config.js `proxy`).
// Same-origin means no preflight and no CORS at all.
// WHY opt-in and not "empty URL means relative": an empty URL is far more often a
// forgotten configuration than a deliberate proxy setup, and failing loudly there
// has already saved debugging time. api.test.js pins that behaviour.
const USE_DEV_PROXY = String(import.meta.env.VITE_USE_DEV_PROXY || '').toLowerCase() === 'true'
const COOLDOWN_SECONDS = Number(import.meta.env.VITE_RATE_LIMIT_COOLDOWN_SECONDS || 10)
const REQUEST_TIMEOUT_MS = 60_000 // models can cold-start; generous but bounded
const HEALTH_TIMEOUT_MS = 8_000

if (!API_BASE && !USE_DEV_PROXY) {
  // eslint-disable-next-line no-console
  console.warn(
    '[TruthGuard] No backend URL configured — AI calls will fail.\n' +
      '  Fix on a static host (Netlify Drop): set apiBaseUrl in /config.js and re-upload.\n' +
      '  Fix locally or on a Git-connected host: set VITE_API_BASE_URL in frontend/.env, then rebuild.',
  )
} else if (USE_DEV_PROXY) {
  // eslint-disable-next-line no-console
  console.info('[TruthGuard] dev proxy mode: calling same-origin /api/* (Vite forwards to the backend)')
}

/* ------------------------------------------------------------------ *
 * Client-side cooldown state (Part C.3 — Rate Limiting Awareness)
 *
 * WHY: when the backend replies 429, the correct user behaviour is "wait".
 * Locking the submit button for N seconds makes that automatic, prevents an
 * anxious user from hammering a GPU-backed service into a longer ban, and is
 * trivial to demonstrate. It is a courtesy control only — real rate limiting
 * still has to happen server-side, because a browser timer can be bypassed.
 * ------------------------------------------------------------------ */
let cooldownUntil = 0
const cooldownListeners = new Set()

function setCooldown(seconds = COOLDOWN_SECONDS) {
  cooldownUntil = Date.now() + seconds * 1000
  cooldownListeners.forEach((fn) => fn(cooldownUntil))
}
function clearCooldownIfExpired() {
  if (cooldownUntil && Date.now() >= cooldownUntil) {
    cooldownUntil = 0
    cooldownListeners.forEach((fn) => fn(0))
  }
}

/** Subscribe to cooldown changes (used by useRateLimitCooldown hook). */
export function onCooldownChange(fn) {
  cooldownListeners.add(fn)
  fn(cooldownUntil)
  return () => cooldownListeners.delete(fn)
}

/** Milliseconds of cooldown remaining (0 = free to submit). */
export function getCooldownRemainingMs() {
  clearCooldownIfExpired()
  return Math.max(0, cooldownUntil - Date.now())
}

/* ------------------------------------------------------------------ *
 * JWT acquisition (Part C.1)
 * ------------------------------------------------------------------ */

/**
 * Fetch a FRESH access token for every request instead of caching one.
 * WHY: Supabase access tokens are short-lived (~1 hour) and are rotated by the
 * built-in refresh mechanism. Reading `getSession()` each time means we always
 * send a currently-valid JWT and never a stale one — and we never keep our own
 * copy of the token in module state or localStorage (fewer leak surfaces).
 */
export async function getAccessToken() {
  if (DEMO_MODE || supabase.__demo) return null
  const { data, error } = await supabase.auth.getSession()
  if (error) throw new ApiError('Could not read your session. Please sign in again.', { status: 401, code: 'session_error' })
  return data?.session?.access_token ?? null
}

/* ------------------------------------------------------------------ *
 * Core request helper
 * ------------------------------------------------------------------ */

async function request(path, { method = 'GET', body, headers = {}, timeoutMs = REQUEST_TIMEOUT_MS } = {}) {
  if (!API_BASE && !USE_DEV_PROXY) {
    throw new ApiError(
      'Backend URL is not configured. Set apiBaseUrl in config.js (static hosting) ' +
        'or VITE_API_BASE_URL in frontend/.env (then rebuild).',
      { status: 0, code: 'not_configured' },
    )
  }

  // Respect an active 429 cooldown before spending a request.
  const remaining = getCooldownRemainingMs()
  if (remaining > 0 && method !== 'GET') {
    throw new ApiError(`Please wait ${Math.ceil(remaining / 1000)}s before trying again.`, {
      status: 429,
      code: 'client_cooldown',
      retryable: true,
    })
  }

  // AbortController: cancel the request if it exceeds the timeout so the UI
  // never hangs on a spinner forever (common with sleeping HF Spaces).
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)

  try {
    const token = await getAccessToken()

    const finalHeaders = {
      // SECURITY (Part C.1): the FastAPI middleware verifies this exact header.
      // Without it the backend returns 401 and refuses to burn GPU time on an
      // anonymous caller. `Bearer` + the Supabase-issued JWT is proof that the
      // request came from an authenticated TruthGuard user.
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      // We intentionally DO NOT set Content-Type for multipart/form-data:
      // fetch must generate the boundary itself (e.g. ----WebKitFormBoundaryXyz).
      // Setting it manually corrupts the body and yields a 422.
      ...(body instanceof FormData ? {} : body ? { 'Content-Type': 'application/json' } : {}),
      ...headers,
    }

    const res = await fetch(`${API_BASE}${path}`, {
      method,
      headers: finalHeaders,
      body,
      signal: controller.signal,
      // SECURITY: default is already 'same-origin'; being explicit documents
      // that we never send cookies/credentials to the third-party AI host.
      credentials: 'omit',
    })

    if (!res.ok) {
      const apiError = await toApiError(res)
      // 429 -> start the client-side cooldown.
      if (apiError.status === 429) setCooldown(COOLDOWN_SECONDS)
      throw apiError
    }

    const text = await res.text()
    try {
      return text ? JSON.parse(text) : {}
    } catch {
      throw new ApiError('The AI service returned an unreadable response.', {
        status: 502,
        code: 'bad_json',
        retryable: true,
      })
    }
  } catch (err) {
    if (err instanceof ApiError) throw err
    if (err?.name === 'AbortError') {
      throw new ApiError('The analysis took too long and was cancelled. The model may be cold-starting — please retry.', {
        status: 504,
        code: 'client_timeout',
        retryable: true,
      })
    }
    throw await toApiError(err)
  } finally {
    clearTimeout(timer)
  }
}

/* ------------------------------------------------------------------ *
 * Public API surface — matches the deployed FastAPI contract exactly
 * ------------------------------------------------------------------ */

/**
 * POST /api/v1/detect-image
 * @param {File} file  image file (already validated client-side)
 * @returns {Promise<{verdict:string, confidence:number, raw_label:string,
 *                    fake_probability:number, is_fake:boolean, analyzed_in_ms:number}>}
 */
export async function detectImage(file) {
  const form = new FormData()
  form.append('file', file, file.name) // field name MUST be "file"
  return request('/api/v1/detect-image', { method: 'POST', body: form })
}

/**
 * POST /api/v1/fact-check
 * @param {string} claim  10–1000 characters
 * @returns {Promise<{verdict:string, explanation:string, sources:string[],
 *                    retrieved_context:any[], checked_in_ms:number}>}
 */
export async function factCheck(claim) {
  return request('/api/v1/fact-check', {
    method: 'POST',
    body: JSON.stringify({ claim }),
  })
}

/** GET /health — used by the landing page status pill. */
export async function getHealth() {
  return request('/health', { method: 'GET', timeoutMs: HEALTH_TIMEOUT_MS })
}

export { COOLDOWN_SECONDS }
