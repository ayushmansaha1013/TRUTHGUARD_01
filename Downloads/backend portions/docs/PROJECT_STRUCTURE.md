# Project Structure — TruthGuard AI

Complete file-by-file map of the delivered project. **104 files, ~17 200 lines**
(16 900 hand-written, plus a generated lockfile).

Every folder has one job. This document explains what that job is, and which file
satisfies which requirement of the brief.

---

## 1. Top level — the 30-second view

```
truthguard-ai/
│
├── frontend/            PART A + PART C (client) — React + Vite + Tailwind UI
├── backend/             PART A (server) — the deployable FastAPI service
├── backend_security/    PART C.1 — standalone JWT/RBAC deliverable for the report
├── supabase/            PART B — the SQL script + its verification script
├── tools/               Developer/demo utilities (diagnose, mock, end-to-end test)
├── docs/                Report material and operating instructions (9 documents)
│
├── render.yaml          One-click deploy config for Render  (primary)
├── railway.yaml         Alternative deploy config for Railway (never sleeps)
├── README.md            Project overview, quick start, feature/requirement map
└── .gitignore           Keeps secrets (.env) and artifacts (node_modules) out of git
```

**Why the split:** the four graded parts map onto four folders, so a marker can be
pointed at one directory per requirement. `docs/` is deliberately separate from code
so the written deliverables (RBAC summary, testing checklist, SQL script) can be
lifted into the report without reading source.

---

## 2. `frontend/` — Part A + client-side Part C

