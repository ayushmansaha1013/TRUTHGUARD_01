# Deploying TruthGuard AI — Render + Supabase + frontend

**Written for: submission tomorrow.** Follow §1 → §5 in order. Total time ~40 minutes, most of it waiting on builds.

```
┌─────────────────────┐      ┌──────────────────────┐      ┌─────────────────────┐
│  FRONTEND           │      │  BACKEND             │      │  DATABASE / AUTH    │
│  React + Vite       │─────▶│  FastAPI on Render   │      │  Supabase           │
│  Vercel / Netlify   │      │  truthguard-backend  │      │  profiles, scan_logs│
│                     │─────▶│  .onrender.com       │      │  RLS + JWT          │
└─────────────────────┘      └──────────────────────┘      └─────────────────────┘
        │                              ▲                              │
        └──────────── supabase-js session (Bearer token) ─────────────┘
                       the SAME token the backend verifies
```

Three free services, three separate URLs, no credit card.

---

## §0 — What already works, and what you still have to do

| Piece | Status |
|---|---|
| Backend API (`/health`, `/api/v1/detect-image`, `/api/v1/fact-check`) | ✅ **written, runs, 57 tests pass** |
| Deepfake detection engine (forensic heuristics) | ✅ works, no model download, verified on real images |
| Fact-checker (DuckDuckGo + Wikipedia + OpenAlex retrieval) | ✅ works, no API key — see the honest limits in §7 |
| JWT auth, rate limiting, CORS, validation, audit log | ✅ implemented and tested |
| `render.yaml` blueprint | ✅ written |
| Frontend (all screens, 3D layer, 92 tests) | ✅ done |
| Supabase schema + RLS | ✅ `supabase/schema.sql` written — **you must run it** |
| **Deploy the backend to Render** | ⬜ **§2 — you do this** |
| **Deploy the frontend** | ⬜ **§4 — you do this** |
| **Create the Supabase project** | ⬜ **§5 — you do this** |

---

## §1 — Run the whole thing locally first (5 minutes)

Do this **before** touching Render. If it works locally, a Render failure is a configuration problem, not a code problem — which is a much smaller thing to debug the night before a deadline.

**Terminal 1 — backend:**
```bash
cd backend
python -m venv .venv                     # macOS/Linux
.venv\Scripts\activate                   # Windows
# (macOS/Linux: source .venv/bin/activate)

pip install -r requirements.txt
python -m uvicorn main:app --reload --port 8000
```
Leave it running. Open **http://127.0.0.1:8000** — you should see a dark page listing the endpoints. Open **http://127.0.0.1:8000/docs** for the interactive API docs.

**Terminal 2 — frontend:**
```bash
cd frontend
npm install
npm run dev
```
Open **http://localhost:5173**. `frontend/.env` already points at `http://127.0.0.1:8000`.

**Prove it works:** Image Scanner → drop any photo → the card flips → a verdict appears. Fact-Checker → type *"Vaccines cause autism in children"* → `False` with CDC and FactCheck.org sources.

> **CORS trouble locally?** Add one line to `frontend/.env`:
> ```ini
> VITE_USE_DEV_PROXY=true
> ```
> and restart `npm run dev`. The app then calls same-origin `/api/...` and Vite forwards it to the backend, so there is no cross-origin request at all. This is **development only** — `vite preview` and static hosts don't run the proxy, so production still exercises the real CORS path (which is what you want to test before deploying, not after).

**Run both test suites:**
```bash
cd backend  && python -m pytest -q        # 57 passed
cd frontend && npm test                   # 7 files, 92 passed
cd backend_security && SUPABASE_JWT_SECRET=test-secret-only-for-local-tests python test_jwt_middleware.py   # 23/23
```

---

## §2 — Deploy the backend to Render (10 minutes)

### 2.1 Push the repo to GitHub

Render deploys *from* GitHub. If the project isn't in a repo yet:

```bash
cd truthguard-ai
git init
git add .
git commit -m "TruthGuard AI: React frontend, FastAPI backend, Supabase schema"
git branch -M main
git remote add origin https://github.com/<your-username>/truthguard-ai.git
git push -u origin main
```

