import { beforeEach, describe, expect, it, vi } from 'vitest'

/**
 * ---------------------------------------------------------------------------
 * Audit-trail tests (Part B.5 / Part C.6) and the dashboard's defence-in-depth
 * role re-check.
 * ---------------------------------------------------------------------------
 * The authoritative control is PostgreSQL RLS (see supabase/schema.sql and
 * docs/TESTING_CHECKLIST.md §4). These tests cover the client-side half: that a
 * log write is well-formed, that a logging failure never destroys a good AI
 * result, and that a non-educator gets an empty result set.
 */

function mockSupabase({ role = 'educator', insertError = null, rows = [], uid = 'user-1' } = {}) {
  const inserted = []
  const chain = {
    select: vi.fn(() => chain),
    eq: vi.fn(() => chain),
    gte: vi.fn(() => chain),
    order: vi.fn(() => chain),
    limit: vi.fn(() => chain),
    maybeSingle: vi.fn(async () => ({ data: role ? { role } : null, error: null })),
    insert: vi.fn(async (row) => {
      inserted.push(row)
      return { data: row, error: insertError }
    }),
    then: async (resolve) => resolve({ data: rows, error: null }),
  }
  vi.doMock('./supabaseClient.js', () => ({
    DEMO_MODE: false,
    supabaseReady: true,
    supabase: {
      auth: { getUser: vi.fn(async () => ({ data: { user: { id: uid } }, error: null })) },
      from: vi.fn(() => chain),
    },
  }))
  return { inserted, chain }
}

async function load() {
  vi.resetModules()
  return import('./scanLog.js')
}

beforeEach(() => {
  vi.resetModules()
  vi.unstubAllGlobals()
})

describe('logScan — audit trail writes (Part C.6)', () => {
  it('records who / what / result, and lets the DB generate the timestamp', async () => {
    const { inserted } = mockSupabase()
    const { logScan } = await load()

    const res = await logScan({
      contentType: 'image',
      inputSummary: 'suspect_photo.png',
      verdict: 'Likely Fake',
      confidenceScore: 94.2,
      userId: 'user-1',
    })

    expect(res.ok).toBe(true)
    expect(inserted).toHaveLength(1)
    expect(inserted[0]).toEqual({
      user_id: 'user-1',
      content_type: 'image',
      input_summary: 'suspect_photo.png',
      verdict: 'Likely Fake',
      confidence_score: 94.2,
    })
    // CRITICAL: no client-supplied timestamp. `DEFAULT now()` in Postgres owns it,
    // so a user cannot back-date or forward-date their own audit entry.
    expect('timestamp' in inserted[0]).toBe(false)
  })

  it('clamps an out-of-range confidence score instead of storing garbage', async () => {
    const { inserted } = mockSupabase()
    const { logScan } = await load()

    await logScan({ contentType: 'text', inputSummary: 'x', verdict: 'False', confidenceScore: 4242, userId: 'u' })
    await logScan({ contentType: 'text', inputSummary: 'x', verdict: 'True', confidenceScore: -17, userId: 'u' })
    await logScan({ contentType: 'text', inputSummary: 'x', verdict: 'True', confidenceScore: NaN, userId: 'u' })

    expect(inserted[0].confidence_score).toBe(100)
    expect(inserted[1].confidence_score).toBe(0)
    expect(inserted[2].confidence_score).toBeNull()
  })

  it('truncates a long claim so the audit table stays small and readable', async () => {
    const { inserted } = mockSupabase()
    const { logScan } = await load()

    await logScan({ contentType: 'text', inputSummary: 'a'.repeat(900), verdict: 'False', confidenceScore: 90, userId: 'u' })

    expect(inserted[0].input_summary.length).toBeLessThanOrEqual(180)
    expect(inserted[0].input_summary.endsWith('…')).toBe(true)
  })

  it('NEVER throws when logging fails — a good AI result must survive a DB hiccup', async () => {
    mockSupabase({ insertError: { message: 'new row violates row-level security policy' } })
    const { logScan } = await load()

    const res = await logScan({ contentType: 'image', inputSummary: 'a.png', verdict: 'Likely Fake', confidenceScore: 91, userId: 'u' })

    expect(res.ok).toBe(false)
    expect(res.error.message).toMatch(/row-level security/)
  })

  it('swallows a thrown exception from the client too', async () => {
    vi.doMock('./supabaseClient.js', () => ({
      DEMO_MODE: false,
      supabaseReady: true,
      supabase: {
        from: () => {
          throw new Error('supabase exploded')
        },
      },
    }))
    const { logScan } = await load()

    await expect(
      logScan({ contentType: 'image', inputSummary: 'a.png', verdict: 'x', confidenceScore: 1, userId: 'u' }),
    ).resolves.toMatchObject({ ok: false })
  })
})

