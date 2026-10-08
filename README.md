# 🛡️ TruthGuard AI

**Deepfake & Misinformation Detection for civic education**
*Software Engineering project · aligned with UN SDG 4 (Quality Education) and SDG 16 (Peace, Justice & Strong Institutions)*

A **complete full-stack application**: a React + Tailwind SPA, a FastAPI detection backend that deploys to Render, and a Supabase auth/database layer with three-layer role-based access control and an immutable audit trail — presented through a WebGL/3D interactive interface designed around Hick's Law.

The backend is **not** a wrapper around someone else's model. It ships two swappable detection engines (image forensics by default, a real transformer classifier behind one env var) and three fact-check retrieval engines (DuckDuckGo + Wikipedia + OpenAlex by default, an LLM behind one env var, an offline knowledge base for demos). **172 automated tests** cover both halves.

---

## Contents

| Path | What it is |
|---|---|
| `backend/` | **The FastAPI backend** — detection + fact-checking engines, JWT auth, rate limiting, validation, audit log, **57 tests** |
| `render.yaml` | Render Blueprint: creates the web service, sets every env var, deploys on push |
| `railway.yaml` | The same backend on **Railway** instead — use one, not both. Railway doesn't sleep when idle |
| `frontend/` | React 18 + Vite + Tailwind SPA (Part A), **92 tests** |
| `tools/check_backend.py` | **Run this first when detection does nothing** — diagnoses the backend URL, routes, CORS, auth and rate limits in one command |
| `tools/mock_backend.py` | Contract-accurate **mock AI backend** (stdlib only) so the whole UI works offline, before the real model is deployed |
| `supabase/schema.sql` | **The SQL to run in Supabase** — tables, RLS policies, triggers, dashboard view (Part B) |
| `supabase/verify.sql` | Evidence queries that prove RLS/triggers/view options are correctly applied |
| `backend_security/jwt_auth.py` | Drop-in FastAPI JWT middleware + `require_role()` RBAC dependency (Part C.1) |
| `backend_security/integration_example.py` | The exact integration diff for the existing backend, runnable standalone |
| `backend_security/test_jwt_middleware.py` | 23 automated checks proving the auth/RBAC layer works |
| `docs/PROJECT_STRUCTURE.md` | **The whole project, file by file** — annotated tree, and a table mapping every file to the requirement it satisfies |
| `docs/DEPLOY.md` | **Start here** — the full Render + Supabase + frontend deployment, end-to-end acceptance test, known limitations, submission checklist |
| `docs/FIX_RENDER_BUILD_ELI5.md` | **"Build failed: maturin / pydantic-core / Read-only file system"** — why a Python-version mismatch causes a Rust compiler error, the 2-minute fix on Render and Railway, and the two follow-on traps |
| `docs/GO_LIVE_ELI5.md` | **"My site is up but the AI calls fail"** — plain-language, ordered walkthrough: unzip the prebuilt bundle, fill in 3 values, drop it on Netlify, then point the backend at it. No Node needed |
| `docs/SUPABASE_ENV_ELI5.md` | **"What do I put in `SUPABASE_JWT_SECRET`?"** — plain-language answer, incl. why it may need to be *blank*, how to tell which kind of Supabase project you have in 30 s, an error→cause table, and a live-demo plan |
| `docs/TESTING.md` | **How to test it** — all 6 layers, what each can and cannot see, a real 30/30 smoke-test transcript, and the algorithm-confusion attack writeup |
| `docs/API_REFERENCE.md` | **Every API** — endpoints, request/response shapes, all 12 error codes, every env var, and which external services are called (spoiler: none need a key) |
| `tools/smoke_test.py` | 30 live end-to-end checks over real HTTP — point it at localhost *or* your deployment |
| `docs/RUNNING_LOCALLY.md` | Laptop setup: install Node, `npm install`, run it, troubleshooting |
| `docs/WHY_NOT_DETECTING.md` | Decision tree for a backend that isn't answering |
| `docs/RBAC.md` | Paste-ready report section: RBAC at three layers (Part C.7) |
| `docs/HICKS_LAW.md` | Paste-ready report section: the Hick's Law audit of every screen, and the interaction-design rationale |
| `docs/TESTING_CHECKLIST.md` | Manual test plan incl. the RLS-bypass proofs and screenshot list |

---

> **First time on your own laptop?** Read **[`docs/RUNNING_LOCALLY.md`](docs/RUNNING_LOCALLY.md)** —
> it covers installing Node, unzipping, `npm install`, the 2-minute demo-mode path, and a
> troubleshooting table. The section below is the short version.

## 1. Quick start

> **Deploying for submission?** Go straight to **[`docs/DEPLOY.md`](docs/DEPLOY.md)** — it is written
> for a next-day deadline and covers Render, Vercel, Supabase, the acceptance test and the
> submission checklist. The steps below are for running everything locally.

