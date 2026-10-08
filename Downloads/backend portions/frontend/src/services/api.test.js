import { beforeEach, describe, expect, it, vi } from 'vitest'

/**
 * ---------------------------------------------------------------------------
 * api.js tests — Part C.1 (JWT), C.2 (transport correctness), C.3 (rate limit),
 *                and the friendly error mapping for 4xx/5xx responses.
 * ---------------------------------------------------------------------------
 * Each test re-imports api.js with a fresh module registry so the module-level
 * cooldown state cannot leak between tests.
 */

const TEST_TOKEN = 'eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ0ZXN0LXVzZXIifQ.signature-part'
const BASE = 'https://test-backend.example'

function mockSupabase(token = TEST_TOKEN) {
  // `token` may be a string (fixed) or a function (e.g. one that rotates the
  // access token on every read, the way Supabase does after a refresh).
  vi.doMock('./supabaseClient.js', () => ({
    DEMO_MODE: false,
    supabaseReady: true,
    supabase: {
      auth: {
        getSession: vi.fn(async () => {
          const value = typeof token === 'function' ? token() : token
          return {
            data: { session: value ? { access_token: value } : null },
            error: null,
          }
        }),
      },
    },
  }))
}

function mockFetch(responder) {
  const calls = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url, options) => {
      calls.push({ url, options })
      // `responder` is normally a factory from json()/raw(); calling it per
      // request guarantees a fresh, unconsumed Response every time.
      return typeof responder === 'function' ? responder(url, options) : responder
    }),
  )
  return calls
}

async function loadApi(env = {}) {
  vi.resetModules()
  vi.stubEnv('VITE_API_BASE_URL', BASE)
  vi.stubEnv('VITE_DEMO_MODE', 'false')
  vi.stubEnv('VITE_RATE_LIMIT_COOLDOWN_SECONDS', String(env.cooldown ?? 1))
  mockSupabase(env.token === undefined ? TEST_TOKEN : env.token)
  const api = await import('./api.js')
  return api
}

/**
 * Build a mock-response FACTORY.
 * A Response body can only be consumed once, so a test that makes two calls must
 * get two distinct Response objects — returning the same instance would make the
 * second `res.text()` throw. Every helper below therefore returns a factory that
 * mockFetch() invokes per request.
 */
const json = (body, status = 200) => () =>
  new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })

const raw = (text, status = 200) => () => new Response(text, { status })

const networkFailure = () => () => {
  throw new TypeError('Failed to fetch')
}

const png = () => new File([new Uint8Array([0x89, 0x50, 0x4e, 0x47, 1, 2, 3])], 'photo.png', {
  type: 'image/png',
})

beforeEach(() => {
  vi.unstubAllGlobals()
  vi.unstubAllEnvs()
  vi.resetModules()
})

/* ============================== Part C.1 — JWT ============================== */
describe('JWT attachment (Part C.1)', () => {
  it('sends Authorization: Bearer <supabase jwt> on POST /api/v1/detect-image', async () => {
    const calls = mockFetch(json({ verdict: 'Likely Fake', confidence: 94.2 }))
    const api = await loadApi()

    const result = await api.detectImage(png())

    expect(calls).toHaveLength(1)
    expect(calls[0].url).toBe(`${BASE}/api/v1/detect-image`)
    expect(calls[0].options.method).toBe('POST')
    expect(calls[0].options.headers.Authorization).toBe(`Bearer ${TEST_TOKEN}`)
    expect(result.verdict).toBe('Likely Fake')
  })

  it('sends the JWT on POST /api/v1/fact-check too', async () => {
    const calls = mockFetch(json({ verdict: 'True', explanation: 'x', sources: [] }))
    const api = await loadApi()

    await api.factCheck('A claim long enough to be valid.')

    expect(calls[0].options.headers.Authorization).toBe(`Bearer ${TEST_TOKEN}`)
    expect(JSON.parse(calls[0].options.body)).toEqual({ claim: 'A claim long enough to be valid.' })
    expect(calls[0].options.headers['Content-Type']).toBe('application/json')
  })

  it('reads a FRESH token per request rather than caching one (no stale JWTs)', async () => {
    // Simulate Supabase rotating the access token between requests (it refreshes
    // sessions automatically). api.js must pick up the new value every time
    // instead of caching the token it saw first.
    let issued = 0
    const calls = mockFetch(json({ verdict: 'True' }))
    const api = await loadApi({ token: () => `rotated-token-${++issued}` })

    await api.factCheck('First claim that is long enough.')
    await api.factCheck('Second claim that is long enough.')

    expect(calls).toHaveLength(2)
    expect(calls[0].options.headers.Authorization).toBe('Bearer rotated-token-1')
    expect(calls[1].options.headers.Authorization).toBe('Bearer rotated-token-2')
  })

  it('omits the header entirely when there is no session (instead of sending "Bearer undefined")', async () => {
    const calls = mockFetch(json({ verdict: 'True' }))
    const api = await loadApi({ token: null })

    await api.factCheck('A claim long enough to be valid.')

    expect(calls[0].options.headers.Authorization).toBeUndefined()
  })

  it('never sends cookies to the third-party AI host', async () => {
    const calls = mockFetch(json({ verdict: 'True' }))
    const api = await loadApi()

    await api.factCheck('A claim long enough to be valid.')

    expect(calls[0].options.credentials).toBe('omit')
  })
})

