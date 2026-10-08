# Role-Based Access Control (RBAC) in TruthGuard AI
### Part C.7 — paste-ready section for the project report

---

## 1. The threat model in one paragraph

TruthGuard AI exposes two things worth protecting: **expensive AI compute** (image forensics and outbound retrieval on a shared Render instance) and **student activity data** (who submitted what, and what the model concluded). The two roles have different needs: a **student** should only ever see their own history, while an **educator** needs class-wide visibility to teach from it. The platform is a browser SPA holding a *public* Supabase anon key and calling a *public* AI endpoint — so no single check can be trusted. We therefore enforce the same rule at three independent layers.

| Layer | Where it runs | What it protects | Can it be bypassed? |
|---|---|---|---|
| **1. Route guards** | Browser (React) | UI/UX — students never see educator screens | **Yes**, trivially (DevTools, curl) |
| **2. Row Level Security** | PostgreSQL (Supabase) | **Data** — rows are filtered inside the DB engine | **No** — enforced by the database, not by our code |
| **3. JWT role-claim check** | FastAPI backend | **Compute** — inference refuses anonymous/unauthorised callers | **No** — requires a valid signature from the JWT secret |

The design principle is **defence in depth with fail-closed defaults**: if layer 1 is bypassed, layer 2 returns an empty result set rather than an error; if the role cannot be determined anywhere, the user is treated as a `student` (least privilege).

---

## 2. Layer 1 — Frontend route protection (React)

**Implementation:** `src/components/ProtectedRoute.jsx` and `src/components/EducatorRoute.jsx`, composed in `src/App.jsx`.

```jsx
<Route path="/dashboard" element={
  <ProtectedRoute>          {/* requires a valid Supabase session      */}
    <EducatorRoute>         {/* requires profile.role === 'educator'   */}
      <EducatorDashboard />
    </EducatorRoute>
  </ProtectedRoute>
} />
```

* `ProtectedRoute` redirects unauthenticated visitors to `/login`, preserving the attempted path in router state so they return there after signing in.
* `EducatorRoute` redirects any non-educator to a dedicated **403 Access Denied** page instead of silently pretending the feature does not exist — explicit denial is better hygiene and makes the control demonstrable.
* The `Navbar` also omits the Dashboard link for students, so the feature is not merely blocked but undiscoverable in normal use.

**Where the role comes from:** `AuthContext` reads it with a `SELECT` against the `profiles` table using the caller's own JWT — never from `localStorage`, a cookie, or anything editable in DevTools. If that query fails, the context falls back to `role: 'student'`.

**Honest limitation (worth stating in a report):** a React guard is a *user-experience* control, not a security boundary. Any user can call the API directly. We say so explicitly in the code comments, because claiming otherwise would be a security anti-pattern.

---

## 3. Layer 2 — Supabase Row Level Security (the real data boundary)

**Implementation:** `supabase/schema.sql`. RLS is both `ENABLE`d and `FORCE`d on `profiles` and `scan_logs`, so the policies apply even to the table owner.

Because the browser talks to Postgres directly with a public anon key, **RLS is what makes that architecture safe**: PostgREST rewrites every query with a predicate derived from the caller's JWT (`auth.uid()`, `auth.jwt()`). Filtering happens inside the database engine, *before* results reach the network — so there is no client code path that can widen the result set.

| Policy | Table | Command | Effect |
|---|---|---|---|
| `students_select_own_scan_logs` | `scan_logs` | SELECT | `user_id = auth.uid()` **AND** caller's role is `student` |
| `educators_select_all_scan_logs` | `scan_logs` | SELECT | caller's role is `educator` → all rows, all users |
| `users_insert_own_scan_logs` | `scan_logs` | INSERT | `WITH CHECK (user_id = auth.uid())` |
| *(none — deliberate)* | `scan_logs` | UPDATE / DELETE | **denied for everyone** → append-only audit trail |
| `profiles_select_own` | `profiles` | SELECT | `id = auth.uid()` |
| `educators_select_all_profiles` | `profiles` | SELECT | educators resolve submitter attribution for the dashboard |
| `profiles_update_own` | `profiles` | UPDATE | `USING` + `WITH CHECK (id = auth.uid())` |
| *(none — deliberate)* | `profiles` | INSERT | rows are created only by the `handle_new_user()` trigger |

Three properties matter most:

1. **A student cannot read another student's logs.** Not because the UI hides them — the rows simply do not exist in their result set.
2. **An educator can read but not write.** No UPDATE/DELETE policy exists, so even the educator role cannot alter or erase history. This makes `scan_logs` a genuine **audit trail** (Part C.6): immutable, attributable, server-timestamped (`DEFAULT now()`, so a client cannot back-date its own activity).
3. **Nobody can forge attribution.** `WITH CHECK (user_id = auth.uid())` means a user cannot insert a log line blamed on someone else — which would be both a data-integrity attack and a way to frame a classmate.