### Step 0 — Run the backend (terminal 1)

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m uvicorn main:app --reload --port 8000
```

Open **http://127.0.0.1:8000** — you should see the endpoint list. `frontend/.env` already points here, so the frontend will find it with no configuration.

`AUTH_ENABLED` defaults to **true** and fails **closed**, so for a no-login local run either set `AUTH_ENABLED=false` in `backend/.env`, or complete Step 1 first so a real token exists.

### Step 1 — Create the Supabase project

1. [supabase.com](https://supabase.com) → **New project** (free tier is fine).
2. Dashboard → **SQL Editor** → *New query* → paste the entire contents of **`supabase/schema.sql`** → **Run**.
   You should see “Success. No rows returned”.
3. *(Optional but recommended)* Run **`supabase/verify.sql`** the same way and check the expected values printed in its comments — this is your evidence that RLS is on, forced, and correctly shaped.
4. Dashboard → **Authentication** → *Providers* → **Email** → turn **OFF** “Confirm email”.
   *Why:* with confirmation ON, `signUp()` returns no session, so a new user cannot immediately satisfy an RLS policy. The app handles that case (it shows a “check your inbox” screen and uses the `set_my_role()` definer function), but OFF is smoother for a live demo.
5. Dashboard → **Settings** → **API** and copy:
   - **Project URL** → `VITE_SUPABASE_URL`
   - **anon / public key** → `VITE_SUPABASE_ANON_KEY`
   - **JWT Secret** → *backend only* (`SUPABASE_JWT_SECRET`). **Never** put this in the frontend.

### Step 2 — Configure the frontend

```bash
cd frontend
cp .env.example .env
```

Edit `.env`:

```ini
VITE_API_BASE_URL=https://truthguard-backend.onrender.com
VITE_SUPABASE_URL=https://YOUR-PROJECT-REF.supabase.co
VITE_SUPABASE_ANON_KEY=eyJhbGciOi...your-anon-key...
VITE_DEMO_MODE=false
```

### Step 3 — Run it

```bash
npm install
npm run dev          # http://localhost:5173
```

### Step 4 — Create the two demo accounts

Use `/signup` twice:

| Email | Role | Use it to demonstrate |
|---|---|---|
| `educator@college.edu` | **Educator** | the analytics dashboard, class-wide visibility |
| `student@college.edu` | **Student** | the 403 page, and RLS hiding other users' logs |

Then run a few scans/fact-checks as each so the dashboard has data. (Or uncomment the seed block at the bottom of `schema.sql`.)

### Step 5 — Run the test suites (evidence for the report)

```bash
# Frontend: 92 automated tests — RBAC guards, input validation, XSS-safe links,
# JWT attachment, 429 cooldown, error mapping, audit writes, 3D accessibility,
# and a Hick's Law regression suite that fails if the signup form grows a field.
cd frontend && npm test

# Backend auth layer: 23 checks — forged/expired/alg=none tokens, 401 vs 403,
# server-side validation, public /health.
cd ../backend_security
pip install -r requirements.txt
SUPABASE_JWT_SECRET=test-secret-only-for-local-tests python test_jwt_middleware.py
```

### Step 6 — Secure the backend (teammate task)

Copy `jwt_auth.py` into the FastAPI repo as `app/security/jwt_auth.py`, add
`dependencies=[Depends(require_auth)]` to the `/api/v1` router, and set
`SUPABASE_JWT_SECRET` in the Render service's Environment tab. See the header of
`integration_example.py` for the full 3-step diff — **no inference code changes**.

---

## 2. Demo mode (no Supabase needed)

Shipped `.env` has `VITE_DEMO_MODE=true` with empty Supabase vars, so the app runs immediately as a
signed-in educator and every screen is explorable — useful for screenshots before the project is
provisioned, or if Supabase is down during the presentation.

- Auth is stubbed (role = `educator`, all screens reachable).
- AI calls still hit the real backend (without a JWT, so they only work while the backend is auth-free).
- `scan_logs` writes go to an in-memory stub, so the dashboard still demonstrates itself.
- A yellow **DEMO MODE** badge shows in the navbar so nobody mistakes it for the real thing.

**Set `VITE_DEMO_MODE=false` for the graded demo.**

---

## 3. Architecture

```
Browser (React SPA)
  │
  ├─ Supabase Auth ──────── email/password → JWT session (managed by supabase-js)
  │      │
  │      └─ Postgres (RLS) ─ profiles, scan_logs, educator_scan_logs view
  │                          ↑ every query rewritten with auth.uid()/role predicates
  │
  └─ FastAPI AI backend ─── Authorization: Bearer <supabase JWT>
         │                    verified by jwt_auth.require_auth (Depends)
         ├─ POST /api/v1/detect-image   (multipart, field "file", ≤8 MB)
         ├─ POST /api/v1/fact-check     (JSON, claim 10–1000 chars)
         └─ GET  /health                (public — uptime probes need no token)