describe('fetchEducatorStats — dashboard aggregation', () => {
  const ROWS = [
    { id: 1, user_id: 'a', content_type: 'image', verdict: 'Likely Fake', confidence_score: 94, timestamp: new Date().toISOString(), user_email: 'a@x.edu' },
    { id: 2, user_id: 'a', content_type: 'image', verdict: 'Likely Real', confidence_score: 88, timestamp: new Date().toISOString(), user_email: 'a@x.edu' },
    { id: 3, user_id: 'b', content_type: 'text', verdict: 'False', confidence_score: 92, timestamp: new Date().toISOString(), user_email: 'b@x.edu' },
    { id: 4, user_id: 'b', content_type: 'text', verdict: 'Unverified', confidence_score: 45, timestamp: new Date().toISOString(), user_email: 'b@x.edu' },
  ]

  it('computes totals and isolates flagged content for an educator', async () => {
    mockSupabase({ role: 'educator', rows: ROWS })
    const { fetchEducatorStats } = await load()

    const stats = await fetchEducatorStats({ days: 7, limit: 25 })

    expect(stats.totals.totalScans).toBe(4)
    expect(stats.totals.imageScans).toBe(2)
    expect(stats.totals.textChecks).toBe(2)
    expect(stats.totals.deepfakesDetected).toBe(2) // Likely Fake + False
    expect(stats.totals.uniqueUsers).toBe(2)
    expect(stats.totals.avgConfidence).toBeCloseTo((94 + 88 + 92 + 45) / 4, 5)
    expect(stats.recentFlagged.map((r) => r.id)).toEqual([1, 3])
  })

  it('returns an EMPTY result set for a student without even querying the view (defence in depth)', async () => {
    const { chain } = mockSupabase({ role: 'student', rows: ROWS })
    const { fetchEducatorStats } = await load()

    const stats = await fetchEducatorStats()

    expect(stats.rows).toEqual([])
    expect(stats.totals.totalScans).toBe(0)
    expect(stats.recentFlagged).toEqual([])
    // The view was never touched — only the profiles role check ran.
    expect(chain.gte).not.toHaveBeenCalled()
  })

  it('survives a project with no logs yet (fresh install)', async () => {
    mockSupabase({ role: 'educator', rows: [] })
    const { fetchEducatorStats } = await load()

    const stats = await fetchEducatorStats()

    expect(stats.totals).toMatchObject({ totalScans: 0, deepfakesDetected: 0, avgConfidence: 0 })
    expect(stats.recentFlagged).toEqual([])
  })

  it('propagates a real DB error so the UI can show a helpful message', async () => {
    const chain = {
      select: vi.fn(() => chain),
      eq: vi.fn(() => chain),
      gte: vi.fn(() => chain),
      order: vi.fn(() => chain),
      limit: vi.fn(() => chain),
      maybeSingle: vi.fn(async () => ({ data: { role: 'educator' }, error: null })),
      then: async (_res, rej) => rej(new Error('relation "educator_scan_logs" does not exist')),
    }
    vi.doMock('./supabaseClient.js', () => ({
      DEMO_MODE: false,
      supabaseReady: true,
      supabase: {
        auth: { getUser: async () => ({ data: { user: { id: 'u' } }, error: null }) },
        from: () => chain,
      },
    }))
    const { fetchEducatorStats } = await load()

    await expect(fetchEducatorStats()).rejects.toThrow(/does not exist/)
  })
})

describe('isFlagged', () => {
  it('recognises fake/false/misleading verdicts and ignores real/true/unverified', async () => {
    mockSupabase()
    const { isFlagged } = await load()

    expect(isFlagged({ verdict: 'Likely Fake' })).toBe(true)
    expect(isFlagged({ verdict: 'False' })).toBe(true)
    expect(isFlagged({ verdict: 'Misleading' })).toBe(true)
    expect(isFlagged({ verdict: 'Likely Real' })).toBe(false)
    expect(isFlagged({ verdict: 'True' })).toBe(false)
    expect(isFlagged({ verdict: 'Unverified' })).toBe(false)
    expect(isFlagged(null)).toBe(false)
  })
})