**Before you push, check `.gitignore` is doing its job:**
```bash
git status --ignored | grep -E "\.env$"
```
`frontend/.env` and `backend/.env` must appear as *ignored*. If either is listed as a normal file, stop — `git rm --cached frontend/.env` and re-commit. Pushing a Supabase JWT secret to a public repo means anyone can forge a login token for your whole user base.

### 2.2 Create the service

1. Render dashboard → **New +** → **Blueprint**
2. Connect your GitHub account, pick the `truthguard-ai` repo
3. Render reads `render.yaml` and shows one service, `truthguard-backend`
4. Click **Apply** / **Create**

> **Prefer clicking through manually?** New + → **Web Service**, then set exactly:
>
> | Field | Value |
> |---|---|
> | Root Directory | `backend` |
> | Runtime | Python 3 |
> | Build Command | `pip install -r requirements.txt` |
> | Start Command | `uvicorn main:app --host 0.0.0.0 --port $PORT --workers 1` |
> | Instance Type | Free |
> | Health Check Path | `/health` |

### 2.3 Set the environment variables

Service → **Environment** tab. Four of these need *your* values:

| Key | Value | Where to get it |
|---|---|---|
| `SUPABASE_PROJECT_URL` | `https://abcdefgh.supabase.co` | Supabase → Settings → API → **Project URL** (always required) |
| `SUPABASE_JWT_SECRET` | *(secret, or blank)* | Supabase → Settings → API Keys → **JWT Signing Keys** → legacy secret. **BLANK for projects created after 1 May 2025** — those sign with RS256, verified via the public JWKS endpoint. Detection: put a real token in jwt.io and read `alg`. See **docs/SUPABASE_ENV_ELI5.md** |
| `FRONTEND_ORIGIN` | `https://truthguard-ai.vercel.app` | your deployed frontend URL (§4) |
| `AUTH_ENABLED` | `false` **for now** | flip to `true` after §5 |

Everything else already has a value in `render.yaml`.

> ⚠️ **Set `AUTH_ENABLED=false` until Supabase exists.** With it `true` and no secret configured, the backend deliberately returns **503 on every AI call** — that is the fail-closed behaviour working correctly, but it looks like a broken deployment if you aren't expecting it. Turn auth on in §5.4 once a real user can sign in.

> **Ordering tip:** you don't know your frontend URL yet. Deploy the backend first with `FRONTEND_ORIGIN=http://localhost:5173`, then come back and add the Vercel URL in §4.3. Comma-separate both.

### 2.4 Watch the build

**Logs** tab. A healthy build ends with:

```
==> Your service is live 🎉
INFO:     Uvicorn running on http://0.0.0.0:10000
INFO:     Application startup complete.
```

Render gives you `https://truthguard-backend.onrender.com` (or similar). **Copy it — you need it twice.**

### 2.5 Verify before moving on

```bash
python tools/check_backend.py https://truthguard-backend.onrender.com
```

You want:
```
[PASS] GET /health                 200
[PASS] POST /api/v1/detect-image   200 — detection works
[PASS] POST /api/v1/fact-check     200
[PASS] CORS preflight              allow-origin: …
```

> **First request may take 30–60 s.** Render's free tier spins the service down after 15 minutes idle and cold-starts it on the next request. This is normal and it is the single most likely thing to go wrong mid-presentation — see §7.

---

## §2b — Railway instead of Render (optional)

Render's free tier **suspends the service after ~15 minutes idle**, and waking it takes 30–60 s. If that risks your demo, Railway's trial plan meters usage instead of sleeping, so it stays warm.

The backend code does not change — it already binds `0.0.0.0` and reads `$PORT`, which is what every PaaS wants. `railway.yaml` is included alongside `render.yaml`. **Use one, not both.**

```bash
pip install railwayapp
railway login
cd truthguard-ai
railway up                      # or: New Project -> GitHub Repo in the dashboard
railway domain                  # gives you https://truthguard-backend-production.up.railway.app
```

Then set the same four variables (§2.3):
```bash
railway variables --set "SUPABASE_JWT_SECRET=<secret>" \
                  --set "SUPABASE_PROJECT_URL=https://<ref>.supabase.co" \
                  --set "FRONTEND_ORIGIN=https://truthguard-ai.vercel.app" \
                  --set "AUTH_ENABLED=false"
```