Result of every successful AI call ──► INSERT INTO scan_logs  (append-only audit trail)
                                       └──► powers the Educator Dashboard
```

### Frontend file map

```
frontend/src/
├── main.jsx                     Router + Toast + Auth providers
├── App.jsx                      Route table, guard composition, z-order contract
├── index.css                    Tailwind layers + design tokens
├── styles/3d.css                All 3D/motion CSS + the reduced-motion override
├── context/
│   └── AuthContext.jsx          Session, profile, role; sign in/up/out
├── components/
│   ├── ProtectedRoute.jsx       Layer-1: requires a session
│   ├── EducatorRoute.jsx        Layer-1: requires role = educator → else /403
│   ├── Navbar.jsx               Role-aware glass navigation (scroll-reactive)
│   ├── AuthLayout.jsx           Shared shell for login/signup
│   ├── FileDropzone.jsx         Drag & drop + pre-upload validation
│   ├── Toast.jsx                Toasts (used by "Generate Quiz" stub)
│   ├── FullPageLoader.jsx       Session-restore splash
│   ├── AmbientBackground.jsx    Fixed 3D depth layer (grid floor, aurora, grain)
│   ├── ScrollProgress.jsx       Reading-progress hairline (scaleX only, no layout)
│   ├── ui.jsx                   VerdictBadge, ConfidenceGauge, SafeLink, …
│   ├── three/
│   │   ├── Hero3D.jsx           WebGL scene (lazy-loaded `three`) + pulse API
│   │   └── Hero3DFallback.jsx   CSS-3D hero for no-WebGL / reduced-motion
│   └── interactive/
│       ├── TiltCard.jsx         Pointer-driven perspective tilt + glare
│       ├── SpotlightCard.jsx    Edge-tracking light (Linear/Vercel look)
│       ├── ScrollReveal.jsx     IntersectionObserver entrance animation
│       ├── MagneticButton.jsx   Cursor-attracted CTA (capped, Fitts-safe)
│       ├── CountUp.jsx          rAF number tween for the stat cards
│       ├── ConfidenceRing.jsx   3D-looking SVG gauge with light spill
│       └── VerdictFlip.jsx      True rotateY card flip for the verdict reveal
├── pages/
│   ├── Landing.jsx              Marketing + live backend health pill
│   ├── Login.jsx  Signup.jsx    Supabase Auth + role selection
│   ├── ImageScanner.jsx         POST /api/v1/detect-image
│   ├── FactChecker.jsx          POST /api/v1/fact-check (chat UI)
│   ├── EducatorDashboard.jsx    Stats, flagged-content table, quiz stub
│   ├── AccessDenied.jsx         403
│   └── NotFound.jsx             404
├── services/
│   ├── supabaseClient.js        Client factory (+ demo stub)
│   ├── api.js                   THE ONLY module that calls the AI backend
│   └── scanLog.js               Audit-trail writes + dashboard aggregation
├── hooks/
│   └── useRateLimitCooldown.js  429 countdown for the submit button
└── utils/
    ├── validation.js            File/claim validation, URL allow-listing
    └── errors.js                HTTP status → friendly message mapping