```
frontend/
├── index.html                     Vite entry; sets the page title + font preconnect
├── package.json                   Dependencies (react, react-router-dom, supabase-js, three) + scripts
├── package-lock.json              Generated — exact dependency tree, 5 020 lines
├── vite.config.js                 Build config + the dev-only /api proxy to :8000
├── tailwind.config.js             The design system as code: colours, radii, fonts
├── postcss.config.js              Wires Tailwind into the Vite pipeline
├── netlify.toml                   Netlify build config + SPA redirect (harmless on Vercel)
├── .env / .env.example            VITE_* variables; .env is gitignored (example is committed)
│
├── public/
│   └── favicon.svg                Inline SVG logo — no external asset dependency
│
└── src/
    ├── main.jsx                   React root; mounts <App/>, imports global CSS
    ├── App.jsx                    React Router route table + auth/role guards
    ├── index.css                  Tailwind directives + global base styles
    │
    ├── styles/
    │   └── 3d.css                 All 3D/interaction CSS: perspective, tilt, spotlight,
    │                              reveal, reduced-motion overrides (578 lines)
    │
    ├── pages/                     One file per screen (9)
    │   ├── Landing.jsx            Hero + WebGL scene; Hick's Law: 1 primary CTA + 1 ghost
    │   ├── Login.jsx              Email/password sign-in
    │   ├── Signup.jsx             Sign-up with Student|Educator role select (pre-selected)
    │   ├── ImageScanner.jsx       Drag-drop upload → POST /detect-image → verdict + gauge
    │   ├── FactChecker.jsx        Claim input → POST /fact-check → verdict, explanation, sources
    │   ├── EducatorDashboard.jsx  Stat cards (that double as filters) + recent-flagged table
    │   ├── AccessDenied.jsx       The 403 page for a student reaching an educator route
    │   ├── NotFound.jsx           The 404 page
    │   └── Signup.test.jsx        Locks in the Hick's Law decisions (role defaulted, 2 fields)
    │
    ├── components/                Reusable UI (12 + 3 test files)
    │   ├── ui.jsx                 Primitives: Button, Card, Badge, Input, Spinner, SafeLink…
    │   ├── Navbar.jsx             Top nav; renders different items per role
    │   ├── AuthLayout.jsx         Shared two-column shell for /login and /signup
    │   ├── FileDropzone.jsx       Drag-drop + click upload; pre-validates type and size
    │   ├── ProtectedRoute.jsx     Part C.7 — redirects to /login when there is no session
    │   ├── EducatorRoute.jsx      Part C.7 — renders the 403 page for non-educators
    │   ├── Toast.jsx              Toast system; used for "Quiz generation coming soon"
    │   ├── FullPageLoader.jsx     Shown while Supabase restores a session
    │   ├── AmbientBackground.jsx  Fixed decorative depth layer behind the whole app
    │   ├── ScrollProgress.jsx     2px teal reading-progress bar
    │   ├── ui.test.jsx            Tests the primitives
    │   └── guards.test.jsx        Tests that the two route guards actually guard
    │
    ├── components/interactive/    The CSS-3D interaction layer (7 + 1 test)
    │   ├── TiltCard.jsx           Pointer-tracked 3D tilt (max 9°, 900px perspective)
    │   ├── SpotlightCard.jsx      Radial highlight following the cursor
    │   ├── ScrollReveal.jsx       IntersectionObserver entrance animation
    │   ├── MagneticButton.jsx     Button that leans toward the cursor
    │   ├── CountUp.jsx            Animates a number from 0 to its value
    │   ├── ConfidenceRing.jsx     SVG ring gauge; role="progressbar" for screen readers
    │   ├── VerdictFlip.jsx        3D flip card revealing the verdict
    │   └── interactive.test.jsx   Tests all seven, incl. reduced-motion behaviour
    │
    ├── components/three/          The real-WebGL layer (2)
    │   ├── Hero3D.jsx             Three.js hero scene; lazy-loaded so it isn't in the main bundle
    │   └── Hero3DFallback.jsx     Static CSS hero for no-WebGL / reduced-motion / slow network
    │
    ├── services/                  All I/O lives here — pages never call fetch directly
    │   ├── api.js                 Part A — the 3 backend calls + Bearer token + 429 cooldown
    │   ├── supabaseClient.js      Part B — supabase-js client + session management
    │   ├── scanLog.js             Part B/C — writes every successful AI call to scan_logs
    │   ├── api.test.js            23 tests: auth header, error mapping, no manual Content-Type
    │   └── scanLog.test.js        Tests the audit-trail writes
    │
    ├── context/
    │   └── AuthContext.jsx        Part B — session, user, role; single source of truth
    │
    ├── hooks/
    │   └── useRateLimitCooldown.js Part C.3 — exposes the 10 s client-side cooldown
    │
    └── utils/
        ├── validation.js          Part C.2 — jpg/png/webp, <8 MB, claim 10–1000 chars
        ├── errors.js              Maps {detail, error_code} → friendly human text
        ├── webgl.js               Capability detection so the 3D layer degrades gracefully
        └── validation.test.js     Tests every boundary in the validation rules
```

**Conventions that matter:**
- `services/` is the only place that performs I/O. Pages stay presentational, which is
  why the error-mapping logic is testable in isolation.
- Every screen has a matching guard or test file, so behaviour is locked in rather
  than trusted.

---

## 3. `backend/` — the deployable FastAPI service

```
backend/
├── main.py                     App assembly: CORS, middleware, routers, error handlers,
│                               audit log, /health and /api/v1/meta (667 lines)
├── config.py                   Every tunable read once from the environment (149)
├── schemas.py                  Pydantic models — the response contract, enforced (112)
├── test_api.py                 57 pytest tests, in-process, no network (1 048)
├── requirements.txt            Runtime dependencies, all pinned
├── requirements-dev.txt        pytest only — deliberately not installed in production
├── runtime.txt                 python-3.11.9, kept in step with render.yaml
├── Procfile                    web: uvicorn … --port $PORT  (fallback for Railway/Heroku)
├── .env / .env.example         Local config; .env gitignored, example committed
├── .gitignore                  Belt-and-braces .env protection at the folder level
│
├── api/
│   ├── errors.py               Normalises every failure to {detail, error_code};
│   │                           drops Pydantic's `input` field so submitted text is
│   │                           never echoed back (152)
│   └── rate_limit.py           Fixed-window limiter on the AI routes only; skips
│                               OPTIONS; keyed on the JWT subject (170)
│
└── services/
    ├── detection/              The image-forensics engines
    │   ├── base.py             Engine interface + registry; selects one by env var
    │   ├── heuristic.py        DEFAULT. EXIF, AI metadata fingerprints, JPEG block-grid
    │   │                       periodicity, noise/ELA residuals → probability (415)
    │   ├── transformer_engine.py  Optional real classifier (needs torch) — off by default
    │   └── mock_engine.py      Deterministic engine for tests and offline demos
    │
    └── factcheck/              The claim-verification engines
        ├── base.py             Retrieval interface + the verdict scorer, incl. negation
        │                       handling and a corroboration discount (410)
        ├── duckduckgo_engine.py DEFAULT. Five keyless retrieval layers merged: DDG HTML,
        │                       DDG Instant Answer, Wikipedia action API, OpenAlex,
        │                       Wikipedia full-text (565)
        ├── llm_engine.py       Optional; reads only from the retrieved set, and discards
        │                       citations it did not retrieve (224)
        └── mock_engine.py      Offline knowledge base of documented claims (225)
```

