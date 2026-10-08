# Testing TruthGuard AI

Four layers. Run them in this order — each one narrows where a problem can be.

| Layer | Command | Tests | Needs network? | When |
|---|---|---|---|---|
| **1. Backend units + contract** | `cd backend && python -m pytest -q` | **57** | No | Before you deploy |
| **2. Auth / RBAC (legacy HS256)** | `cd backend_security && …` | **23** | No | Before you deploy |
| **2b. Auth / JWKS (asymmetric RS256)** | `cd backend_security && python test_asymmetric_jwks.py` | **25** | localhost only | If your Supabase project was created after 1 May 2025 |
| **3. Frontend units** | `cd frontend && npm test` | **92** | No | Before you deploy |
| **4. Live end-to-end over HTTP** | `python tools/smoke_test.py <url>` | **30** | Partly | After every deploy |
| **5. In the browser** | `docs/DEPLOY.md` §6 | 14 checks | Yes | Before you present |

**Total automated: 172 tests.** Plus 30 live checks and 14 manual ones.

---

## 1 — Backend tests (57, no network, ~5 seconds)

```bash
cd backend
pip install -r requirements-dev.txt      # just pytest
python -m pytest -q
```

Expected: `57 passed`.

What they cover, and why each group exists:

| Group | Tests | The failure it prevents |
|---|---|---|
| `TestDetectImageContract` | 6 | A response field the React app reads disappears. **The API still returns 200**, so nothing else catches it — you find out when a badge renders `undefined` in front of the marker. |
| `TestDetectionDiscriminates` | 4 | The detector answers the same way regardless of input. Includes the false-positive test (a genuine camera JPEG must **not** be called fake) and the false-negative test (a generator-shaped PNG **must** be). |
| `TestUploadValidation` | 6 | A shell script renamed `.jpg` gets accepted; a 9 MB upload OOM-kills a free instance; a `../../etc/passwd` filename reaches the audit log. |
| `TestFactCheckValidation` | 7 | The 10–1000 char bounds drift from the frontend's, so a user passes the form and is then rejected by the server. |
| `TestErrorContract` | 3 | A 404 returns Starlette's HTML and the UI shows "Unexpected error" with no message. |
| `TestSystemEndpoints` | 3 | `/health` stops being public → Render's probe fails → the platform restart-loops a healthy service. |
| `TestCors` | 4 | `Authorization` missing from `allow_headers`: **every logged-in call dies in the browser while curl keeps working.** The most confusing bug in cross-origin deployment. |
| `TestRateLimiting` | 2 | The limiter is global, so twenty students behind one college NAT trip it together and the feature looks broken in class. |
| `TestAuthentication` | 5 | A route is added without `require_auth`; or the backend serves AI calls with **no JWT secret configured** instead of failing closed. |
| `TestEngineBehaviour` | 4 | The heuristic claims 100% certainty; a JPEG-only measurement is applied to a PNG and silently biases the score. |
| `TestFactCheckScorer` | 8 | **The dangerous one.** A CDC snippet reading *"The claim 'vaccines do not cause autism' is not evidence-based"* gets scored as **supporting** the myth — the tool tells a student the opposite of the truth. |
| `TestRetrievalHelpers` | 4 | DuckDuckGo redirect URLs are shown instead of real citations; a noise filter empties the result set and the user sees zero sources. |

Run one group:
```bash
python -m pytest test_api.py -q -k TestFactCheckScorer
python -m pytest test_api.py -q -k "cors or auth"
```

---

## 2 — Auth / RBAC deliverable (23 checks, no network)

```bash
cd backend_security
pip install -r requirements.txt
# Linux / macOS
SUPABASE_JWT_SECRET=test-secret-only-for-local-tests python3 test_jwt_middleware.py
# Windows PowerShell
$env:SUPABASE_JWT_SECRET="test-secret-only-for-local-tests"; python test_jwt_middleware.py
```

Expected: `23/23 checks passed.`

This is Part C.1 as a standalone artefact. It proves forged tokens, expired tokens, `alg=none` algorithm confusion, wrong audience, wrong issuer and student→educator escalation are all rejected. The secret here is a throwaway — it never touches your real Supabase secret.

---

## 2b — Asymmetric JWT / JWKS (25 checks)

```bash
cd backend_security
python test_asymmetric_jwks.py
```

Expected: `25/25 checks passed.`

**Why this suite exists.** Supabase projects created after **1 May 2025** sign access
tokens with an **RSA key (RS256)**, not the legacy HS256 shared secret. Such a project
has *no secret to configure at all* — verification uses the project's **public** key
from `https://<ref>.supabase.co/auth/v1/.well-known/jwks.json`. Before this suite
existed, the middleware only accepted HS256, so a brand-new Supabase project would
have returned `401` on every single AI call — a failure that looks exactly like a
wrong secret and can cost hours to diagnose. See **docs/SUPABASE_ENV_ELI5.md**.