/* ============================ Part C.2 — transport =========================== */
describe('multipart correctness (Part C.2)', () => {
  it('posts FormData with the field name "file" and does NOT set Content-Type manually', async () => {
    const calls = mockFetch(json({ verdict: 'Likely Real' }))
    const api = await loadApi()

    await api.detectImage(png())

    const body = calls[0].options.body
    expect(body).toBeInstanceOf(FormData)
    expect(body.has('file')).toBe(true)
    // Critical: fetch must generate the multipart boundary itself. A manually
    // set Content-Type corrupts the body and the backend replies 422.
    expect(calls[0].options.headers['Content-Type']).toBeUndefined()
  })

  it('attaches an AbortController so a hung model cannot spin forever', async () => {
    const calls = mockFetch(json({ verdict: 'Likely Real' }))
    const api = await loadApi()

    await api.detectImage(png())

    expect(calls[0].options.signal).toBeInstanceOf(AbortSignal)
  })
})

/* ========================= friendly error mapping =========================== */
describe('error mapping — users never see a raw status code', () => {
  const cases = [
    [413, /too large/i],
    [422, /could not understand/i],
    [429, /wait a moment/i],
    [502, /starting up|unreachable/i],
    [503, /temporarily unavailable|overloaded/i],
    [504, /timed out/i],
  ]

  it.each(cases)('maps HTTP %i to a friendly, actionable message', async (status, pattern) => {
    mockFetch(json({ detail: '', error_code: 'x' }, status))
    const api = await loadApi()

    // One single call: assert the ApiError carries the status AND the mapped,
    // human-readable message instead of a raw code or stack trace.
    let caught = null
    try {
      await api.factCheck('A claim long enough to be valid.')
    } catch (err) {
      caught = err
    }
    expect(caught).not.toBeNull()
    expect(caught.name).toBe('ApiError')
    expect(caught.status).toBe(status)
    expect(caught.message).toMatch(pattern)
  })

  it('surfaces the backend `detail` when it is present and reasonable', async () => {
    mockFetch(json({ detail: 'Image exceeds the 8 MB limit.', error_code: 'payload_too_large' }, 413))
    const api = await loadApi()

    await expect(api.factCheck('A claim long enough to be valid.')).rejects.toMatchObject({
      message: 'Image exceeds the 8 MB limit.',
      code: 'payload_too_large',
      status: 413,
    })
  })

  it('flattens FastAPI 422 validation arrays into one readable sentence', async () => {
    mockFetch(
      json({ detail: [{ msg: 'String should have at least 10 characters' }] }, 422),
    )
    const api = await loadApi()

    await expect(api.factCheck('short')).rejects.toMatchObject({
      message: 'String should have at least 10 characters',
    })
  })

  it('handles a non-JSON error body (HTML proxy page) without crashing', async () => {
    mockFetch(raw('<html>502 Bad Gateway</html>', 502))
    const api = await loadApi()

    await expect(api.factCheck('A claim long enough to be valid.')).rejects.toMatchObject({
      status: 502,
    })
  })

  it('converts a network failure into a retryable, human message', async () => {
    mockFetch(networkFailure())
    const api = await loadApi()

    await expect(api.factCheck('A claim long enough to be valid.')).rejects.toMatchObject({
      status: 0,
      code: 'network_error',
      retryable: true,
    })
  })

  it('fails with a clear message when the backend URL is not configured', async () => {
    vi.resetModules()
    vi.stubEnv('VITE_API_BASE_URL', '')
    vi.stubEnv('VITE_DEMO_MODE', 'false')
    // WHY stub this too: VITE_USE_DEV_PROXY is a local-development flag that
    // makes the app call same-origin /api/* paths, deliberately bypassing the
    // "nothing configured" guard. Vitest loads the developer's real .env, so
    // without this stub the test silently passed or failed depending on whose
    // machine it ran on. Pinning it here makes the test mean what it says.
    vi.stubEnv('VITE_USE_DEV_PROXY', 'false')
    mockSupabase()
    mockFetch(json({}))
    const api = await import('./api.js')

    // The message must name BOTH ways to fix it: the runtime config file (for
    // static hosts with no build step) and the build-time env var. A diagnosis
    // without a fix is what made this error costly to act on in the first place.
    await expect(api.factCheck('A claim long enough to be valid.')).rejects.toMatchObject({
      code: 'not_configured',
      message: expect.stringContaining('config.js'),
    })
  })

  it('prefers the RUNTIME config over the build-time env var', async () => {
    // WHY this matters: a prebuilt `dist/` uploaded to a static host (Netlify
    // Drop) has the build-time value frozen into it. `public/config.js` is read
    // at runtime specifically so that bundle can still be re-pointed at a real
    // backend without a rebuild. If build-time ever won, that escape hatch would
    // be silently useless.
    vi.resetModules()
    vi.stubEnv('VITE_API_BASE_URL', 'https://baked-in-at-build-time.example')
    vi.stubEnv('VITE_DEMO_MODE', 'false')
    mockSupabase()
    const fetchMock = mockFetch(json({ verdict: 'True', explanation: 'x', sources: [] }))
    window.__TRUTHGUARD__ = { apiBaseUrl: 'https://runtime-config.example' }

    try {
      vi.stubEnv('VITE_USE_DEV_PROXY', 'false')
      const api = await import('./api.js')
      await api.factCheck('A claim long enough to be valid.')
      expect(fetchMock[0].url).toContain('https://runtime-config.example')
      expect(fetchMock[0].url).not.toContain('baked-in-at-build-time')
    } finally {
      delete window.__TRUTHGUARD__
    }
  })

  it('ignores an empty runtime config and falls back to the env var', async () => {
    // config.js ships with apiBaseUrl: '' so that a Git-connected host building
    // with a proper .env behaves exactly as before. An empty string must NOT be
    // treated as "configured but empty" and blank out a working build.
    vi.resetModules()
    vi.stubEnv('VITE_API_BASE_URL', 'https://from-env-var.example')
    vi.stubEnv('VITE_DEMO_MODE', 'false')
    mockSupabase()
    const fetchMock = mockFetch(json({ verdict: 'True', explanation: 'x', sources: [] }))
    window.__TRUTHGUARD__ = { apiBaseUrl: '' }

    try {
      vi.stubEnv('VITE_USE_DEV_PROXY', 'false')
      const api = await import('./api.js')
      await api.factCheck('A claim long enough to be valid.')
      expect(fetchMock[0].url).toContain('https://from-env-var.example')
    } finally {
      delete window.__TRUTHGUARD__
    }
  })
})