**Two patterns carry the whole backend:**
1. **Strategy pattern.** The brief fixes the *response contract*, not the model. Each
   capability is an interface with swappable implementations chosen by an env var, so
   `DETECTION_ENGINE=transformer` upgrades the product without touching a route.
2. **Fail closed.** Auth, rate limiting and validation all reject by default; a
   missing secret returns 503 rather than silently serving unprotected endpoints.

---

## 4. `backend_security/` — Part C.1, the standalone deliverable

```
backend_security/
├── jwt_auth.py                 The JWT middleware snippet the brief asks for (581).
│                               FastAPI Depends()-based; verifies HS256 (legacy) AND
│                               RS256/ES256 (Supabase's current default) via JWKS.
│                               Written as a drop-in plus integration notes.
├── integration_example.py      A minimal FastAPI app showing the 3 edits needed to
│                               wire the middleware in — not part of the deployed
│                               service, purely so the snippet is provably runnable (261)
├── test_jwt_middleware.py      23 checks: forged, expired, tampered, foreign-audience,
│                               algorithm-confusion, role escalation, 401 vs 403 (179)
├── test_asymmetric_jwks.py     25 checks: real RSA keypair, real JWKS server, real
│                               signatures, the algorithm-confusion attack with a
│                               hand-rolled HMAC signature + controls (433)
└── requirements.txt            pyjwt[crypto] + httpx, listed separately so the marker
                                can install just this piece
```

**Why this folder exists separately:** the brief asks for *"the Python JWT middleware
snippet"* as a deliverable. Extracting it means the report can show the middleware and
its evidence without wading through the whole backend — but it is the *same file* the
deployed `backend/main.py` imports, so it cannot drift out of sync with reality.

---

## 5. `supabase/` — Part B

```
supabase/
├── schema.sql                  The complete SQL script the brief asks for (433):
│                               · pgcrypto + user_role enum (student|educator)
│                               · profiles  (id → auth.users CASCADE, email, role,
│                                 role_locked) and scan_logs (identity PK, user_id
│                                 SET NULL, content_type CHECK, verdict, confidence)
│                               · RLS ENABLED and FORCED on both tables
│                               · 6 policies — students insert/view own logs; educators
│                                 view all and may not modify; users read/update own profile
│                               · SECURITY DEFINER functions with a pinned search_path:
│                                 handle_new_user() trigger, current_user_role(),
│                                 jwt_role(), set_my_role() (write-once),
│                                 enforce_role_immutable()
│                               · educator_scan_logs view with security_invoker = true
│
└── verify.sql                  Run after schema.sql to PROVE the posture (101):
                                checks RLS is forced, policies exist, role escalation is
                                blocked, and logs are append-only. Output doubles as
                                report screenshots.
```

Three real bugs were found and fixed in this schema, all documented inline: the
educator view used to hide profiles, `role` was client-writable (privilege escalation),
and React does not escape `href` (fixed with an allow-list `SafeLink`).

---

## 6. `tools/` — diagnose, mock, and prove