Nothing here is mocked: the test generates a real 2048-bit RSA key pair, serves its
public half from a real JWKS HTTP endpoint, and verifies real RS256 signatures over
real HTTP fetches.

| Group | Checks | The failure it prevents |
|---|---|---|
| JWKS reachability & happy path | 3 | A valid new-project token is accepted, and the response contract is unchanged on the RS256 path |
| Role extraction | 2 | Educator/student role routing still works when claims come from an asymmetric token |
| Wrong signing key | 2 | A token signed by a *different* RSA key is rejected with `invalid_signature` |
| **Algorithm confusion** | 5 | See below |
| `alg: none` and unlisted algorithms | 4 | `none`, HS512, RS512, PS256 all rejected |
| Standard claim checks | 5 | Expiry, audience, issuer, missing `sub`, garbage — all `401` |
| `kid` handling | 1 | An unknown key id is `401`, never a silent fallback to "the only key we have" |
| Public routes | 2 | `/health` stays public; a missing header is `401` |
| JWKS caching | 1 | 5 requests cause ≤2 fetches, so the key set isn't refetched per scan |

### The algorithm-confusion attack

The classic exploit: take the server's **RSA public key** — public by design, served
over plain HTTP — and use it as an **HMAC secret** to sign a token whose header claims
`alg: HS256`. A verifier that lets a token choose both its algorithm *and* its key
material will verify that signature successfully, because the attacker can compute it.
The forged token in this suite even carries `app_metadata.role = "educator"`.

Two deliberate details make the result meaningful rather than decorative:

1. **The forged signature is hand-rolled** with `hmac`/`hashlib`, not produced by
   PyJWT. PyJWT refuses to use a PEM public key as an HMAC secret — a useful
   guard-rail in our own code, but *not* a defence, because a real attacker would not
   use a polite library.
2. **A control check proves the forged token is otherwise perfectly valid** — its
   signature matches under a naive verifier and its claims parse. Without that
   control, a `401` would prove nothing, since malformed input also gets a `401`.

The attack is then exercised in **both** configurations, because the risk differs:

| Configuration | Result | Why |
|---|---|---|
| RS256 project, no shared secret set | `503` | The HS256 path cannot run at all. Never `200` |
| **Both schemes configured** (migrated project that still has its legacy secret in the environment) | **`401 invalid_signature`** | The dangerous case: the HS256 path is live, so the only thing stopping the attacker is that signing requires the **secret**, not the **public key** they can read off the internet |

A final control confirms the reverse is not true — a token genuinely signed with the
configured secret still returns `200`. Rejecting the attack is only good news if the
server isn't simply rejecting all legacy tokens.

**Verified end-to-end against the real deployable backend** (`backend/main.py`, not
the example app):

```
{"status": 200, "verdict": "Likely Fake", "confidence": 76.9, "is_fake": true,
 "algorithm_in_token": "RS256"}
```

## 3 — Frontend tests (92, no network)

```bash
cd frontend
npm install
npm test
```

Expected: `Test Files 7 passed (7) · Tests 92 passed (92)`

| File | Tests | Covers |
|---|---|---|
| `utils/validation.test.js` | 18 | jpg/png/webp + 8 MB pre-upload checks; claim 10–1000 |
| `services/api.test.js` | 23 | JWT attached as `Bearer`; **never** a manual `Content-Type` on FormData; 429/502/503/504 → friendly messages; the 10 s client cooldown |
| `services/scanLog.test.js` | 10 | Every successful AI call writes to `scan_logs`; failure doesn't |
| `components/interactive/interactive.test.jsx` | 16 | The 3D primitives: WebGL fallback to CSS, `prefers-reduced-motion`, one visible flip face, `aria-live` |
| `components/ui.test.jsx` | 11 | Badge/gauge rendering, XSS-safe `SafeLink` allow-list |
| `components/guards.test.jsx` | 7 | `ProtectedRoute` and `EducatorRoute` (the 403 path) |
| `pages/Signup.test.jsx` | 7 | **The Hick's Law regression suite** — fails the build if a field comes back, a third role appears, or the default role stops being pre-selected |

Watch mode while you edit: `npm run test:watch`.

---

## 4 — Live smoke test (30 checks, over real HTTP)

```bash
python tools/smoke_test.py                                  # defaults to http://127.0.0.1:8000
python tools/smoke_test.py https://truthguard-backend.onrender.com
python tools/smoke_test.py --token <supabase-jwt>           # an auth-enabled backend
python tools/smoke_test.py --skip-factcheck                 # no internet
SMOKE_ORIGIN=https://my-app.vercel.app python tools/smoke_test.py <url>   # test your real CORS origin
```

**Why this is separate from pytest:** `pytest` runs in-process with no network, so it cannot see CORS, cold starts, rate limits, or a misconfigured `FRONTEND_ORIGIN`. `smoke_test.py` talks to a URL exactly the way the browser does — so you can point it at your **Render deployment** and get a real answer.

