# Every API this project needs

Three questions answered: **what the backend exposes**, **what it calls out to**, and **what you must sign up for**.

> **Headline: the default configuration needs ZERO third-party API keys.** No OpenAI, no Google, no card. Detection runs on local image forensics; fact-checking uses keyless public endpoints. The only accounts you create are the three free hosts (Render, Vercel, Supabase).

---

## 1 — The backend's own HTTP API

Base URL: `VITE_API_BASE_URL` → e.g. `https://truthguard-backend.onrender.com`

| Method | Path | Auth | Rate-limited | Called by |
|---|---|---|---|---|
| `GET` | `/` | public | no | a human opening the URL |
| `GET` | `/health` | **public** | no | Render's health check, `tools/check_backend.py`, `getHealth()` |
| `GET` | `/api/v1/meta` | **public** | no | diagnostics; advertises the limits the UI hardcodes |
| `POST` | `/api/v1/detect-image` | **Bearer JWT** | yes | `detectImage(file)` — Image Scanner |
| `POST` | `/api/v1/fact-check` | **Bearer JWT** | yes | `factCheck(claim)` — Fact Checker |
| `GET` | `/docs` | public | no | you, during development (Swagger UI) |
| `OPTIONS` | any of the above | public | no | the browser's CORS preflight |

`/health` is deliberately public and deliberately **not** rate-limited: Render probes it to decide whether the deploy succeeded, and if it required a token the platform would restart-loop a healthy service.

### `POST /api/v1/detect-image`

**Request** — `multipart/form-data`, and the field name must be exactly `file`:

```
Content-Disposition: form-data; name="file"; filename="photo.jpg"
Content-Type: image/jpeg
```

| Constraint | Value | Enforced by |
|---|---|---|
| Allowed types | `image/jpeg`, `image/png`, `image/webp` | server **and** browser |
| Max size | 8 MB (8388608 bytes) | server **and** browser |
| Max pixels | 64 MP | server only — a decompression-bomb guard |
| Type check | **magic bytes**, not the `Content-Type` header | server |

> ⚠️ Do **not** set `Content-Type` yourself when sending `FormData`. `fetch` must generate the multipart boundary (`----WebKitFormBoundary…`); setting it manually corrupts the body and yields a `422`. `services/api.js` already handles this.

**Response 200** — the six frozen fields the React app reads, plus additive extras it ignores:

```json
{
  "verdict": "Likely Fake",
  "confidence": 93.0,
  "raw_label": "fake",
  "fake_probability": 0.93,
  "is_fake": true,
  "analyzed_in_ms": 41,

  "engine": "heuristic-forensics",
  "image": { "format": "PNG", "mode": "RGBA", "width": 512, "height": 512,
             "megapixels": 0.26, "bytes": 51209, "filename": "generated.png",
             "sha256_prefix": "9f2c…" },
  "signals": {
    "generator_square": "512x512 is a model-native resolution",
    "has_alpha": "alpha channel present (mode RGBA) — cameras do not emit these",
    "png_photo": "photographic content stored as PNG (lossless) is atypical",
    "no_exif": "no camera EXIF (Make/Model). Common for shared images — weak signal only.",
    "smooth_residual": { "looks_synthesised": true, "highpass_energy": 0.09,
                         "spatial_uniformity": 0.273, "reading": "…" },
    "jpeg_grid": { "boundary_ratio": 2.31, "strength": 0.9, "reading": "…" }
  },
  "warnings": [],
  "disclaimer": "Heuristic forensic analysis … NOT a trained deepfake classifier …"
}
```

`verdict` is always one of `Likely Fake` · `Uncertain` · `Likely Real` → the red / yellow / green badge.
`confidence` is `50 + |p − 0.5| × 100`, so it answers "how sure?" not "how fake?" — a p of 0.02 and a p of 0.98 both read as high confidence.
`is_fake` is always exactly `verdict === "Likely Fake"`, so the badge colour and the orb pulse can never disagree.

