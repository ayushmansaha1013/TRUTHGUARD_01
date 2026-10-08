# TruthGuard AI — Manual Testing Checklist

Run these in order. Each test states **what to do**, **what you should see**, and **why it proves the control works**. Tests marked 🔒 are the security tests you need screenshots of for the report.

**Prerequisites**

- [ ] `supabase/schema.sql` has been run in the Supabase SQL Editor
- [ ] `frontend/.env` has `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`, `VITE_API_BASE_URL`, and `VITE_DEMO_MODE=false`
- [ ] Supabase → Authentication → Providers → Email → **Confirm email = OFF** (so sign-up creates a session immediately; otherwise expect the "check your inbox" screen — which is itself a valid pass for test 1.3)
- [ ] Two test accounts exist: `educator@college.edu` and `student@college.edu` (same password)
- [ ] Dev server running: `cd frontend && npm install && npm run dev`

---

## A. Automated tests (run these first — they are your regression safety net)

| # | Command | Expected |
|---|---|---|
| A.1 | `cd frontend && npm test` | **7 files, 92 tests passed** |
| A.2 | `cd frontend && npm run build` | Builds cleanly: `index-*.js` ≈ 469 kB **plus a separate lazy `three.module-*.js` ≈ 684 kB chunk**, ~44 kB CSS, no unresolved imports |
| A.3 | `cd backend_security && SUPABASE_JWT_SECRET=test-secret-only-for-local-tests python test_jwt_middleware.py` | **23/23 checks passed** |

What A.1 already proves for you (so the manual steps below can focus on the real database):

| Area | Tests |
|---|---|
| **RBAC layer 1** | unauthenticated → `/login`; student → `/403`; educator → dashboard; anonymous checked *before* role; unknown role treated as student; renders nothing while the session loads (fails closed) |
| **XSS (C.5)** | `javascript:` / `data:` URLs render as inert text, never `<a>`; markup in a URL is escaped; `rel="noopener noreferrer"` present on real links |
| **Validation (C.2)** | wrong MIME rejected; renamed `.txt`→`.png` rejected; >8 MB rejected with both sizes in the message; exactly 8 MB accepted; empty file rejected; claim <10 / >1000 rejected; control + zero-width characters stripped (log-injection defence) |
| **JWT (C.1)** | `Authorization: Bearer …` present on both AI endpoints; a *fresh* token is read per request (rotation-safe); header omitted rather than `"Bearer undefined"` when logged out; `credentials: 'omit'` |
| **Transport (C.2)** | multipart field is `file`; `Content-Type` is *not* set manually (so the boundary is generated); an `AbortSignal` is attached |
| **Errors / 429 (C.3)** | 413/422/429/502/503/504 each map to a friendly message; FastAPI validation arrays are flattened; non-JSON error bodies don't crash; network failure → retryable message; after a 429 the next call is refused **locally** (zero extra requests) and the countdown is observable |
| **Audit trail (C.6)** | log row carries user/content/verdict/confidence and **no client timestamp**; confidence clamped to 0–100; long claims truncated; a logging failure never throws away a good AI result |
| **Dashboard defence in depth** | a student gets an empty result set *without the view ever being queried* |
| **3D layer resilience** | no WebGL (jsdom) → the CSS fallback renders and there is **no `<canvas>` and no crash**; the scene is `aria-hidden`; a `pulse` before the lazy `three` import resolves does not throw |
| **Reduced motion / a11y** | `ScrollReveal` never hides content and falls back to visible without `IntersectionObserver`; `VerdictFlip` shows exactly one face per state and is an `aria-live` region; `CountUp` lands exactly on the target and renders `0` (not `NaN`) for a missing value |
| **Hick's Law regression** | signup has exactly **2** text inputs, **no** confirm-password field, **2** role radios with `student` pre-selected, and **1** submit button; password strength rises monotonically and never exceeds 100% |
| **Disabled-state honesty** | a disabled `MagneticButton` does **not** drift toward the cursor (moving a dead control implies it is clickable) |

---

## 0. Smoke test — the app runs