It generates its own test images (no downloads, no Pillow required — Pillow only enables two extra checks).

### Actual output from a local run

```
1 · Is the service alive?
  PASS  GET /health  200 · v1.0.0
        detection engine : heuristic-forensics
        fact-check engine: duckduckgo+instant-answer+wikipedia
        auth enabled     : False   jwt secret set: False

2 · Do the advertised limits match what the frontend hardcodes?
  PASS  GET /api/v1/meta  8 MB cap, claim 10-1000 chars

3 · IMAGE detection — does it actually detect?
  PASS  response contract              all 6 fields the frontend depends on
  PASS  verdict is explainable          engine=heuristic-forensics, 6 signals
  PASS  real camera JPEG NOT called fake  Likely Real · p=0.109
  PASS  re-encoded JPEG shows a grid     boundary ratio 2.309x (clean ≈ 1.2x)
  PASS  generator-shaped PNG IS flagged   Likely Fake · p=0.93
  PASS  AI-tool fingerprint found        Midjourney XMP tag in raw bytes
  PASS  verdict is deterministic         same bytes twice -> p=0.93

4 · Upload validation — the server-side security half
  PASS  non-image renamed .jpg rejected   415 — magic bytes, not the header
  PASS  wrong Content-Type rejected       415
  PASS  wrong multipart field rejected    422 — must be named "file"
  PASS  oversized upload rejected         413 — the 8 MB DoS cap holds
  PASS  path traversal neutralised        logged as 'passwd'

5 · TEXT detection — the fact-checker
  PASS  fact-check contract              all 5 fields present
  PASS  a documented myth is refuted      False · 6 sources · 1498ms
  PASS  sources are http(s) only          cdc.gov, wikipedia.org, factcheck.org, snopes.com
  PASS  claim under 10 chars rejected     422 claim_too_short
  PASS  claim over 1000 chars rejected    422 claim_too_long
  PASS  control chars stripped            log-injection guard working
  PASS  empty claim rejected              422

6 · Error contract
  PASS  404 returns JSON, not HTML
  PASS  malformed JSON leaks no stack trace

7 · CORS
  PASS  preflight allows your origin      allow-origin: http://localhost:5173
  PASS  Authorization header permitted
  PASS  credentials not allowed
  PASS  unlisted origins not reflected    it is an allow-LIST, not a wildcard

8 · Rate limiting (Part C.3)
  PASS  limiter trips + says how long     429 · Retry-After: 54s

9 · Security posture
  PASS  /health leaks no secrets
  PASS  root URL is a readable service page

==============================================================
  30/30 checks passed
==============================================================
```

A `SKIP` is not a failure — it means the check couldn't be performed (no internet, Pillow absent, auth configured differently). The script says which.

---

## 5 — In the browser

`docs/DEPLOY.md` §6 has the 14-step acceptance test (route guards, client-side rejection before upload, the 429 cooldown, the audit row appearing in Supabase, the `Authorization: Bearer` header in DevTools, the educator 403). Items 12–14 are the ones markers ask about.

`docs/TESTING_CHECKLIST.md` is the full manual plan, including the RLS-bypass proofs, the 19 browser-only 3D/interaction checks in §10b, accessibility in §11, and a 19-item screenshot list.

---

## The fastest possible "does it work?" (3 commands)

```bash
# terminal 1 — backend
cd backend && pip install -r requirements.txt
python -m uvicorn main:app --reload --port 8000

# terminal 2 — prove the backend works, without a browser
python tools/smoke_test.py

# terminal 2 — then the UI
cd frontend && npm install && npm run dev      # http://localhost:5173
```

If `smoke_test.py` is green and the browser isn't, the problem is **frontend configuration or CORS** — not the API. That single fact saves most of the debugging time.

---

## What each layer can and cannot see

| | pytest | smoke_test | browser |
|---|---|---|---|
| Response contract | ✅ | ✅ | ✅ |
| Detection accuracy | ✅ | ✅ | ✅ |
| Validation + security | ✅ | ✅ | ✅ |
| Real CORS preflight | ✅ (simulated) | ✅ (real headers) | ✅ (real enforcement) |
| Cold starts / sleeping service | ❌ | ✅ | ✅ |
| Rate limiting under real timing | ✅ (unit) | ✅ (live) | ✅ |
| Supabase RLS actually blocking a user | ❌ | ❌ | ✅ — needs a real project |
| The 3D layer, animations, a11y | ✅ (jsdom) | ❌ | ✅ |
| Your deployed `FRONTEND_ORIGIN` value | ❌ | ✅ | ✅ |

**RLS can only be proven against a real Supabase project** — there is no Postgres in a unit test. That's what `supabase/verify.sql` and the RLS-bypass proofs in `docs/TESTING_CHECKLIST.md` §7 are for.