Verify exactly the same way — the smoke test does not care which platform hosts it:
```bash
python tools/smoke_test.py https://<your-railway-domain>.up.railway.app
```

| | Render free | Railway trial |
|---|---|---|
| Sleeps when idle | **Yes** (~15 min) → 30–60 s cold start | No |
| Limit | 750 instance-hours/month | usage-metered trial credit |
| Needs a card | No | No for the trial |
| Config file | `render.yaml` | `railway.yaml` |
| Health check | `/health` | `/health` |

> If you use Railway, remember to still set `FRONTEND_ORIGIN` — CORS is not a Render feature, it is a browser feature, and it applies identically.

---

## §3 — What the backend actually does (for your report)

| Layer | File | The security property |
|---|---|---|
| JWT verification | `backend_security/jwt_auth.py` | HS256 signature + `exp`/`iat`/`aud`/`iss`, algorithm allow-list blocks `alg=none`. **Fails closed**: no secret → 503, never open access. |
| Authorisation | `require_auth` / `require_role()` on the router | Applied at router level, so a newly added route is protected by default. |
| Validation | `backend/main.py` `_validate_upload()` | MIME **and** extension **and magic bytes**. The Content-Type header is client-controlled and cannot be trusted; the file's first bytes can. |
| Size / DoS | `config.py` | 8 MB body cap *and* a 64-megapixel decode cap, so one hostile PNG cannot OOM-kill a free instance. |
| Rate limiting | `backend/api/rate_limit.py` | Sliding window, keyed on the **JWT subject** when present so a whole college NAT doesn't share one bucket. Sends an honest `Retry-After`. |
| CORS | `backend/main.py` | Explicit allow-list from `FRONTEND_ORIGIN`. `allow_credentials=False` because we use Bearer tokens, not cookies. |
| Error contract | `backend/api/errors.py` | Every failure → `{"detail","error_code"}`. Stack traces are logged server-side, never returned. |
| Audit trail | `backend/main.py` `audit_log` | Logs who/what/status/duration. **Never** the image bytes and **never** the claim text. |
| Input sanitising | `_strip_control_chars()` | Newlines and NULs removed so a claim cannot forge audit-log lines. |

**Detection engines** (swap with one env var, no code change):

| `DETECTION_ENGINE` | What it is | Requirements |
|---|---|---|
| `heuristic` *(default)* | Image forensics: EXIF provenance, JPEG double-compression grid, sensor-noise residual, generator-typical geometry, embedded AI-tool fingerprints | Nothing. Boots in seconds. |
| `transformer` | A real Hugging Face deepfake classifier | `torch` + `transformers`, ≥4 GB RAM, paid Render instance |
| `mock` | Deterministic stub for offline rehearsal | Nothing |

**Fact-check engines:**

| `FACT_CHECK_ENGINE` | What it is | Requirements |
|---|---|---|
| `duckduckgo` *(default)* | Retrieves from DuckDuckGo → DDG Instant Answer → Wikipedia → OpenAlex, then scores evidence with negation handling and domain-trust weighting | Nothing |
| `llm` | Retrieves the same sources, then has llama-3.3-70b reason over them with citations restricted to what was actually retrieved | Free `GROQ_API_KEY` |
| `mock` | Offline knowledge base of well-documented claims with real citations | Nothing |

---

## §4 — Deploy the frontend (10 minutes)

### 4.1 Vercel (recommended)

1. vercel.com → **Add New… → Project** → import your GitHub repo
2. Vercel detects Vite automatically. Confirm:
   - **Root Directory:** `frontend`
   - **Framework Preset:** Vite
   - **Build Command:** `npm run build`
   - **Output Directory:** `dist`
3. **Environment Variables** — add before the first deploy:

   | Name | Value |
   |---|---|
   | `VITE_API_BASE_URL` | `https://truthguard-backend.onrender.com` |
   | `VITE_SUPABASE_URL` | `https://abcdefgh.supabase.co` |
   | `VITE_SUPABASE_ANON_KEY` | the **anon public** key |
   | `VITE_DEMO_MODE` | `false` |
   | `VITE_RATE_LIMIT_COOLDOWN_SECONDS` | `10` |