```
tools/
├── check_backend.py            **Run first when detection does nothing.** Diagnoses
│                               the backend URL, routes, CORS, auth and rate limits
│                               in one command and prints what to fix (367)
├── mock_backend.py             Contract-accurate mock backend, stdlib only. Lets the
│                               whole UI work offline, before the real model is
│                               deployed — and is a fallback if the venue has no Wi-Fi (510)
└── smoke_test.py               30 live end-to-end checks over real HTTP against
                                localhost OR a deployed URL. Generates its own test
                                images (hand-rolled PNG builder, no Pillow needed) and
                                covers the contract, discrimination in both directions,
                                upload validation, CORS, rate limiting and secret
                                leakage (622)
```

---

## 7. `docs/` — the written deliverables

```
docs/
├── DEPLOY.md                   **Start here.** Render (§2) and Railway (§2b) walkthroughs,
│                               security/engine tables, frontend hosting (§4), Supabase
│                               setup (§5), the 14-point acceptance test (§6), known
│                               limitations (§7), troubleshooting (§8), checklists (§9)
├── SUPABASE_ENV_ELI5.md        Plain-language answer to "what do I put in
│                               SUPABASE_JWT_SECRET?" — incl. why it may need to be
│                               BLANK, how to identify your project's signing scheme in
│                               30 s, and an error→cause table
├── TESTING.md                  All 6 test layers, what each can and cannot see, a real
│                               30/30 smoke-test transcript, and the algorithm-confusion
│                               attack writeup
├── TESTING_CHECKLIST.md        Manual test plan — the brief's required deliverable —
│                               incl. the RLS-bypass proofs and a screenshot list
├── API_REFERENCE.md            Every endpoint, all 12 error codes and what the UI does
│                               for each, every env var, all supabase-js calls, package
│                               lists, ports. Headline: zero third-party API keys needed
├── RBAC.md                     Paste-ready report section — RBAC at three layers (C.7)
├── HICKS_LAW.md                Paste-ready report section — the Hick's Law audit of every
│                               screen and the interaction-design rationale
├── RUNNING_LOCALLY.md          Laptop setup from a blank machine, with troubleshooting
├── WHY_NOT_DETECTING.md        Decision tree for "the backend isn't answering"
└── PROJECT_STRUCTURE.md        This document
```

---

## 8. Root configs

| File | Purpose | Notes |
|---|---|---|
| `render.yaml` | Render blueprint: service, start command, health check, env vars | Primary deploy target |
| `railway.yaml` | Railway: Nixpacks build, `rootDir: backend`, health check | Use **instead of** `render.yaml`, not both. Railway does not sleep |
| `README.md` | Overview, quick start, requirements map, design rationale | 586 lines — the report's front page |
| `.gitignore` | Excludes `.env`, `node_modules/`, `dist/`, caches | Secrets and artifacts verified absent from all commits |

---

## 9. Where each requirement lives