| # | Action | Expected |
|---|---|---|
| 0.1 | Open `http://localhost:5173/` | Landing page renders on navy `#0A192F` with teal accents; no console errors |
| 0.2 | Look at the health pill on the landing page | "AI backend online" (green) if `VITE_API_BASE_URL` is reachable; otherwise a red unreachable message — **this is correct behaviour, not a crash** |
| 0.3 | Resize the window to ~375px wide | Navbar collapses to a ☰ menu; cards stack vertically; no horizontal scrollbar |
| 0.4 | Open DevTools → Network → filter `WS`/`Fetch` | Supabase calls go to `*.supabase.co`, AI calls to your Render URL — nothing hardcoded to `localhost` |

---

## 1. Authentication flow (Part B.3)

| # | Action | Expected |
|---|---|---|
| 1.1 🔒 | `/signup` → enter `student@college.edu`, a 6+ char password, choose **Student** → Create account | Redirected to `/scanner`. Navbar shows the email and role badge `student`. **No "Dashboard" link visible.** |
| 1.2 | Supabase Dashboard → Table Editor → `profiles` | Exactly one new row: `id` = the auth user's UUID, `email` set, `role = student`, `role_locked = true`. **Proves the `handle_new_user()` trigger fired.** |
| 1.3 | `/signup` → choose **Educator** with `educator@college.edu` | Redirected to `/dashboard` (or the "check your inbox" screen if email confirmation is ON). The `profiles` row shows `role = educator`. |
| 1.4 | Sign up with a 5-character password | The strength meter stays red ("Weak"), the submit is rejected instantly with "Password must be at least 6 characters." — **no network request is made** (Network tab stays empty) |
| 1.4b | Click **Show** next to the password field | The password becomes visible and the button reads **Hide**. **This toggle is why there is no confirm-password field** — see `docs/HICKS_LAW.md` §3 |
| 1.4c | Count the fields on `/signup` | Exactly **two** text inputs (email, password) plus the pre-selected **Student** role. The form was reduced from 4 decisions to 2 (Hick's Law); `pages/Signup.test.jsx` fails the build if a field is re-added |
| 1.5 | `/login` → wrong password | Error banner "Incorrect email or password." Note the message does **not** reveal whether the email exists (anti-enumeration) |
| 1.6 | `/login` → `student@college.edu` with the correct password | Lands on `/scanner`. Toast: "Signed in securely." |
| 1.7 | Refresh the browser (F5) on `/scanner` | Still signed in — no flash of the login page (session restored from Supabase-managed storage) |
| 1.8 🔒 | DevTools → Application → Local Storage | You see exactly **one** auth entry (`truthguard-auth-token`). There is **no** custom key holding a raw JWT, no token in a cookie, and nothing in `sessionStorage`. Proves Part B.3 ("use Supabase's built-in session management") |
| 1.9 | Click **Sign out** | Redirected to `/login`. Re-visiting `/scanner` bounces back to `/login`. |

---

## 2. 🔒 Unauthenticated users are redirected to login (Part B.4)

| # | Action | Expected |
|---|---|---|
| 2.1 | Sign out, then type `http://localhost:5173/scanner` directly in the address bar | Immediately redirected to `/login`. The scanner UI is **never** rendered — not even for a frame. |
| 2.2 | Same for `/fact-checker` | Redirected to `/login` |
| 2.3 | Same for `/dashboard` | Redirected to `/login` (**not** to `/403` — authentication is checked before authorisation, which is the correct order) |
| 2.4 | Sign in, then open `/dashboard` in a new tab | Works if educator; redirects if student. Both tabs share one session. |
| 2.5 | Visit a random URL like `/secret-admin` | 404 page. It discloses nothing about the real route table. |

---

## 3. 🔒 A student cannot see the educator dashboard (Part B.4 / C.7 layer 1)

| # | Action | Expected |
|---|---|---|
| 3.1 | Sign in as `student@college.edu` | Navbar has **no** Dashboard link |
| 3.2 | Type `http://localhost:5173/dashboard` manually | **403 Access Denied** page: "Educator role required", showing the signed-in email and `role: student`, plus buttons back to the scanner |
| 3.3 | DevTools → Console → run the guard check: `document.body.innerText.includes('Total scans')` | `false` — the dashboard component never mounted, so no data was even fetched |
| 3.4 | **Bypass the frontend entirely** (the important one) using the console snippet below, signed in as the student | `allLogsForStudent` returns **`[]`** — empty, even though the educator's rows exist. RLS filtered them inside Postgres. This proves layer 1 is not the only defence. |

```js
// Paste into the browser console while signed in as the STUDENT.
// This bypasses every React component and asks Supabase directly, using only
// public information: the project URL + anon key are in the bundle BY DESIGN —
// which is exactly why RLS, not the key, has to be the security boundary.

// 1) Copy these two values from frontend/.env (or Supabase -> Settings -> API).
const url = 'https://YOUR-PROJECT-REF.supabase.co'
const key = 'YOUR_ANON_KEY'

// 2) Reuse the session Supabase already stored for this browser tab.
const entry = Object.entries(localStorage).find(([k]) => k.includes('auth-token'))
const stored = JSON.parse(entry[1])
const session = Array.isArray(stored) ? stored[0] : (stored.currentSession ?? stored)

// 3) Build a fresh client with that session and query as the student.
const { createClient } = await import('https://esm.sh/@supabase/supabase-js@2')
const sb = createClient(url, key)
await sb.auth.setSession({
  access_token: session.access_token,
  refresh_token: session.refresh_token,
})

const allLogsForStudent = await sb.from('educator_scan_logs').select('*')
console.log('rows visible to a student:', allLogsForStudent.data?.length, allLogsForStudent.data)
// EXPECTED: 0 rows (or only this student's own rows) — never the educator's or
// other students' submissions.
```

> **Cleaner and more convincing: prove it in SQL.** Run this in the Supabase SQL
> Editor to impersonate each user at the PostgREST layer. Replace the secret and
> the two UUIDs (get them from `select id, email from auth.users;`).
>
> ```sql
> -- ⚠ Uses your project JWT secret. Run it once for evidence, then clear the
> --   editor history. Never paste the secret into the frontend or a screenshot.
> select current_setting('request.jwt.claims', true) as impersonated_as;
> ```
>
> ```sql
> -- STEP 1: impersonate the STUDENT
> select set_config('request.jwt.claims', json_build_object(
>   'sub', '<STUDENT_UUID>', 'role', 'authenticated',
>   'aud', 'authenticated', 'email', 'student@college.edu'
> )::text, false);
>
> select auth.uid() as i_am;                  -- must equal <STUDENT_UUID>
> select public.current_user_role() as my_role;   -- must be 'student'
> select count(*) as rows_i_can_see from public.scan_logs;      -- ONLY their own
> select count(*) as rows_i_can_see from public.educator_scan_logs;
> ```
>
> ```sql
> -- STEP 2: impersonate the EDUCATOR (same queries, different sub)
> select set_config('request.jwt.claims', json_build_object(
>   'sub', '<EDUCATOR_UUID>', 'role', 'authenticated',
>   'aud', 'authenticated', 'email', 'educator@college.edu'
> )::text, false);
>
> select public.current_user_role() as my_role;   -- must be 'educator'
> select count(*) as rows_i_can_see from public.scan_logs;      -- EVERY row
> ```
>
> ```sql
> -- STEP 3: still impersonating the STUDENT — prove writes are constrained
> -- 3a. forging attribution must FAIL with a row-level security violation
> insert into public.scan_logs (user_id, content_type, input_summary, verdict)
> values ('<EDUCATOR_UUID>', 'text', 'forged by student', 'False');
>
> -- 3b. self-promotion must be silently reverted by enforce_role_immutable()
> update public.profiles set role = 'educator' where id = auth.uid();
> select role, role_locked from public.profiles where id = auth.uid();  -- still 'student'
>
> -- 3c. erasing history must FAIL (no DELETE policy exists)
> delete from public.scan_logs where user_id = auth.uid();
>
> -- 3d. a correct self-attributed insert must SUCCEED
> insert into public.scan_logs (user_id, content_type, input_summary, verdict, confidence_score)
> values (auth.uid(), 'text', 'legitimate entry', 'True', 88.0);
>
> -- STEP 4: reset to the dashboard role so the editor behaves normally again
> select set_config('request.jwt.claims', '', false);
> ```
>
> Expected: 3a and 3c raise `new row violates row-level security policy` /
> delete 0 rows; 3b leaves the role as `student`; 3d succeeds. Those four
> results *are* your Part B.2 evidence.

---

## 4. 🔒 A student cannot see another student's logs (Part B.2)

Setup: create a **third** account, `student2@college.edu`, and have both students submit a few scans so the table has several rows from different users.

| # | Action | Expected |
|---|---|---|
| 4.1 | Sign in as `student@college.edu`, run a scan and a fact-check | Both succeed; rows appear in `scan_logs` (check the Table Editor) |
| 4.2 | Sign in as `student2@college.edu`, then query `scan_logs` from the browser console | Only `student2`'s own rows are returned. `student@college.edu`'s rows are **absent**, not hidden by CSS or filtering in JS |
| 4.3 | In the Supabase Table Editor, confirm both students' rows exist | They do — so the empty/partial result in 4.2 is RLS filtering, not missing data. **This contrast is the proof.** |
| 4.4 | Try to insert a log attributed to someone else (console): `.insert({ user_id: '<student2-uuid>', content_type:'text', input_summary:'forged', verdict:'False' })` while signed in as student 1 | **Rejected** — RLS `WITH CHECK (user_id = auth.uid())` violation (`new row violates row-level security policy`). Proves nobody can forge attribution. |
| 4.5 | Try to delete your own log: `.delete().eq('id', <your-row-id>)` | **Rejected / 0 rows affected** — no DELETE policy exists. Proves the audit trail is append-only (Part C.6). |
| 4.6 | Try to edit your own log's verdict: `.update({ verdict:'Likely Real' }).eq('id', <id>)` | **Rejected / no change** — no UPDATE policy exists. |
| 4.7 | Try to self-promote: `.from('profiles').update({ role:'educator' }).eq('id', <own-id>)` | The update is accepted but the `enforce_role_immutable` trigger **silently reverts** `role`. Re-read the row: still `student`. Reload the app → `/dashboard` still returns 403. |
| 4.8 | Try `.from('profiles').update({ role_locked:false })` then retry 4.7 | Still `student` — the trigger reverts `role_locked` too. The only sanctioned path is `set_my_role()`, which refuses once `role_locked = true`. |

---

## 5. Educator dashboard analytics (Part A.4 / B.5)

| # | Action | Expected |
|---|---|---|
| 5.1 | Sign in as `educator@college.edu` | Navbar shows the Dashboard link; `/dashboard` loads |
| 5.2 | With scan rows present from *other* users, inspect the table | Rows from **all** students appear, with the "Submitted by" column populated (partially masked, e.g. `st•••••@college.edu`) |
| 5.3 | Check the four stat cards | Total Scans, Deepfakes/False claims, Average confidence, Active users — all non-zero and consistent with the table below |
| 5.4 | Toggle **This week / 30 days** | Numbers change; a scan made 8 days ago disappears from the 7-day view |
| 5.5 | Click **↻ Refresh** | Table reloads without a full page refresh |
| 5.6 | Click **✨ Generate Quiz** | Toast: "Quiz generation coming soon…" (intentional stub for this milestone) |
| 5.7 | Run a scan as the educator, then refresh the dashboard | Your own new row appears — educators can also submit, and their logs are visible to themselves |
| 5.8 | Run the query on a **fresh project with no scans** | Empty state "Nothing flagged in this period", zeros in the cards, **no crash** |
| 5.9 | Delete `educator_scan_logs` in the SQL Editor, then reload the dashboard | Friendly error: "Database objects are missing. Run supabase/schema.sql…" — graceful degradation, not a stack trace |

---

## 6. Image scanner (Part A.2 / C.2)

| # | Action | Expected |
|---|---|---|
| 6.1 | Drag a valid `.jpg` onto the dropzone | Dropzone highlights teal on drag-over; preview thumbnail + filename + size appear |
| 6.2 | Click the dropzone instead of dragging | Native file picker opens, filtered to images |
| 6.3 | Press **Analyse image** | Spinner + "Analysing… Ns" live counter; verdict panel shows a skeleton/waiting state |
| 6.4 | Wait for the result | Verdict badge (red/green/yellow), confidence gauge animating to the right %, raw label, fake probability, analysis time |
| 6.5 🔒 | Try to upload a `.txt`, `.pdf` or `.gif` | **Instant** inline error "Unsupported file type…" — and **no request appears in the Network tab**. This is the point of client-side validation (Part C.2) |
| 6.6 🔒 | Rename `notes.txt` to `notes.png` and upload | Rejected — the browser reports the real MIME type, so extension spoofing does not pass |
| 6.7 🔒 | Try an image larger than 8 MB | Instant error "Image is too large (X MB). The maximum size is 8.0 MB." — no upload attempted |
| 6.8 | Click **Remove image** then **Analyse** | Button is disabled with no file selected |
| 6.9 | Press **New scan** after a result | Result clears, dropzone resets, preview memory freed |
| 6.10 🔒 | DevTools → Network → inspect the `detect-image` request headers | `Authorization: Bearer eyJhbGciOi...` is present (Part C.1). **Do not screenshot the token itself.** Also confirm the request payload is `multipart/form-data` with a field named `file` |
| 6.11 | Upload an image with a bizarre filename, e.g. `<img src=x onerror=alert(1)>.png` | The filename is displayed as **literal text** in the preview and in the dashboard table. No image breaks, no script runs (Part C.5) |

---

## 7. Fact checker (Part A.3 / C.5)

| # | Action | Expected |
|---|---|---|
| 7.1 | Type a claim under 10 characters | Counter warns "N more characters needed"; **Verify is disabled** |
| 7.2 | Paste a 1001+ character claim | Counter turns red "Too long — 1001/1000"; Verify disabled; textarea stops accepting at the cap |
| 7.3 | Submit a valid claim | Your claim appears as a right-aligned teal bubble; then an "Analyzing sources •••" bubble with animated dots and skeleton lines |
| 7.4 | Wait for the response | Assistant bubble with verdict badge, explanation, and a numbered, **clickable** source list |
| 7.5 🔒 | Inspect a source link in DevTools | `<a target="_blank" rel="noopener noreferrer nofollow">` — prevents tab-nabbing and Referer leakage (Part C.5) |
| 7.6 🔒 | In the console, confirm no raw HTML injection: `document.querySelectorAll('*').length` before/after a response with a hostile source | Grows by the expected few nodes only. Also run `document.body.innerHTML.includes('<script')` → `false` |
| 7.7 🔒 | Grep the source for the dangerous API: `grep -rn "dangerouslySetInnerHTML=" frontend/src` | **No matches** (searching for the *call* syntax; the bare word appears only in explanatory comments). This is the XSS evidence for the report |
| 7.8 | Press **Enter** in the textarea | Sends the claim. **Shift+Enter** inserts a newline instead |
| 7.9 | Click one of the example-claim chips | The textarea fills with that claim |
| 7.10 | Expand "Show retrieved context" | Up to 5 retrieved passages render as escaped plain text (objects are JSON-stringified, never interpreted) |
| 7.11 | Submit a claim containing `<script>alert(1)</script>` (padded to 10+ chars) | Rendered as visible literal text in the bubble and stored as text in `scan_logs.input_summary`. Nothing executes. |
| 7.12 | Submit a claim containing a newline + `[ADMIN] approved` | Stored as a single clean line in `scan_logs` — control characters were stripped, so log lines cannot be forged (log-injection defence) |

---

## 8. 🔒 Rate limiting & error handling (Part C.3)

| # | Action | Expected |
|---|---|---|
| 8.1 | Trigger a 429 (fastest way: temporarily point `VITE_API_BASE_URL` at an endpoint that returns 429, or spam the button until the backend rate limiter fires) | Error banner "Too many requests. Please wait a moment before trying again." |
| 8.2 | Watch the submit button immediately after | It becomes **disabled** and shows a live countdown "Please wait 10s…" → "9s…" → … → re-enables at 0 |
| 8.3 | Try to submit during the cooldown | No request is sent at all — `api.js` short-circuits locally. Verify in the Network tab. |
| 8.4 | Point `VITE_API_BASE_URL` at a dead URL and submit | "Could not reach the TruthGuard AI service…" with a **Retry-friendly** message. No infinite spinner. |
| 8.5 | Point it at a URL that hangs forever | The request aborts after the 60s client timeout with "The analysis took too long and was cancelled." Spinner stops. |
| 8.6 | Simulate a 502/503/504 (e.g. stop the backend) | Mapped message such as "The AI model is starting up or unreachable (gateway error). Try again in ~30 seconds." — never a raw stack trace |
| 8.7 | Sign in, then manually corrupt the stored token in Local Storage and submit | Backend returns 401 → "Your session has expired. Please sign in again." |

---

## 9. 🔒 Backend JWT middleware (Part C.1 — run with your backend teammate)

| # | Action | Expected |
|---|---|---|
| 9.1 | `cd backend_security && pip install -r requirements.txt` | Installs `pyjwt[crypto]`, `httpx` |
| 9.2 | `SUPABASE_JWT_SECRET=test-secret-only-for-local-tests python test_jwt_middleware.py` | **23/23 checks passed** — screenshot this for the report |
| 9.3 | `curl -i -X POST $BACKEND/api/v1/fact-check -H 'Content-Type: application/json' -d '{"claim":"A claim long enough to pass validation"}'` (no token) | `401` with `{"detail":"Authentication required…","error_code":"missing_token"}` and a `WWW-Authenticate: Bearer` header |
| 9.4 | Same request with `Authorization: Bearer garbage.token.here` | `401` `invalid_signature` / `invalid_token` |
| 9.5 | Same request with a **real** token copied from the browser (DevTools → Application → Local Storage → `truthguard-auth-token` → `access_token`) | `200` with the normal fact-check payload |
| 9.6 | `curl -i $BACKEND/api/v1/analytics/summary` with a **student** token | `403` `insufficient_role` (not 401 — the identity is known, the role is insufficient) |
| 9.7 | Same with an **educator** token | `200` |
| 9.8 | `curl -i $BACKEND/health` with no token | `200` — health checks stay public so uptime monitors work |
| 9.9 | Forge a token with `alg: none` and an `educator` claim | `401` — the algorithm allow-list blocks the classic JWT confusion attack |

---

## 10. Environment & secrets hygiene (Part C.4)

| # | Action | Expected |
|---|---|---|
| 10.1 | `grep -rn "supabase.co" frontend/src` | **No hardcoded project URL** — only `import.meta.env.VITE_SUPABASE_URL` |
| 10.2 | `grep -rnE "hf\.space|onrender\.com" frontend/src` | **No hardcoded backend URL** — only `import.meta.env.VITE_API_BASE_URL` |
| 10.3 | `git check-ignore -v frontend/.env` | Confirms `.env` is ignored by `.gitignore` |
| 10.4 | `git status` after editing `.env` | `.env` does **not** appear as a changed/untracked file; `.env.example` does (it is committed on purpose) |
| 10.5 | Search the built bundle for secrets: `grep -o "eyJ[A-Za-z0-9_-]\{20,\}" frontend/dist/assets/*.js \| sort -u` | Only the **anon** key appears (public by design). The JWT secret and any service-role key must be absent. |
| 10.6 | Delete `VITE_API_BASE_URL` and reload | A console warning appears and API calls fail with a clear "Backend URL is not configured" message rather than silently 404ing |
| 10.7 | View page source | The CSP `<meta>` tag is present (`default-src 'self'`, `object-src 'none'`, `frame-ancestors 'none'`) |

---

## 10b. 🔮 The 3D & interaction layer (manual — automated parts are in §A)

These are the checks that need a real browser, because jsdom has no WebGL and no compositor.

| # | Action | Expected |
|---|---|---|
| 10b.1 | Open `/` on a laptop with a GPU | The hero renders a **`<canvas>`** (`document.querySelector('canvas')` is non-null, `data-testid="hero-webgl"`): a rotating wireframe shield with two orbital rings and a particle field |
| 10b.2 | Move the mouse across the hero | The rig eases toward the cursor — **smoothly**, not snapping. It must not stutter on a high-refresh-rate trackpad (the pointer is lerped inside the rAF loop, never written to the DOM in the event handler) |
| 10b.3 | Scroll down the landing page | The 3D object recedes and drifts up; the teal **scroll-progress hairline** at the very top fills left→right and fades out at both ends |
| 10b.4 | Scroll the hero out of view and open DevTools → Performance | Frame activity **stops** while the hero is off-screen (the `IntersectionObserver` pauses the loop). Switch tabs → also stops (`visibilitychange`) |
| 10b.5 | DevTools → Network → JS, then hard-reload `/scanner` directly | The `three.module-*.js` chunk is **only** fetched when a 3D scene mounts. Check its *Initiator* is a dynamic import, and that it is not in the initial waterfall for a page with no hero |
| 10b.6 | OS setting → enable **"Reduce motion"**, reload | No WebGL canvas at all: the **CSS 3D fallback** renders (`data-testid="hero-css"`), nothing spins, scroll reveals appear instantly, stat numbers jump straight to their final value. Toggle the OS setting back off mid-session → the app re-checks live |
| 10b.7 | Open the site on a phone (or DevTools device mode) | No tilt, no magnetism, no spotlight (coarse pointer = no hover). Layout still works and the CSS fallback hero shows |
| 10b.8 | Simulate no WebGL: DevTools → ⋮ → More tools → **Rendering** → "Emulate: WebGL disabled", reload | CSS fallback hero, **no blank box**, no console error |
| 10b.9 | Hover a feature card on the landing page | It tilts toward the cursor with a moving glare, and the badge/icon visibly floats *above* the surface (`translateZ` inside a `perspective` container). Move away → it eases back over ~520 ms, not instantly |
| 10b.10 | Hover the primary CTA | It drifts toward the cursor but **never moves out from under it** (capped at 12 px — a button that escapes would violate Fitts's Law) |
| 10b.11 | Click any button | A 1px "push in" on `:active` — a **non-colour** confirmation, so it works for colour-blind users |
| 10b.12 | Tab through the whole app with the keyboard | Every hover affordance has a visible 2px teal `:focus-visible` ring; the clickable stat cards and filter chips announce their pressed state |
| 10b.13 | On `/scanner`, run a scan that returns **Likely Fake** | The verdict card **flips over in 3D** (mid-flip it rocks on its edge), the confidence **ring** sweeps up with a coloured glow, and the small WebGL orb behind the card **pulses red** |
| 10b.14 | Run a scan that returns **Likely Real** | Same flip, but the ring glows green and the orb does **not** pulse red |
| 10b.15 | Click the dashboard stat card **"Deepfakes / false claims"** | The table below narrows to flagged rows and the card shows a teal focus ring. Click **"Total scans"** → all rows. This is direct manipulation replacing a filter menu: **0 extra controls, more capability** |
| 10b.16 | Switch the dashboard range 7 → 30 days | The stat numbers **tween** to their new values instead of jumping, and the table rows stagger in |
| 10b.17 | DevTools → Performance, record 5s while moving the mouse over cards | No purple "Layout" or green "Paint" spikes per frame — only compositing. If you see layout thrash, something is animating a non-composited property |
| 10b.18 | Check the decorative layers can't eat a click | `.bg-stage`, `.tilt-glare` and `.spotlight::after` are all `pointer-events: none`. Verify by clicking a button that sits on top of an aurora blob |
| 10b.19 | Screen reader (VoiceOver/NVDA) on the landing page | The hero canvas and background are **not announced** (`aria-hidden="true"`); the confidence ring is announced as a progress bar with its value; toasts use `aria-live="polite"` |

---

## 11. Accessibility & polish (quick pass before the demo)

- [ ] Tab through the whole app: focus rings are visible (teal) and never trapped
- [ ] Clickable stat cards and filter chips expose `aria-pressed`; the range control is a labelled `role="group"`
- [ ] The verdict flip is an `aria-live="polite"` region, so the result is announced rather than only shown
- [ ] No animation depends on colour alone: press feedback is geometric, verdicts carry text labels
- [ ] The dropzone is keyboard-operable (Tab to it, Enter/Space opens the file picker)
- [ ] Loading states are announced (`role="status"`, `aria-live="polite"` on toasts)
- [ ] The confidence gauge exposes `role="progressbar"` with `aria-valuenow`
- [ ] Colour is never the only signal: every verdict badge has a text label as well as red/green/yellow (colour-blind safe)
- [ ] `npm run build` completes with no errors and no unresolved imports

---

## Screenshot list for the report

1. Landing page + "AI backend online" health pill
2. Signup with the Student/Educator role selector
3. `profiles` table in Supabase showing both roles (proves the trigger)
4. Student hitting `/dashboard` → **403 Access Denied**
5. Student console query returning `[]` while the Table Editor shows rows (proves RLS)
6. Image scanner result with the confidence gauge and a red "Likely Fake" badge
7. Fact-checker conversation with cited sources expanded
8. Rate-limit cooldown with the disabled button and countdown
9. Educator dashboard populated with multi-user stats
10. `python test_jwt_middleware.py` → **23/23 checks passed**
11. `pg_policies` output from `supabase/verify.sql`
12. `grep -rn "dangerouslySetInnerHTML=" src` → no matches
13. The **WebGL hero** mid-rotation with the floating glass chips
14. The **verdict card mid-flip** (the 3D edge state) and then revealed with the glowing confidence ring
15. The **orb pulsing red** after a "Likely Fake" detection
16. The dashboard with a **stat card active as a filter** (teal ring + narrowed table)
17. `npm run build` output showing **`three.module-*.js` as a separate lazy chunk**
18. `npm test` → **7 files, 92 tests passed**
19. Side-by-side of the site with **Reduce motion ON** (CSS fallback hero, no animation)