4. Deploy. You get `https://truthguard-ai.vercel.app`.

> **Netlify instead?** Build `npm run build`, publish `frontend/dist`. The SPA
> redirect is already handled: `frontend/public/_redirects` is copied into `dist/`
> by Vite, so deep links and refreshes work without touching `netlify.toml`.

### 4.1b Netlify Drop — no build step, no Node (fastest for a demo)

Dragging a prebuilt folder onto **app.netlify.com/drop** is the quickest way to get
a URL, but it has one property that dominates everything else: **there is no build
step and no environment-variable screen.** Vite substitutes `VITE_*` values at build
time, so whatever the build machine had is frozen into the uploaded JavaScript. A
folder built without a backend URL can never be fixed from the Netlify dashboard.

That is exactly why `frontend/public/config.js` exists — it is read by the browser at
**runtime**, so one file can be edited and re-uploaded in seconds.

**The failure this prevents.** A build with no configured URL shows the site working
perfectly — landing page, styling, Supabase login — and then, on the first AI call:

> Verification failed — Backend URL is not configured (VITE_API_BASE_URL).

Nothing is broken. The bundle simply contains an empty string where the backend
address should be.

**The fix, in order:**

1. **Have a backend URL that works.** Open `<your-backend-url>/health` in a browser
   tab. You must see `{"status":"ok",...}`. If you do not, complete **§2 (Render)**
   first — no frontend setting can compensate for a backend that is not running.
2. **Edit `config.js`** (at the root of the uploaded folder) and fill in:

   ```js
   window.__TRUTHGUARD__ = {
     apiBaseUrl: 'https://your-service.onrender.com',   // NO trailing slash, no /api/v1
     supabaseUrl: 'https://your-ref.supabase.co',
     supabaseAnonKey: 'eyJ...',                          // the anon PUBLIC key
     demoMode: false,
   }
   ```

   The `anon` key is safe to publish: it identifies the project, it does not
   authorise data access — Row Level Security in Postgres decides that. The
   `service_role` key must never appear here or anywhere a browser can read it.
3. **Re-upload the folder** (or drop `netlify-drop.zip` from the project root).
4. **Hard-refresh** the site: **Ctrl/Cmd + Shift + R**. The old bundle is cached, and
   a normal refresh can keep serving it. This step is not optional.

> **Set `apiBaseUrl` even if you also built with `VITE_API_BASE_URL`.** Runtime config
> wins, so it is the single place to look when the URL is wrong.

### 4.1c `connect-src` — the error that comes AFTER you fix the URL

`frontend/index.html` declares a Content Security Policy. Its `connect-src` directive
is an allow-list of hosts the page may send requests to, and it deliberately names
hosts individually rather than allowing all of `https:`, because that list is what
stops a successful XSS from quietly POSTing user data to an attacker's server.

The consequence is that **a backend host missing from `connect-src` is blocked by the
browser even when the URL is perfectly correct**, with a console error that looks
nothing like a configuration mistake:

> Refused to connect to 'https://your-api.onrender.com/api/v1/fact-check' because it
> violates the following Content Security Policy directive: "connect-src ..."

`*.onrender.com`, `*.up.railway.app` and `localhost:8000` are already allowed. If you
host the backend somewhere else, add it to the `connect-src` list in
`frontend/index.html` and rebuild — and use the **exact** host, since this list does
not follow redirects.

### 4.1d Why your production build cannot accidentally point at localhost

`frontend/.env` contains `VITE_API_BASE_URL=http://127.0.0.1:8000` for local
development. Left alone, `npm run build` would bake *localhost* into the deployed
bundle — meaning the visitor's own machine, so every AI call would fail with a
connection error that looks like the backend is down.

`frontend/.env.production` is loaded only by `vite build` and pins:

- `VITE_USE_DEV_PROXY=false` — this flag makes the app call same-origin `/api/*`,
  which only the **dev server** proxies. If it survives into a production build, the
  static host answers those requests itself and every AI call 404s on your own domain.