| Brief requirement | Primary file(s) |
|---|---|
| **A** Landing / Login / Signup + role select | `frontend/src/pages/{Landing,Login,Signup}.jsx` |
| **A** Image Scanner, drag-drop, gauge, verdict badge | `pages/ImageScanner.jsx`, `components/FileDropzone.jsx`, `components/interactive/ConfidenceRing.jsx` |
| **A** Fact-Checker chat, animated dots, clickable sources | `pages/FactChecker.jsx`, `pages/FactChecker.jsx` ✓ |
| **A** Educator Dashboard, stat cards, flagged table | `pages/EducatorDashboard.jsx` |
| **A** "Generate Quiz" stub → toast | `pages/EducatorDashboard.jsx` + `components/Toast.jsx` |
| **A** React Router, `.env`, 429/502 handling | `App.jsx`, `services/api.js`, `utils/errors.js` |
| **A** Design system (colours, radii, fonts) | `tailwind.config.js`, `styles/3d.css` |
| **A** Backend serving both AI endpoints | `backend/main.py`, `backend/services/**` |
| **B** `profiles` + `scan_logs` + RLS + trigger | `supabase/schema.sql` |
| **B** supabase-js session management | `services/supabaseClient.js`, `context/AuthContext.jsx` |
| **B** `ProtectedRoute` + `EducatorRoute` (403) | `components/ProtectedRoute.jsx`, `components/EducatorRoute.jsx`, `pages/AccessDenied.jsx` |
| **B** Log every successful AI call | `services/scanLog.js` |
| **C.1** JWT Bearer + `Depends()` middleware | `backend_security/jwt_auth.py` |
| **C.2** Frontend validation (type, 8 MB, 10–1000) | `utils/validation.js` |
| **C.3** 429 → friendly message + 10 s cooldown | `services/api.js`, `hooks/useRateLimitCooldown.js`, `backend/api/rate_limit.py` |
| **C.4** `.env` / `.env.example` / `.gitignore` | Both `backend/` and `frontend/`, plus root `.gitignore` |
| **C.5** XSS prevention | `components/ui.jsx` (`SafeLink` allow-list), `schemas.py` |
| **C.6** Audit trail | `main.py` audit middleware, `services/scanLog.js`, `scan_logs` table |
| **C.7** RBAC (3 layers) | `components/*Route.jsx` → `supabase/schema.sql` → `jwt_auth.py` |
| **C** SQL script deliverable | `supabase/schema.sql` |
| **C** JWT middleware snippet deliverable | `backend_security/jwt_auth.py` |
| **C** Testing checklist deliverable | `docs/TESTING_CHECKLIST.md` |

---

## 10. How it all connects at runtime

```
                       ┌──────────────────────────────────────────┐
   Browser             │  React SPA (Vercel / Netlify / localhost) │
   (the user)          │   pages/ → services/api.js               │
                       └───────────────┬──────────────────────────┘
                                       │
                    1. sign up / in    │  2. AI request
                       (supabase-js)   │     Authorization: Bearer <JWT>
                                       ▼
        ┌────────────────────────────────────────────┐   ┌──────────────────────┐
        │  Supabase (auth + Postgres + RLS)          │   │  FastAPI (Render)    │
        │   · issues the JWT                         │   │  1. rate_limit.py    │
        │   · profiles / scan_logs, RLS enforced     │◄──┤  2. jwt_auth.py ✓    │
        │   · handle_new_user() creates the profile  │   │  3. validate         │
        │   · scanLog.js writes the audit trail      │   │  4. engine (detect / │
        └────────────────────────────────────────────┘   │     fact-check)      │
                                                          │  5. log, respond     │
                             ┌────────────────────────────┤──────────────────────┘
                             │  Outbound, ALL keyless     │
                             │   · DuckDuckGo             │
                             │   · Wikipedia action API   │
                             │   · OpenAlex               │
                             └────────────────────────────┘
```

The JWT is verified **twice, independently**: once by Supabase when the frontend talks
to the database (RLS), and once by FastAPI when a scan is submitted. Neither trusts
the other. The role is read from the token's `app_metadata`, which a client cannot
write — and defaults to `student` if it is missing or unrecognised.

---

## 11. Scale

| Area | Files | Lines |
|---|---|---|
| `frontend/src` | 46 | 6 875 |
| `backend` | 19 | 4 498 |
| `docs` | 10 | 2 299 |
| `tools` | 3 | 1 499 |
| `backend_security` | 4 | 1 454 |
| `supabase` | 2 | 534 |
| **Total (hand-written)** | **~87** | **~17 200** |

**Tests: 197 automated + 14 manual browser checks**

| Suite | Location | Count |
|---|---|---|
| Backend API | `backend/test_api.py` | 57 |
| Auth/RBAC, legacy HS256 | `backend_security/test_jwt_middleware.py` | 23 |
| Auth/JWKS, asymmetric RS256 | `backend_security/test_asymmetric_jwks.py` | 25 |
| Frontend | 7 files in `frontend/src/**/*.test.jsx?` | 92 |
| Live end-to-end (real HTTP) | `tools/smoke_test.py` | 30 |
| Manual acceptance | `docs/DEPLOY.md` §6 | 14 |