### `POST /api/v1/fact-check`

**Request**
```json
{ "claim": "Vaccines cause autism in children" }
```
10–1000 characters, enforced identically on the server and in the browser. Control characters (including newlines) are stripped **before** the length check, so padding cannot sneak an empty claim past.

**Response 200**
```json
{
  "verdict": "False",
  "explanation": "Claim assessed: \"Vaccines cause autism in children\" Across 6 retrieved source(s): 0.7 weighted supporting signal(s), 26.7 refuting (including explicit negations such as 'there is no evidence'), 0.0 hedging. Quoted claims were excluded from the supporting count. Strongest source: cdc.gov (high-trust, trust 5/5). Verdict: False. …",
  "sources": [
    { "title": "Debunking False Vaccine Claim - FactCheck.org",
      "url": "https://www.factcheck.org/2017/11/debunking-false-vaccine-claim/",
      "snippet": "…the myth that vaccines cause autism…",
      "domain": "factcheck.org", "trust": 5,
      "support_hits": 0, "refute_hits": 6, "hedge_hits": 0, "score": 1.0 }
  ],
  "retrieved_context": [ { "text": "…", "score": 1.0, "source": "https://…" } ],
  "checked_in_ms": 1498,

  "claim": "Vaccines cause autism in children",
  "engine": "ddg-html+wikipedia",
  "confidence": 97.3,
  "warnings": [],
  "disclaimer": "Verdict derived from keyword-evidence scoring over retrieved web sources…"
}
```

`verdict` is one of `True` · `Mostly true` · `Mixed` · `Unverified` · `Mostly false` · `False`.
`sources[].url` is always `http(s)` — filtered server-side **and** again by the frontend's `<SafeLink>`, two independent layers.

### Errors — one shape, always

```json
{ "detail": "Image is 9.3 MB; the limit is 8 MB. Please upload a smaller file.",
  "error_code": "payload_too_large" }
```

| Status | `error_code` | Meaning | Frontend behaviour |
|---|---|---|---|
| 400 | `bad_request` · `empty_file` · `undecodable_image` · `invalid_json` | malformed request | error banner |
| 401 | `missing_token` · `invalid_scheme` · `token_expired` | no/invalid JWT | "Please sign in again" |
| 403 | `insufficient_role` | student hit an educator route | 403 Access Denied page |
| 404 | `not_found` | wrong path | error banner |
| 413 | `payload_too_large` | over 8 MB | "Image is too large" |
| 415 | `unsupported_media_type` | not jpg/png/webp, **or bytes disagree with the header** | "Only JPG, PNG and WebP" |
| 422 | `validation_error` · `missing_claim` · `claim_too_short` · `claim_too_long` | field-level rejection | inline field error |
| 429 | `rate_limited` | over 20 AI calls/minute | friendly message **+ 10 s cooldown**, sized from `Retry-After` |
| 500 | `internal_error` | our bug | "Something went wrong" — details logged server-side only |
| 502 | `retrieval_failed` · `bad_gateway` | an **upstream** dependency failed | "Try again shortly" |
| 503 | `service_unavailable` | model unavailable, or **fail-closed auth** | "Service unavailable" |
| 504 | `gateway_timeout` | upstream timed out | "Took too long, try again" |