**Anti-escalation controls.** Two further database objects close the obvious loophole:

* `set_my_role(p_role)` — a `SECURITY DEFINER` function that is the only sanctioned way to set a role. It only ever touches `WHERE id = auth.uid()`, only accepts `'student'`/`'educator'`, only fires while `role_locked = false`, and then locks the row. It exists because with "Confirm email" enabled a brand-new user has no session and therefore cannot satisfy the profile UPDATE policy — without it, every educator would be permanently stuck as a student.
* `enforce_role_immutable()` — a `BEFORE UPDATE` trigger that silently reverts any attempt by a user to change their *own* `role` or `role_locked` value. Since `profiles_update_own` legitimately allows updating your own row, this trigger is what stops `supabase.from('profiles').update({ role: 'educator' })` from being a one-line privilege escalation.

**The role type itself is an enum** (`user_role AS ENUM ('student','educator')`), so values like `'admin'` — or an injection string — cannot be stored at all. Validation at the storage layer is the strongest kind, because it cannot be skipped by skipping the UI.

---

## 4. Layer 3 — Backend JWT verification and role claims (FastAPI)

**Implementation:** `backend_security/jwt_auth.py` (+ `integration_example.py`, verified by `test_jwt_middleware.py`).

The AI endpoints were originally auth-free. We add a single FastAPI dependency so **no inference logic changes**:

```python
api_router = APIRouter(
    prefix="/api/v1",
    dependencies=[Depends(require_auth)],   # ← the whole integration
)

@api_router.get("/analytics/summary")
async def analytics(user: CurrentEducator):  # 403 for students, 401 for anonymous
    ...
```

`require_auth` verifies the Supabase-issued HS256 access token against the project's **JWT Secret** (a server-side credential that must never reach the frontend bundle — anyone holding it can forge a token for any user). It checks signature, `exp`, `iat`, `aud`, and `iss`, with an explicit algorithm allow-list.

Verification results — 23/23 checks passing locally:

| Attack / scenario | Result |
|---|---|
| No `Authorization` header | **401** `missing_token` (before any inference runs) |
| Token signed with a different secret (forgery) | **401** `invalid_signature` |
| Expired token | **401** `token_expired` |
| Token issued for another audience | **401** `invalid_audience` |
| `alg=none` algorithm-confusion attack | **401** — rejected by the algorithm allow-list |
| Malformed / non-JWT string | **401** `invalid_token` |
| Valid **student** token on an educator endpoint | **403** `insufficient_role` |
| Valid **educator** token on an educator endpoint | **200** |
| Unknown role claim (`superadmin`) | downgraded to `student` (least privilege) |
| `/health` | **200** public — uptime probes must not need a token |

Note the deliberate distinction between **401** (who are you?) and **403** (I know who you are, and no). Conflating them breaks client behaviour — the frontend re-prompts for login on 401 and shows Access Denied on 403.

**Role resolution.** The application role lives in `app_metadata.role`, which our `handle_new_user()` trigger writes at signup; `user_metadata.role` (client-supplied) is only a fallback, and anything unrecognised resolves to `student`. A common trap is documented in the code: the JWT's *top-level* `role` claim is PostgREST's `authenticated` role, not our application role.

**Known freshness trade-off.** A JWT role claim is only as current as the moment it was issued (up to ~1 hour). If an educator is demoted mid-session, their existing token still says `educator`. For genuinely sensitive endpoints, `jwt_auth.py` documents an optional re-check of the `profiles` row using the service-role key — a server-side credential that bypasses RLS and therefore must never leave the backend.

---

## 5. Why three layers instead of one

A single control has a single failure mode. Here, each layer fails independently and safely:

* Delete the React guards → RLS still returns zero cross-user rows, and the backend still demands a valid token.
* Misconfigure a policy → the route guard hides the UI and the JWT role check still returns 403 at the API.
* Leak the anon key (it is public anyway) → nothing changes, because the anon key grants no data access; RLS does.

The layer that would be catastrophic to lose is **layer 2**, because it is the only one standing between a public anon key and the database. That is why the schema *enables and forces* RLS, defines deny-by-default (no policy = no access), grants no UPDATE/DELETE on the audit table, and pins `search_path` on every `SECURITY DEFINER` function (an unpinned search path is a classic Postgres escalation vector via schema shadowing).

---

## 6. Summary for the report's conclusion

> TruthGuard AI enforces role-based access control at three independent layers: React route guards for usability, PostgreSQL Row Level Security as the authoritative data boundary, and Supabase-JWT verification with role-claim checks in FastAPI to protect AI compute. Roles are stored as a Postgres enum, assigned write-once through a `SECURITY DEFINER` function, protected from self-escalation by a database trigger, and defaulted to the least-privileged value (`student`) whenever the role is missing, malformed, or unreadable. The `scan_logs` table is append-only by construction — no update or delete policy exists — giving the platform a tamper-evident audit trail of every detection and fact-check, attributable to a specific user and timestamped by the database.