/* ========================= Part C.3 — rate limiting ========================== */
describe('429 handling and client-side cooldown (Part C.3)', () => {
  it('starts a cooldown after a 429 and blocks the next call WITHOUT hitting the network', async () => {
    const calls = mockFetch(json({ detail: 'Rate limit exceeded', error_code: 'rate_limited' }, 429))
    const api = await loadApi({ cooldown: 2 })

    // First call reaches the server and is rate limited.
    await expect(api.factCheck('A claim long enough to be valid.')).rejects.toMatchObject({ status: 429 })
    expect(calls).toHaveLength(1)
    expect(api.getCooldownRemainingMs()).toBeGreaterThan(0)

    // Subsequent calls are refused locally — no request is sent at all.
    await expect(api.factCheck('A claim long enough to be valid.')).rejects.toMatchObject({
      status: 429,
      code: 'client_cooldown',
    })
    expect(calls).toHaveLength(1)
  })

  it('exposes a live countdown for the disabled-button UI', async () => {
    mockFetch(json({ detail: 'slow down', error_code: 'rate_limited' }, 429))
    const api = await loadApi({ cooldown: 3 })

    await expect(api.factCheck('A claim long enough to be valid.')).rejects.toBeTruthy()

    const ms = api.getCooldownRemainingMs()
    expect(ms).toBeGreaterThan(2000)
    expect(ms).toBeLessThanOrEqual(3000)
  })

  it('notifies subscribers so React can re-render the countdown', async () => {
    mockFetch(json({ detail: 'slow down', error_code: 'rate_limited' }, 429))
    const api = await loadApi({ cooldown: 2 })

    const seen = []
    const unsubscribe = api.onCooldownChange((until) => seen.push(until))

    await expect(api.factCheck('A claim long enough to be valid.')).rejects.toBeTruthy()

    expect(seen.length).toBeGreaterThanOrEqual(2) // initial value + the change
    expect(seen[seen.length - 1]).toBeGreaterThan(Date.now())
    unsubscribe()
  })

  it('expires the cooldown so the user is not locked out permanently', async () => {
    mockFetch(json({ detail: 'slow down', error_code: 'rate_limited' }, 429))
    const api = await loadApi({ cooldown: 0 }) // 0s -> expires immediately

    await expect(api.factCheck('A claim long enough to be valid.')).rejects.toMatchObject({ status: 429 })
    expect(api.getCooldownRemainingMs()).toBe(0)
  })

  it('does not start a cooldown for unrelated errors (500/502 are retryable immediately)', async () => {
    mockFetch(json({ detail: 'boom', error_code: 'server_error' }, 502))
    const api = await loadApi({ cooldown: 5 })

    await expect(api.factCheck('A claim long enough to be valid.')).rejects.toMatchObject({ status: 502 })
    expect(api.getCooldownRemainingMs()).toBe(0)
  })
})