FastAPI produces four *different* error shapes by default (`RequestValidationError` gives a list of dicts, `HTTPException` a bare string, Starlette's own give HTML). `api/errors.py` normalises all of them, and strips `input` from validation errors so a user's own submitted value is never echoed back.

### Auth header

```
Authorization: Bearer <supabase access token>
```

The token comes from the Supabase session — `supabase.auth.getSession()`. It is **never** stored in `localStorage` by this app; supabase-js owns it. A fresh token is fetched per request so an expired one can't be replayed.

---

## 2 — External APIs the backend calls

All optional except Supabase, and **none need a key** in the default configuration.

| Service | URL | Key? | Used for | Failure mode |
|---|---|---|---|---|
| DuckDuckGo search | `html.duckduckgo.com/html/` | **No** | primary web retrieval | Returns **HTTP 202** with zero results when it bot-blocks a cloud IP. Layer 1 (`ddgs` package) usually works first. |
| DuckDuckGo Instant Answer | `api.duckduckgo.com/?format=json` | **No** | entity abstracts + related topics | Empty for non-entity claims |
| Wikipedia (action API) | `en.wikipedia.org/w/api.php` | **No** | the reliability floor: search + full lead extract | Very stable; asks for a descriptive User-Agent, which we send |
| OpenAlex | `api.openalex.org/works` | **No** | peer-reviewed literature, with DOIs | Occasional empty abstracts |
| Groq *(optional)* | `api.groq.com/openai/v1/chat/completions` | **Free key** | `FACT_CHECK_ENGINE=llm` | Falls back to keyword scoring if the key is missing |
| Hugging Face Hub *(optional)* | model download | No key for public models | `DETECTION_ENGINE=transformer` | Needs ≥4 GB RAM + a paid Render instance |
| Supabase | `https://<ref>.supabase.co` | anon key (public by design) | auth + `profiles` + `scan_logs` | App runs in demo mode without it |

**Why five retrieval layers:** free search endpoints are the least stable part of any stack — `duckduckgo_search` was literally renamed to `ddgs` mid-project, and DuckDuckGo bot-blocks cloud IP ranges. The engine tries `ddgs` → `duckduckgo_search` → HTML scrape → Instant Answer → Wikipedia → OpenAlex, **merges** what comes back, and only then judges. When DuckDuckGo refuses, you get fewer-but-more-authoritative sources instead of a dead feature.

---

## 3 — Supabase: the exact calls the frontend makes

| Call | Where | Purpose |
|---|---|---|
| `supabase.auth.signUp({ email, password, options:{ data:{ role } } })` | `Signup.jsx` | create the user; the role travels in metadata and `handle_new_user()` writes the profile row |
| `supabase.auth.signInWithPassword({ email, password })` | `Login.jsx` | session + the JWT the backend verifies |
| `supabase.auth.getSession()` | `api.js` | a fresh access token **per request** |
| `supabase.auth.getUser()` | `AuthContext` | validate the session on load |
| `supabase.auth.onAuthStateChange(cb)` | `AuthContext` | react to sign-in/out without a refresh |
| `supabase.auth.signOut()` | `Navbar` | end the session |
| `.rpc('set_my_role', { p_role })` | `Signup.jsx` | write-once role selection. **Needed because with email confirmation ON a new user has no JWT yet**, so RLS would block a direct update |
| `.from('scan_logs').insert({...})` | `scanLog.js` | the audit trail, after every successful AI call |
| `.from('scan_logs').select(...)` | `EducatorDashboard.jsx` | the recent-flagged table |
| `.from('profiles').select(...).update(...)` | `AuthContext` | read/update own profile |
| `educator_scan_logs` view | `EducatorDashboard.jsx` | class-wide history with `user_email` and `user_role` |

**Backend → Supabase:** none. The backend never talks to your database. It only *verifies the JWT* Supabase issued, using `SUPABASE_JWT_SECRET`. That is why a leaked anon key cannot read another user's data (RLS blocks it) and why the backend needs no database credentials at all.

---

## 4 — Every environment variable

### Backend (Render → Environment tab)

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `SUPABASE_JWT_SECRET` | **Yes** if `AUTH_ENABLED=true` | *(empty)* | Verifies tokens. **Server-side only — never in the frontend.** |
| `SUPABASE_PROJECT_URL` | Yes, with auth | *(empty)* | Validates the token's `iss` claim |
| `AUTH_ENABLED` | — | `true` | **Fails closed**: `true` with no secret → 503 on every AI call, never open access |
| `FRONTEND_ORIGIN` | **Yes** in production | localhost:5173/4173 | The CORS allow-list. Must match the browser's origin **exactly** |
| `DETECTION_ENGINE` | — | `heuristic` | `heuristic` · `transformer` · `mock` |
| `TRANSFORMER_MODEL` | — | `swinv2/Detect-fake-images-cifarSwinV2` | only with `transformer` |
| `FACT_CHECK_ENGINE` | — | `duckduckgo` | `duckduckgo` · `llm` · `mock` |
| `GROQ_API_KEY` | only for `llm` | *(empty)* | free at console.groq.com |
| `GROQ_MODEL` | — | `llama-3.3-70b-versatile` | |
| `RATE_LIMIT_ENABLED` | — | `true` | |
| `RATE_LIMIT_PER_MINUTE` | — | `20` | Per **JWT subject**, not per IP |
| `FACT_CHECK_TIMEOUT` | — | `15` | seconds per upstream call |
| `DEMO_MODE` | — | `false` | adds `_mock: true` to responses |
| `PORT` | injected | `8000` | **Render sets this.** Never hard-code it |
| `PYTHON_VERSION` | — | `3.11.9` | pinned in `render.yaml` |
| `PYTHONUNBUFFERED` | — | `1` | without it your `[audit]` lines appear in the log minutes late |

### Frontend (Vercel/Netlify → Environment)

| Variable | Purpose |
|---|---|
| `VITE_API_BASE_URL` | your Render URL. **No trailing slash, no path.** |
| `VITE_SUPABASE_URL` | Project URL |
| `VITE_SUPABASE_ANON_KEY` | the **anon public** key. Never `service_role`. |
| `VITE_DEMO_MODE` | `true` = offline demo, pre-authenticated as an educator. `false` = real auth + RLS |
| `VITE_RATE_LIMIT_COOLDOWN_SECONDS` | `10` — how long the button locks after a 429 |
| `VITE_USE_DEV_PROXY` | **dev only.** `true` makes the app call same-origin `/api/*`, which Vite forwards to the backend — no CORS at all. Delete before deploying. |

> **Why the `VITE_` prefix matters:** Vite inlines every `VITE_*` value into the browser bundle at **build time**. Anything else in `.env` stays invisible to the app. That's the safety property — but it also means **changing one on Vercel does nothing until you redeploy.** This catches everyone once.

---

## 5 — npm / pip packages

### `backend/requirements.txt`
```
fastapi==0.115.6          uvicorn[standard]==0.34.0
python-multipart==0.0.20  pydantic==2.10.4
PyJWT==2.10.1             Pillow==11.1.0
numpy==2.2.1              httpx==0.28.1
beautifulsoup4==4.12.3    ddgs==9.5.2
python-dotenv==1.0.1
```
`python-multipart` is **not** optional — without it FastAPI cannot parse `UploadFile` at all.
Deliberately **absent**: `torch` and `transformers` (~2 GB). They'd make the free-tier build fail. Added only if you switch to `DETECTION_ENGINE=transformer`.

### `frontend/package.json`
React 18, React Router 7, Vite 5, Tailwind 3, `@supabase/supabase-js`, `three` (lazy-loaded as its own chunk), `sonner`, Vitest + Testing Library.

---

## 6 — Ports

| Port | What |
|---|---|
| `8000` | backend, locally (`uvicorn … --port 8000`) |
| `$PORT` | backend on Render — **injected**, often `10000`. Never hard-code |
| `5173` | `npm run dev` |
| `4173` | `npm run preview` (the production build) |

---

## Quick reference: the three commands that answer "does it work?"

```bash
python tools/smoke_test.py                    # 30 live checks against the backend
python tools/check_backend.py                 # numbered diagnosis when something fails
cd backend && python -m pytest -q             # 57 contract tests
```

Full testing guide: **[`TESTING.md`](TESTING.md)**. Deployment: **[`DEPLOY.md`](DEPLOY.md)**.