- `VITE_API_BASE_URL=` (empty) — so the backend URL is either supplied at build time
  (`VITE_API_BASE_URL=https://... npx vite build`, a real shell variable overrides
  `.env` files) or at runtime via `config.js`. Never silently localhost.

Leaving it unset is deliberate: an explicit "not configured" message is far easier to
act on than a fetch to the wrong host.

### 4.2 Rebuild if you change an env var

`VITE_*` values are **inlined into the JavaScript bundle at build time**. Changing one in the dashboard does nothing until you redeploy. This catches everyone once.

### 4.3 Close the CORS loop

Backend → Environment → `FRONTEND_ORIGIN` = `https://truthguard-ai.vercel.app` (comma-separated with `http://localhost:5173` if you still develop locally) → **Save**, which redeploys.

Then from your machine:
```bash
curl -i -X OPTIONS https://truthguard-backend.onrender.com/api/v1/detect-image \
  -H "Origin: https://truthguard-ai.vercel.app" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: authorization,content-type"
```
You need `access-control-allow-origin: https://truthguard-ai.vercel.app`. If you see the frontend's URL missing there, every logged-in call will die in the browser while curl keeps working.

---

## §5 — Supabase (10 minutes)

### 5.1 Create the project
supabase.com → **New project** → free tier → pick a region near you → set a **database password** (store it; you won't need it in the app, but Supabase asks for some operations).

### 5.2 Run the schema
**SQL Editor** → **New query** → paste the entire contents of `supabase/schema.sql` → **Run**.

Expected: `Success. No rows returned.`

Then run `supabase/verify.sql` the same way — it reports whether every table, policy, trigger and grant exists. You want all green.

What it creates:
- `profiles` (id → `auth.users`, email, role, role_locked) and `scan_logs` (append-only audit trail)
- **RLS enabled and forced**, 6 policies: students see only their own logs, educators see everyone's but cannot modify anything, users read/update only their own profile
- `handle_new_user()` trigger — creates the profile row on signup, reads the role from metadata, and downgrades to `student` on any error
- `enforce_role_immutable()` trigger — **blocks privilege escalation**. Without it, `update({role:'educator'})` from a student's browser would succeed, because RLS lets a user update their own row.
- `educator_scan_logs` view with `security_invoker=true`

### 5.3 Turn off email confirmation
**Authentication → Providers → Email** → **Confirm email: OFF** → Save.

> **Why:** with confirmation ON, a brand-new user has **no JWT until they click a link** — so they cannot call the backend *or* write to `scan_logs`, and your first demo signup appears to hang. Turning it off issues a session immediately. (This is also why `set_my_role()` exists as a write-once RPC: the role has to be chosen during signup, before any token exists.)

### 5.4 Get the keys
**Settings → API**:
- **Project URL** → `VITE_SUPABASE_URL` (frontend) and `SUPABASE_PROJECT_URL` (backend)
- **anon public** key → `VITE_SUPABASE_ANON_KEY` (frontend). Safe in a browser: RLS, not the key, protects the data.
- **JWT Secret** → `SUPABASE_JWT_SECRET` (backend only). **Never** in the frontend — with it anyone can mint a valid educator token.
- **service_role** key → **never used anywhere in this project.** It bypasses RLS entirely.

### 5.5 Turn auth on
Backend → Environment:
- `AUTH_ENABLED` = `true`
- fill in `SUPABASE_JWT_SECRET` and `SUPABASE_PROJECT_URL`
- Save (redeploys)

Frontend → Environment: `VITE_DEMO_MODE` = `false`, plus the two Supabase values → **Redeploy**.

### 5.6 Sign up twice
On the live frontend, create:
- `educator@college.edu` → role **Educator**
- `student@college.edu` → role **Student** (leave the default)

Log in as the student, run a few scans. Log out, log in as the educator: the dashboard shows that student's scans with their email, and `/scanner` is blocked with the 403 page.

> **Dashboard empty?** `schema.sql` has an optional seed block at the bottom — uncomment and run it. Or run a few scans as the student first; the dashboard reads live from `scan_logs`.

---

## §6 — Full end-to-end acceptance test

Run these in order. Every one should pass before you submit.

```bash
# 1. Backend is alive and configured
curl -s https://truthguard-backend.onrender.com/health | python -m json.tool
#    -> status ok, auth.enabled true, jwt_secret_configured true

# 2. Limits the frontend hardcodes match the server
curl -s https://truthguard-backend.onrender.com/api/v1/meta | python -m json.tool
#    -> max_image_bytes 8388608, claim 10-1000

# 3. Full diagnostic
python tools/check_backend.py https://truthguard-backend.onrender.com
#    -> all PASS

# 4. Unauthenticated calls are refused (this SHOULD fail — that's the point)
curl -s -o /dev/null -w "%{http_code}\n" -X POST \
  https://truthguard-backend.onrender.com/api/v1/fact-check \
  -H "Content-Type: application/json" -d '{"claim":"Vaccines cause autism in children"}'
#    -> 401
```

Then in the browser, on the deployed frontend:

| # | Action | Expect |
|---|---|---|
| 1 | Open `/scanner` while logged out | Redirected to `/login` |
| 2 | Sign up as a student | Lands on the dashboard/scanner, no email step |
| 3 | Upload a photo | Card flips → verdict badge + confidence ring |
| 4 | Upload a `.txt` renamed to `.jpg` | Rejected **in the browser** before upload |
| 5 | Upload a >8 MB image | Rejected in the browser with a size message |
| 6 | Fact-check *"Vaccines cause autism in children"* | `False` + clickable real sources |
| 7 | Fact-check a 5-character claim | Blocked client-side, never sent |
| 8 | Submit 20+ scans in a minute | `429` → friendly message → button locks 10 s |
| 9 | Generate Quiz | Toast: "Quiz generation coming soon" |
| 10 | Log in as the educator | Dashboard shows the student's scans with emails |
| 11 | Student visits `/dashboard` as a non-educator | 403 Access Denied page |
| 12 | DevTools → Network → any AI call | `Authorization: Bearer eyJ…` present |
| 13 | Supabase → Table Editor → `scan_logs` | One row per successful AI call |
| 14 | Render → Logs | `[audit] POST /api/v1/detect-image user=<uuid> role=student status=200` |

Items 12–14 are the ones markers ask about. Having them ready is worth more than any visual polish.

---

## §7 — Known limitations (say these before you're asked)

Being upfront about these is worth marks. Being caught out by them is not.

### 7.1 The detection engine is forensics, not a trained classifier
`DETECTION_ENGINE=heuristic` measures **physical traces** — EXIF camera provenance, JPEG double-compression grids, sensor-noise residuals, generator-typical geometry, embedded AI-tool fingerprints — and weighs them. It is not a neural network.

Measured behaviour on real generated test images:

| Image | Verdict | Why |
|---|---|---|
| Camera JPEG with EXIF + sensor noise | **Likely Real** (p=0.07) | provenance + broadband noise |
| Clean single-save JPEG | **Uncertain** (p=0.67) | only "no EXIF", which is weak |
| Re-encoded JPEG | **Likely Fake** (p=0.93) | block-grid ratio **6.9×** vs 1.2× |
| Smooth 1024×1024 PNG with alpha | **Likely Fake** (p=0.93) | every container signal at once |
| PNG with a Midjourney XMP tag | **Likely Fake** (p=0.93) | generator fingerprint |

It caps probability at 0.93 deliberately: **no heuristic is entitled to certainty.** Every response names its engine and carries a disclaimer.

**To upgrade to a real model:** add `torch transformers` to `backend/requirements.txt`, move to a paid Render instance with ≥4 GB RAM, and set `DETECTION_ENGINE=transformer`. No code changes — the engine sits behind an interface. That is the honest answer to "how would this become production-grade?"

### 7.2 The keyword fact-checker misjudges some claims
Measured on 12 claims with **no API key and no LLM**: **7 correct**.

It gets right: vaccine/autism (False, 97% confidence, CDC + FactCheck.org + The Lancet), garlic-cures-viruses, mail-voting fraud, the 10%-of-the-brain myth, the moon landing, water boiling at 100 °C, the Eiffel Tower's 1889 origin.

It gets **wrong**: *"Smoking causes lung cancer"* and *"Climate change is caused by human activity"* — both true, both scored False, because the retrieved pages are full of negations about *related* propositions ("no safe level", "not all scientists agree"). Keyword scoring cannot tell what a negation attaches to.

Three things mitigate this, and all three are in the code:
1. **Negation handling** — quoted spans are excluded from the support count, and explicit negations count as refutation. This fixed a case where a CDC snippet reading *"The claim 'vaccines do not cause autism' is not evidence-based"* was being scored as **supporting** the myth.
2. **A corroboration discount** — fewer than 4 sources caps confidence, and the explanation says so in plain words.
3. **A `CAUTION` line in the explanation** whenever the evidence base is thin.

**To fix it properly:** set `FACT_CHECK_ENGINE=llm` and add a free `GROQ_API_KEY` (console.groq.com, no card). That engine retrieves the same real sources and then has llama-3.3-70b reason over them, with any citation not present in the retrieved set **discarded before the response is built** — so it cannot hallucinate a source. This is the single highest-value change you can make with 10 minutes to spare.

### 7.3 Render's free tier sleeps
After ~15 minutes idle the service is suspended. The next request cold-starts it: **30–60 seconds**, during which the frontend shows a mapped 502/503 message.

**Before you present:** open `https://<your-backend>.onrender.com/health` in a browser tab 2–3 minutes early and keep the tab open. Re-run one scan just before you start.

### 7.4 The rate limiter is in-memory
Per-process by design; `render.yaml` pins `--workers 1` so it is correct. With multiple workers the effective limit multiplies. Moving it to Redis (`INCR` + `EXPIRE`) is the documented next step in `backend/api/rate_limit.py`.

### 7.5 DuckDuckGo rate-limits cloud IPs
Observed during development: after enough queries from one IP, `html.duckduckgo.com` starts returning **HTTP 202** with an anti-bot page and **zero results, no error**. That is why the engine has five retrieval layers and merges them — when DuckDuckGo refuses, Wikipedia and OpenAlex still answer, so the feature degrades to fewer-but-more-authoritative sources instead of failing.

If you see every claim return `Unverified` with a `ddg-html retrieval failed` warning, that is what happened. It usually clears within minutes.

---

## §8 — Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Render build fails on `pip install` | A pinned version doesn't exist for Render's Python | Check `PYTHON_VERSION` in `render.yaml` is `3.11.9`; loosen one pin at a time |
| Service boots then Render marks it unhealthy | Start command hard-codes a port | Must be `--port $PORT`, never `--port 8000` |
| Service boots, `/health` 200, but AI calls 503 | `AUTH_ENABLED=true` and the credential the token's signing scheme needs is missing | Read the `detail` — it names the missing variable. For RS256 (new projects) set `SUPABASE_PROJECT_URL`; for HS256 set `SUPABASE_JWT_SECRET`; or set `AUTH_ENABLED=false` to demo without auth |
| `401 unknown_key_id` / `invalid_signature` right after changing signing keys | The browser is still sending a token minted under the old scheme | Log out and log in to get a freshly signed token. Not a server bug |
| `503 Could not retrieve the public signing key` | Wrong `SUPABASE_PROJECT_URL`, or no outbound internet to supabase.co | Fix the URL (no trailing slash, and it must be the *same* project that issued the token) |
| Every AI call 401 in the browser, 200 with curl | Frontend still in demo mode → sends no token | `VITE_DEMO_MODE=false` + Supabase keys, redeploy, then **sign in** |
| CORS error naming `Authorization` | `allow_headers` missing it | Already set in `main.py`; check `FRONTEND_ORIGIN` matches your frontend URL exactly |
| CORS error only after login | `FRONTEND_ORIGIN` has a trailing slash or `http`/`https` mismatch | Must match the browser's origin string exactly |
| Frontend works locally, 404 on refresh when deployed | No SPA redirect rule | Vercel: automatic. Netlify: add the `netlify.toml` from §4.1 |
| Env var changed in Vercel, nothing happened | `VITE_*` is inlined at build time | **Redeploy** |
| Dashboard says "Database objects missing" | `schema.sql` never ran | SQL Editor → run it → `verify.sql` to confirm |
| Dashboard "Submitted by" column blank | Missing the educators→profiles read policy | Re-run `schema.sql`; it adds `educators_select_all_profiles` |
| Signup succeeds but nothing works | Email confirmation is ON, so no JWT exists yet | Auth → Providers → Email → **Confirm email OFF** |
| Student can make themselves an educator | `enforce_role_immutable()` trigger missing | Re-run `schema.sql` |
| Detection always "Uncertain" | Images are tiny or heavily compressed | Signals need ≥0.25 MP; the response says so in `warnings` |
| Fact-check always "Unverified" | DDG blocking the IP, or no outbound network | Check `warnings` in the response; set `FACT_CHECK_ENGINE=mock` to prove the pipeline, or add a `GROQ_API_KEY` |
| `python` not found on macOS/Linux | Not on PATH | Use `python3`; the npm scripts have `:check3` / `:mock3` variants |

---

## §9 — Submission checklist

**The night before**
- [ ] Backend live on Render, `/health` returns `ok`
- [ ] `python tools/check_backend.py <render-url>` → all PASS
- [ ] Frontend live, loads, no console errors
- [ ] `FRONTEND_ORIGIN` matches the deployed frontend URL exactly
- [ ] Supabase schema run; `verify.sql` all green
- [ ] Two accounts created (student + educator) and both can sign in
- [ ] A scan writes a row to `scan_logs`
- [ ] The educator dashboard shows that row with the student's email
- [ ] `cd backend && pytest -q` → 57 passed
- [ ] `cd frontend && npm test` → 92 passed
- [ ] `backend_security` JWT tests → 23/23
- [ ] `.env` files are **not** in the pushed repo (`git status --ignored`)
- [ ] Screenshots taken while everything works, not during the demo

**Two minutes before you present**
- [ ] Open the Render `/health` URL in a tab to wake the service
- [ ] Run one throwaway scan to warm the pipeline
- [ ] Sign in as the account you'll demo with
- [ ] Close unrelated tabs (WebGL + a cold backend on a laptop is a lot)
- [ ] Have phone-hotspot ready if the room Wi-Fi blocks `*.onrender.com`

**If everything dies in the room**
```bash
cd backend  && python -m uvicorn main:app --port 8000     # terminal 1
cd frontend && npm run dev                                # terminal 2
```
`.env` already points at `127.0.0.1:8000`, so the whole product runs offline from your laptop. Detection needs no network at all; set `FACT_CHECK_ENGINE=mock` if the room has no internet.

---

## §10 — Where everything is

```
truthguard-ai/
├── backend/                     ← NEW: the FastAPI service you deploy to Render
│   ├── main.py                     routes, validation, CORS, audit log
│   ├── config.py                   every tunable, from env vars
│   ├── schemas.py                  the frozen response contract
│   ├── api/errors.py               one error shape for every failure
│   ├── api/rate_limit.py           sliding-window limiter (Part C.3)
│   ├── services/detection/         heuristic | transformer | mock engines
│   ├── services/factcheck/         duckduckgo+wiki+openalex | llm | mock engines
│   ├── test_api.py                 57 contract tests
│   ├── requirements.txt            runtime deps
│   ├── requirements-dev.txt        pytest
│   ├── Procfile / runtime.txt      platform fallbacks
│   └── .env.example                local config shape (no secrets)
├── render.yaml                  ← Render Blueprint
├── backend_security/            ← Part C.1 deliverable (jwt_auth.py, 23 tests)
├── frontend/                    ← React + Vite + Tailwind, 92 tests
├── supabase/schema.sql          ← Part B: tables, RLS, triggers, grants
├── supabase/verify.sql          ← confirms the schema applied
├── tools/check_backend.py       ← run this first when anything fails
├── tools/mock_backend.py        ← standalone mock, for offline rehearsal
└── docs/
    ├── DEPLOY.md                ← this file
    ├── RUNNING_LOCALLY.md          laptop setup
    ├── WHY_NOT_DETECTING.md        decision tree for a failing backend
    ├── RBAC.md                     Part C.7 three-layer summary
    ├── HICKS_LAW.md                design rationale
    └── TESTING_CHECKLIST.md        manual test plan
```