Tests (colocated, run with `npm test`) — 92 in total:
    components/guards.test.jsx              7  — ProtectedRoute / EducatorRoute behaviour
    components/ui.test.jsx                 11  — SafeLink URL allow-listing, badge tones, a11y
    components/interactive/*.test.jsx      16  — 3D fallback, reduced motion, a11y, disabled state
    pages/Signup.test.jsx                   7  — Hick's Law regression: decision count is locked in
    utils/validation.test.js               18  — file/claim validation, javascript: URL blocking
    services/api.test.js                   23  — JWT header, multipart, error mapping, 429 cooldown
    services/scanLog.test.js               10  — audit-trail writes, dashboard role re-check
```

---

## 4. Design system

| Token | Value | Tailwind class |
|---|---|---|
| Background | `#0A192F` | `bg-navy` |
| Card background | `#112240` | `bg-navy-card` |
| Border | `#233554` | `border-navy-border` |
| Accent / primary | `#64FFDA` | `text-teal`, `bg-teal` |
| Primary text | `#E6F1FF` | `text-ink` |
| Secondary text | `#8892B0` | `text-ink-muted` |
| Danger / alert | `#FF4D4D` | `text-danger` |
| Warning | `#FFD166` | `text-warn` |
| Safe / real | `#4ADE80` | `text-safe` |
| Font | Inter (body), Poppins (display) | `font-sans`, `font-display` |
| Radius | 8–10 px | `rounded`, `rounded-card` |
| Shadow | soft navy depth | `shadow-card`, `shadow-glow` |

Verdict colour mapping is centralised in `toneFor()` (`components/ui.jsx`):
**red** = Likely Fake / False · **green** = Likely Real / True · **yellow** = Uncertain / Unverified.
Colour is never the only signal — every badge also carries its text label (colour-blind safe).

---

## 4a. The backend (`backend/`)

A FastAPI service implementing the exact contract the frontend was built against:

```
GET  /health                  public — Render health check, reports engine + auth config
GET  /api/v1/meta             public — advertises the limits the frontend hardcodes
POST /api/v1/detect-image     multipart field "file", jpg/png/webp, <= 8 MB   [JWT]
POST /api/v1/fact-check       JSON {"claim": "..."} 10-1000 chars             [JWT]
errors                        {"detail", "error_code"} on 400/413/415/422/429/502/503/504
```

### Engines are strategies, selected by env var

| | `heuristic` *(default)* | `transformer` | `mock` |
|---|---|---|---|
| **What** | Image forensics | Hugging Face classifier | Deterministic stub |
| **Needs** | Nothing | `torch`, ≥4 GB RAM, paid instance | Nothing |
| **Boots** | Seconds | Minutes (downloads weights) | Seconds |

| | `duckduckgo` *(default)* | `llm` | `mock` |
|---|---|---|---|
| **What** | 5-layer retrieval + evidence scoring | Retrieve, then llama-3.3-70b reasons over it | Offline knowledge base |
| **Needs** | Nothing | Free `GROQ_API_KEY` | Nothing |

Swapping either is a dashboard change on Render — no code, no frontend change. That is the point of the interface.

### What the heuristic detector actually measures

Not a neural network. Seven weighted forensic signals, squashed through a logistic curve and **capped at p=0.93** because no heuristic is entitled to certainty:

| Signal | Forensic reasoning | Measured separation |
|---|---|---|
| JPEG double-compression grid | A camera writes one DCT pass; re-encoding imposes a second, and the two interfere on 8×8 boundaries | **1.2× clean vs 6.9× re-encoded** |
| Sensor-noise residual | Real sensors add broadband photon noise; generated images are synthesised smooth | 3.14 vs 0.09 high-pass energy |
| EXIF camera provenance | A photo from a phone carries Make/Model/lens data | −2.6 weight (strongest "real" signal) |
| Generator-typical geometry | 1024×1024, 768×768, 512×512 are model-native resolutions | +1.3 |
| Container mismatch | Photographic content in PNG, or with an alpha channel | +0.8 / +0.7 |
| Embedded generator fingerprints | "Midjourney", "DALL-E", "ComfyUI" in XMP/PNG chunks — bytes Pillow doesn't surface | +3.0 |
| Aspect ratio | Sensors give 4:3, 3:2, 16:9. Exactly 1:1 is a generator default | +0.6 |

Every response names its engine, returns the full `signals` breakdown, and carries a disclaimer. Verified behaviour:

| Image | Verdict |
|---|---|
| Camera JPEG with EXIF + sensor noise | **Likely Real** (p=0.07) |
| Clean single-save JPEG | **Uncertain** (p=0.67) — honest: only "no EXIF", which is weak |
| Re-encoded JPEG | **Likely Fake** (p=0.93) |
| Smooth 1024×1024 PNG with alpha | **Likely Fake** (p=0.93) |
| PNG with a Midjourney XMP tag | **Likely Fake** (p=0.93) |
| Shell script renamed `.jpg` | **415** — magic bytes checked, not the Content-Type header |

**Honest limit:** the keyword fact-checker scores 7/12 on a claim battery with no API key. It misjudges *"smoking causes lung cancer"* because retrieved pages are full of negations about related propositions. `docs/DEPLOY.md` §7.2 documents this and the one-env-var fix (`FACT_CHECK_ENGINE=llm`). Three mitigations are already in the code: negation handling, a corroboration discount, and an explicit `CAUTION` line in thin-evidence explanations.

### Security controls (all with WHY comments, all tested)

| Control | Where | The property |
|---|---|---|
| JWT Bearer verification | `backend_security/jwt_auth.py` | HS256 + `exp`/`iat`/`aud`/`iss`; algorithm allow-list blocks `alg=none`; **fails closed** — no secret → 503, never open access |
| Router-level auth | `backend/main.py` | `dependencies=[Depends(require_auth)]` on the router, so a new route is protected by default |
| Magic-byte validation | `_validate_upload()` | The Content-Type header is client-controlled; the file's first bytes are not |
| Size + pixel bombs | `config.py` | 8 MB body cap **and** a 64-megapixel decode cap, so one PNG cannot OOM a free instance |
| Sliding-window rate limit | `api/rate_limit.py` | Keyed on the **JWT subject**, so a college NAT doesn't pool 20 students into one bucket; sends an honest `Retry-After` |
| CORS allow-list | `main.py` | From `FRONTEND_ORIGIN`; `allow_credentials=False` because we use Bearer tokens |
| Single error shape | `api/errors.py` | Normalises FastAPI's four different error formats into `{"detail","error_code"}`; stack traces logged, never returned |
| Audit trail | `audit_log` middleware | Who/what/status/duration. **Never** image bytes, **never** claim text |
| Log-injection guard | `_strip_control_chars()` | Newlines and NULs removed so a claim cannot forge audit-log lines |

---

## 4b. The 3D interaction layer

Full rationale in **`docs/HICKS_LAW.md`**. Summary:

### Real WebGL, loaded lazily

`components/three/Hero3D.jsx` renders a wireframe icosahedron "shield" with two orbital rings and a 2,000-point particle field, lit in the palette. It parallaxes toward the pointer, recedes as you scroll, and **pulses red when the scanner finds a deepfake**.

| Property | Implementation |
|---|---|
| Bundle cost | `three` is `await import('three')` **inside the effect** → separate 684 kB chunk (176 kB gzip), never in the initial download |
| No WebGL / software GPU | `detectWebGL()` rejects SwiftShader & llvmpipe → CSS-3D `Hero3DFallback` renders instead. No empty box, ever. |
| `prefers-reduced-motion` | Skips WebGL entirely; re-checked **live** via `matchMedia` change events |
| Battery | rAF loop pauses when the canvas is off-screen (`IntersectionObserver`) and when the tab is hidden (`visibilitychange`) |
| Smoothness | Pointer position is **never** written to the DOM in the event handler — it is lerped toward inside the loop, so a 240 Hz trackpad can't outrun the frame rate |
| Memory | Every geometry, material, the renderer and its canvas are disposed on unmount (React StrictMode double-mounts effects in dev, so a leak would show immediately) |
| Particles | One `THREE.Points` = **one draw call** for 2,000 particles, not 2,000 meshes |
| GC stutter | The two `THREE.Color` scratch objects used per frame are hoisted out of the loop — zero allocation at 60 fps |

### CSS 3D everywhere else

Perspective grid floor, aurora fields, glass panels with gradient hairline borders, pointer-tracking tilt (`TiltCard`), edge-tracking spotlight (`SpotlightCard`), a genuine `rotateY` verdict flip (`VerdictFlip`), scroll reveals, magnetic CTAs, count-up metrics, and a reading-progress bar.

**All of it animates only `transform`, `opacity` and custom properties** — the three things a browser can composite without re-running layout or paint. `will-change` is applied only where it earns its layer, and every decorative layer is `pointer-events: none` so a blurred blob can never swallow a click.

### Hick's Law — decision counts were cut, not just decorated

| Screen | Before | After |
|---|---|---|
| Signup | **4** decisions (email, password, confirm, role) | **2** (email, role — pre-selected to `student`) |
| Landing CTA | 3 equal-weight buttons | 1 primary + 1 secondary |
| Scanner header | 2 competing buttons | 1 (reset moved inside the result card) |
| Scanner result | 5 simultaneous metrics | 1 focal ring + 4 behind `<details>` |
| Dashboard header | 5 controls | 1 primary + 1 binary segmented control + 1 quiet icon |
| Dashboard filtering | would need 4 new buttons | **0** — the stat cards *are* the filters (direct manipulation) |

The confirm-password field was **removed** and replaced with a Show/Hide toggle plus a live strength meter: visibility removes the reason duplication exists. No security property changes (Supabase still enforces length server-side and hashes with bcrypt), and `pages/Signup.test.jsx` fails the build if anyone adds the field back.

---

## 5. Database schema (Part B.1 / B.2)

> Full, commented, runnable script: **`supabase/schema.sql`**. Summary below.

### `profiles`

| Column | Type | Notes |
|---|---|---|
| `id` | `uuid` PK | references `auth.users(id) ON DELETE CASCADE` |
| `email` | `text` | lower-cased by the client before signup |
| `role` | `user_role` enum | `'student' \| 'educator'`, **default `'student'`** (least privilege) |
| `role_locked` | `boolean` | write-once guard, set by `set_my_role()` |
| `created_at` | `timestamptz` | `default now()` |

### `scan_logs` — the audit trail

| Column | Type | Notes |
|---|---|---|
| `id` | `bigint identity` PK | |
| `user_id` | `uuid` | references `auth.users` `ON DELETE SET NULL` — deleting a user must **not** delete audit history |
| `content_type` | `text` | `CHECK IN ('image','text')` |
| `input_summary` | `text` | truncated claim, or the image **filename only** (never image bytes) |
| `verdict` | `text` | e.g. `Likely Fake`, `False` |
| `confidence_score` | `numeric(5,2)` | `CHECK 0–100` |
| `timestamp` | `timestamptz` | `DEFAULT now()` — **server-generated**, so a client cannot back-date activity |

### RLS policies

| Policy | Table | Cmd | Rule |
|---|---|---|---|
| `profiles_select_own` | profiles | SELECT | `id = auth.uid()` |
| `educators_select_all_profiles` | profiles | SELECT | caller is an educator (needed so the dashboard join can resolve submitter emails) |
| `profiles_update_own` | profiles | UPDATE | `USING` + `WITH CHECK (id = auth.uid())` |
| *none by design* | profiles | INSERT | rows are created only by the `handle_new_user()` trigger |
| `students_select_own_scan_logs` | scan_logs | SELECT | `user_id = auth.uid() AND role = 'student'` |
| `educators_select_all_scan_logs` | scan_logs | SELECT | caller's role is `educator` |
| `users_insert_own_scan_logs` | scan_logs | INSERT | `WITH CHECK (user_id = auth.uid())` — no forged attribution |
| *none by design* | scan_logs | UPDATE / DELETE | **append-only audit trail** |

RLS is both `ENABLE`d **and** `FORCE`d, so it applies even to the table owner. With no matching policy the answer is an empty set — the system fails closed.

### Functions & triggers

| Object | Purpose |
|---|---|
| `handle_new_user()` | `AFTER INSERT ON auth.users` → creates the `profiles` row (role from `raw_user_meta_data`, else `'student'`) and mirrors the role into `app_metadata` so the backend JWT carries it |
| `set_my_role(p_role)` | `SECURITY DEFINER`, write-once role assignment; only touches `id = auth.uid()`, only accepts the two enum values, then sets `role_locked = true` |
| `enforce_role_immutable()` | `BEFORE UPDATE ON profiles` → silently reverts any attempt by a user to change their **own** role (blocks one-line privilege escalation) |
| `current_user_role()` | `SECURITY DEFINER` + pinned `search_path` → resolves the caller's role for policies without recursing |
| `jwt_role()` | reads the role claim out of the JWT (`app_metadata`, falling back to `user_metadata`) |
| `educator_scan_logs` (view) | `scan_logs ⋈ profiles ⋈ auth.users`; **`security_invoker = true`** so RLS still governs what each caller sees |

> ⚠️ Every `SECURITY DEFINER` function pins `search_path = public, pg_temp`. An unpinned search path is a classic Postgres privilege-escalation vector (schema shadowing) and Supabase's own linter flags it.

---

## 6. Security controls (Part C)

| # | Control | Where | Why it matters |
|---|---|---|---|
| **C.1** | **JWT on every AI call** | `services/api.js` → `getAccessToken()` reads a *fresh* token per request; backend verifies it in `backend_security/jwt_auth.py` | Without it, GPU inference is free compute for anyone on the internet, and AI usage is unattributable. Fresh-per-request means we never hold a stale or leaked copy of the token. |
| **C.2** | **Input validation & sanitisation** | `utils/validation.js` (client) + FastAPI `Field(min_length/max_length)` & content-type/size checks (server) | Instant feedback and no wasted inference on doomed requests. The client check is bypassable, so the server repeats it — defence in depth. Control characters are stripped so claims cannot forge log lines (log injection). |
| **C.3** | **Rate-limit awareness** | `api.js` cooldown state + `hooks/useRateLimitCooldown.js` | A 429 means “wait”. Locking the button for 10 s makes that automatic, stops anxious users from extending their own ban, and protects a shared GPU service from request spam. |
| **C.4** | **Secure environment variables** | `.env` (git-ignored), `.env.example` (committed) | Secrets never reach the repository or a screenshot. Only `VITE_`-prefixed vars are bundled; the JWT secret and any `service_role` key stay server-side. |
| **C.5** | **XSS prevention** | React escaping everywhere + `SafeLink` URL allow-list + CSP in `index.html` | React escapes text but **not** `href` — `javascript:alert(1)` is a valid, fully-escaped URL that still executes. `SafeLink` allows only `http/https` and adds `rel="noopener noreferrer"` (blocks tab-nabbing + Referer leakage). `dangerouslySetInnerHTML` appears **nowhere** in the codebase. The CSP is the backstop if markup ever is injected. |
| **C.6** | **Audit trail** | `scan_logs` + `services/scanLog.js` + server-side `[audit]` log lines | WHO (`user_id`) / WHAT (`content_type`, `input_summary`) / RESULT (`verdict`, `confidence_score`) / WHEN (`timestamp`, DB-generated). Append-only: no UPDATE or DELETE policy exists for any application role, so history cannot be edited or erased. Also serves as an abuse signal. |
| **C.7** | **RBAC at three layers** | React guards → Postgres RLS → FastAPI JWT role claim | See **`docs/RBAC.md`**. Each layer fails independently and safely; the role defaults to `student` whenever it is missing or unrecognised. |
| bonus | **Email masking on the dashboard** | `EducatorDashboard.maskEmail()` | Dashboards get projected in classrooms; showing full student emails leaks personal data to the whole room (data minimisation). |
| bonus | **Object URLs revoked** | `FileDropzone` | Prevents a memory leak from repeated uploads; previews are `blob:` URLs, never injected bytes. |
| bonus | **No source maps in production** | `vite.config.js` | Avoids shipping readable source and inline comments to the public. |

### Verify the XSS claim yourself

```bash
# The API itself must never be *called*. These all return nothing:
grep -rn "dangerouslySetInnerHTML=" frontend/src
grep -rn "innerHTML *=" frontend/src
grep -rn "eval(" frontend/src
grep -rn "document.write" frontend/src

# This one DOES match — but only inside explanatory comments, which is why the
# command above searches for the call syntax (`=`) rather than the bare word:
grep -rn "dangerouslySetInnerHTML" frontend/src
```

### Production hardening to-do (mention in the report as future work)

- Serve the CSP as a real HTTP response header (Netlify `_headers`, Vercel `vercel.json`, or nginx), not just a `<meta>` tag.
- Add `Strict-Transport-Security` and `Permissions-Policy` headers on the host.
- Turn on Supabase **email confirmation** and configure a custom SMTP provider before any real users sign up.
- Add server-side rate limiting in front of the AI endpoints (e.g. `slowapi`) — the client cooldown is UX, not a control.
- Rotate `SUPABASE_JWT_SECRET` if it is ever committed; re-check the `profiles` role from the DB for highly sensitive endpoints (token claims can be up to ~1 h stale).

---

## 7. API contract (implemented by `backend/`, consumed by `frontend/`)

### `POST /api/v1/detect-image`
`multipart/form-data`, field name **`file`**, ≤ 8 MB, JPG/PNG/WEBP.

```json
{ "verdict": "Likely Fake", "confidence": 94.2, "raw_label": "fake",
  "fake_probability": 0.942, "is_fake": true, "analyzed_in_ms": 1823 }
```

### `POST /api/v1/fact-check`
```json
// request
{ "claim": "Vaccines cause autism in children" }
// response — measured, from the live backend with no API key
{ "verdict": "False", "confidence": 97.3,
  "explanation": "Across 6 retrieved source(s): 0.7 weighted supporting signal(s), 26.7 refuting…",
  "sources": [ { "title": "…", "url": "https://www.cdc.gov/…", "domain": "cdc.gov", "trust": 5 } ],
  "retrieved_context": [ … ], "checked_in_ms": 900, "engine": "ddg-html+wikipedia" }
```

Both responses are **frozen by tests** — `backend/test_api.py::TestDetectImageContract` fails the build if a field the React app reads disappears. Both also return additive fields the UI ignores (`engine`, `signals`, `disclaimer`, `warnings`), which is how a verdict stays explainable without a frontend change.

### `GET /health` → `{ "status": "ok", "services": { … } }` (public)

### Errors
`{ "detail": "message", "error_code": "short_code" }` with `400 / 413 / 422 / 429 / 502 / 503 / 504`.
`utils/errors.js` maps each status to a user-facing message; `429` additionally starts the client cooldown.

> ⚠️ Do **not** set `Content-Type` manually when sending `FormData` — `fetch` must generate the
> multipart boundary itself, or the backend returns `422`. `api.js` handles this correctly.

---

## 8. Build & deploy

**The full, ordered, next-day-deadline walkthrough is [`docs/DEPLOY.md`](docs/DEPLOY.md).** Summary:

| Piece | Where | How |
|---|---|---|
| Backend | **Render** (free) | push to GitHub → New + → **Blueprint** → `render.yaml` does the rest |
| Frontend | **Vercel** (free) | import the repo, root `frontend`, framework Vite — auto-detected |
| Database + auth | **Supabase** (free) | SQL Editor → paste `supabase/schema.sql` → Run |

```bash
# backend, locally
cd backend && pip install -r requirements.txt
python -m uvicorn main:app --reload --port 8000     # http://127.0.0.1:8000/docs

# frontend
cd frontend && npm install && npm run dev           # http://localhost:5173

# production build
cd frontend && npm run build && npm run preview     # :4173

# tests
cd backend && python -m pytest -q                   # 57 passed
cd frontend && npm test                             # 92 passed
```

**Render specifics that break deploys if missed**

- Start command must use `--port $PORT`, never a literal port.
- `rootDir: backend` — the repo holds frontend + backend + supabase; Render must see only the Python service.
- `healthCheckPath: /health`, and `/health` must stay **public** or Render restart-loops a healthy service.
- `--workers 1`: the rate limiter is in-process. See `backend/api/rate_limit.py` before raising it.
- `FRONTEND_ORIGIN` must equal the deployed frontend origin **exactly**, or every logged-in call dies in the browser while curl keeps working.
- `VITE_*` values are inlined at **build time** — changing one on Vercel does nothing until you redeploy.

---

## 9. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Console: “Supabase is not configured” | Missing env vars | Fill in `VITE_SUPABASE_URL` + `VITE_SUPABASE_ANON_KEY`, or set `VITE_DEMO_MODE=true` |
| Dashboard: “Database objects are missing” | `schema.sql` not run | Run it in the SQL Editor, then ↻ Refresh |
| Signup succeeds but the user is always a `student` | Email confirmation ON and `set_my_role` failed | Turn confirmation OFF, or re-run `select public.set_my_role('educator')` while signed in as that user |
| `401` on every AI call after the backend adds the middleware | `SUPABASE_JWT_SECRET` mismatch | Copy the exact **JWT Secret** from Supabase → Settings → API into the backend environment |
| `422` on image upload | `Content-Type` set manually, or wrong field name | Use `services/api.js`; the field must be `file` and the header must be auto-generated |
| `403` from the AI backend as an educator | Role claim stale or missing | Sign out/in to mint a new JWT; confirm `app_metadata.role` via `jwt_role()` in the SQL Editor |
| Dashboard shows rows but “Submitted by” is blank | `educators_select_all_profiles` policy missing | Re-run `schema.sql` — the join needs read access to `profiles` |
| CORS error in the console | `FRONTEND_ORIGIN` doesn't match the browser's origin | Set it on Render to the exact deployed URL (no trailing slash), redeploy |
| Every AI call `503` | `AUTH_ENABLED=true` with no `SUPABASE_JWT_SECRET` | Fail-closed by design: set the secret, or `AUTH_ENABLED=false` to demo |
| Detection works with curl, `401` in the browser | Frontend in demo mode sends no token | `VITE_DEMO_MODE=false` + Supabase keys, redeploy, then **sign in** |
| Every fact-check returns `Unverified` | DuckDuckGo is returning HTTP 202 (bot-blocked) from the cloud IP | Check the response `warnings`; the engine falls back to Wikipedia + OpenAlex automatically |
| Render returns `502/503` | Free-tier service is asleep (cold start) | Open the `/health` URL in a tab, wait ~40 s, retry; the UI already shows a mapped message and allows retry |

---

## 10. What is intentionally *not* built (scope for the 1-week deadline)

- **Quiz generation** — the button is a stub that fires a toast (as specified). The scan-log data
  needed to generate real questions is already being collected.
- **Password reset UI** — Supabase supports it; the flow is not wired up.
- **Image storage** — only the filename is logged. Storing the images would need a Storage bucket
  plus its own RLS policies, and would raise privacy questions out of scope here.
- **A trained deepfake model in the default deployment** — the default engine is image forensics,
  because a real classifier needs ~2 GB of weights and a paid Render instance, which would make the
  graded deployment fail to boot. `DETECTION_ENGINE=transformer` is the one-env-var upgrade path
  (`backend/services/detection/transformer_engine.py`). See `docs/DEPLOY.md` §7.1 for measured results.
- **An LLM in the default fact-checker** — the keyless retrieval+scoring engine scores 7/12 on a
  claim battery and *misjudges some true claims*; that is documented rather than hidden.
  `FACT_CHECK_ENGINE=llm` with a free `GROQ_API_KEY` is the fix, and it cannot hallucinate a
  citation because URLs outside the retrieved set are discarded server-side.
- **Redis-backed rate limiting** — the limiter is in-process, correct at `--workers 1` and documented
  as per-process. Multi-worker needs `INCR` + `EXPIRE` in Redis.
- **Automated frontend tests beyond the security and interaction paths** — the **92** tests in
  `src/**/*.test.js(x)` cover the RBAC guards, validation, XSS-safe rendering, JWT attachment,
  rate-limit cooldown, audit writes, the 3D primitives and the Hick's Law screen audit. Full
  page/integration tests (Playwright/Cypress) are out of scope; the UI is covered manually by
  `docs/TESTING_CHECKLIST.md`.

---

## 11. Team split suggestion

| Person | Task | Files |
|---|---|---|
| Frontend | Pages, design system, responsive polish | `frontend/src/pages`, `components/ui.jsx` |
| Backend | **Done** — `backend/` is a complete FastAPI service; set `SUPABASE_JWT_SECRET` on Render | `backend/*`, `backend_security/*` |
| Database / Security | Run `schema.sql` + `verify.sql`, create the demo accounts, capture RLS evidence | `supabase/*`, `docs/*` |
| Report | Paste `docs/RBAC.md` §1–§6, add the `TESTING_CHECKLIST.md` screenshots | `docs/*` |

---

*Built for a college Software Engineering course. AI verdicts are probabilistic — the platform is a
teaching aid for critical thinking, not an oracle.*

##BACKEND LINK: https://truthguard-01-3.onrender.com/
##Website link:https://celadon-chebakia-798555.netlify.app/scanner
