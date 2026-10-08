# Super Simple: What Do I Put In These Two Lines?

```dotenv
SUPABASE_JWT_SECRET=
SUPABASE_PROJECT_URL=
```

**This applies to `backend/.env` locally, and to the Render/Railway service's
Environment tab when you deploy. Same two values, same rules.**

---

## The 10-second answer

| Variable | What goes in it | Always? |
|---|---|---|
| `SUPABASE_PROJECT_URL` | `https://<your-project-ref>.supabase.co` — no trailing slash | **Yes. Always. Every project.** |
| `SUPABASE_JWT_SECRET` | A long random string **— but only if your project is the OLD kind.** New projects leave it **blank**. | **No.** See below. |

That second row is the whole reason this page exists. Read on — it takes 60 seconds.

---

## ELI5: what are these two things?

Think of logging in as showing a **wristband** at the door.

**`SUPABASE_PROJECT_URL` is the address of the building.**
Without it your backend doesn't know where to knock to ask "is this wristband real?"
Example: `https://abcdefghijklm.supabase.co`

**`SUPABASE_JWT_SECRET` was the stamp used to make the wristband.**
Older Supabase projects used *one shared stamp* for everything. Supabase stamped your
wristband, and your backend got given a **copy of the same stamp** so it could check
the wax looked right.

The problem: if anyone steals the stamp, they can make **fake wristbands** — including
one that says "I'm the teacher." That's a whole-user-base compromise from one leaked
string.

So Supabase changed it. New projects (created after **1 May 2025**) don't use a shared
stamp at all:

> Supabase keeps a **pen** that only they own and never give out. They sign each
> wristband with it. They also publish a **photocopy of the signature** at a public
> web address. Your backend downloads that photocopy and checks it matches.
>
> **You never hold a secret. There is nothing to put in `SUPABASE_JWT_SECRET`.**

That public photocopy is called **JWKS**, and its address is:

```
https://<your-project-ref>.supabase.co/auth/v1/.well-known/jwks.json
```

Notice what's in front of it: **your project URL**. That's why `SUPABASE_PROJECT_URL`
is now the one that's always required — it tells the backend where to fetch the
photocopy.

So:

- **Old project (HS256)** → you need both. ✅✅
- **New project (RS256)** → you need only the URL. The secret stays **empty**. ✅⬜

---

## Which kind do I have? 30 seconds, three ways

### Way 1 — the definitive one (do this if you're unsure)

1. Run your app and sign up / log in as any user.
2. Press **F12** → **Application** tab → **Local Storage** → click your site.
3. Find the key starting with `sb-` and ending in `-auth-token`. Copy the
   `access_token` value (a long string starting with `eyJ`).
4. Paste it into **https://jwt.io** → look at the first line of the decoded **HEADER**:

| You see | Your project is | So set `SUPABASE_JWT_SECRET` to |
|---|---|---|
| `"alg": "HS256"` | old-style, shared stamp | **the secret** (Word 3 below) |
| `"alg": "RS256"` | new-style, public signature | **leave it blank** |

This is the only check that cannot lie to you.

### Way 2 — the dashboard

1. Supabase dashboard → your project.
2. Go to **Settings → API Keys** (older dashboards: **Settings → API**).
3. Go to the **JWT Signing Keys** tab (older dashboards: **Settings → JWT**).

| You see | Meaning |
|---|---|
| A **"Legacy JWT secret"** with a Reveal/Copy button that gives you a real value | old-style → use it |
| A **current signing key** labelled **RS256** (or ECC / Ed25519), and no legacy secret | new-style → leave blank |

### Way 3 — paste the URL and let the backend tell you

Set `SUPABASE_PROJECT_URL` and leave the secret blank. Start the backend and try a
scan. Read the error:

| Error you get back | What it means | Fix |
|---|---|---|
| Works — 200 | You're on RS256. Done. 🎉 | nothing |
| `503 … this token is signed with the legacy symmetric key, so SUPABASE_JWT_SECRET must be set` | You're on HS256 | set the secret (Word 3) |

The error message is written to tell you the answer, on purpose.

---

## Word 3 — Where to actually click to get each value

### `SUPABASE_PROJECT_URL`

Supabase dashboard → your project → **Settings → API** (or **Settings → Data API**).
Copy **Project URL**. It looks like:

```
https://abcdefghijklm.supabase.co
```

- **No trailing slash.** `...supabase.co` ✅ — `...supabase.co/` ❌
- **Not** the database connection string (`db.abcdefgh.supabase.co:5432`) — that's a
  different thing, for a different purpose.
- **Not** the `anon` key. That's a long `eyJ...` string; it is not a URL.

### `SUPABASE_JWT_SECRET` (old-style projects ONLY)

Supabase dashboard → **Settings → API Keys** → **JWT Signing Keys** tab → the legacy
section → **Reveal** → copy.

It's a long random string, roughly 40–60 characters, something like
`super-long-random-looking-string-here`.

⚠️ **This is the single most dangerous string in the project.** Anyone holding it can
mint a valid *educator* login for your app. Therefore:
- it goes in `backend/.env` (**gitignored**) and Render's Environment tab, and
- it must **never** go in `frontend/.env`, and **never** in a `VITE_*` variable —
  every `VITE_*` value is compiled into the JavaScript that every visitor downloads.

---

## Real-time demonstration: what to actually do tomorrow

You have three options. Pick based on what you need to *show*.

### Option A — Demo auth for real (best, worth the 5 minutes)

Supabase Auth is live, RLS is enforced, the Educator dashboard shows real rows.

```bash
cd backend
cp .env.example .env
# then edit .env:
#   AUTH_ENABLED=true
#   SUPABASE_PROJECT_URL=https://<your-ref>.supabase.co
#   SUPABASE_JWT_SECRET=            <- blank if RS256, the value if HS256
#   FRONTEND_ORIGIN=http://localhost:5173
```

Also put the **same two values** in Render → your service → **Environment**.

### Option B — Demo the AI with no login at all (safest if anything is flaky)

```bash
AUTH_ENABLED=false
```

Now nobody needs to log in, nothing depends on Supabase, and the scanner and
fact-checker both work. Good insurance if the venue's Wi-Fi or the projector is
misbehaving.

**What you give up:** the "educator sees all scans, student sees only their own" RLS
demo. If that's a marking criterion, run Option A on the day and keep this as the
fallback you switch to mid-demo if logins misbehave.

### Option C — Both, seamlessly

Leave `AUTH_ENABLED=false` in `backend/.env` for local, and set `AUTH_ENABLED=true`
plus the real values **on Render only**. Your local demo is bulletproof; your deployed
URL shows the full secure stack. This is the configuration I'd pick.

> **Regardless of which you choose:** do one full dry run in the exact room, on the
> exact laptop, against the exact URL you'll present from. The failure mode that
> ruins demos isn't a bug — it's a cold start, hotel Wi-Fi, or a `.env` you edited on
> a different machine.

---

## The gotcha that will bite you (and how to fix it in 5 seconds)

**If you change signing keys, or set the secret after users have already logged in,
their existing sessions stop working** — until they sign out and back in.

Why: the `access_token` in their browser was minted under the old scheme. The backend
correctly refuses it forever. The browser keeps using it because it doesn't know.

**Fix:** log out, log in. If you're demoing, do a fresh login right before you present.
If a student in your audience is testing and gets 401s, tell them to log out and in.

You'll recognise it by the error code `invalid_signature` or `unknown_key_id`.

---

## I got an error — what does it actually mean?

| What you see | Real cause | Fix |
|---|---|---|
| `401 invalid_signature` | Token isn't signed by the key you configured | Old token → log out/in. Still broken → wrong `SUPABASE_JWT_SECRET`, or you're on RS256 with a wrong `SUPABASE_PROJECT_URL` pointing at a *different* project |
| `503 … not configured: … SUPABASE_JWT_SECRET must be set` | HS256 project, secret empty | Fill in the secret |
| `503 … not configured: … SUPABASE_PROJECT_URL must be set` | RS256 token, URL empty | Fill in the URL |
| `503 Could not retrieve the public signing key from Supabase` | URL wrong, or the server has no outbound internet | Check the URL has no typo/no trailing slash; check outbound network |
| `401 unknown_key_id` | Token signed with a key Supabase has retired | Log out and back in |
| `401 token_expired` | Session over 1 hour old, quite normal | Just log in again |
| `401 Token algorithm 'X' is not accepted` | Something exotic (not HS256/RS256/ES256/EdDSA) | You're not hitting your own app |
| Everything works locally, all AI calls 503 **on Render** | You set the values locally but not in the Render dashboard | Render never reads `.env`. Add them under **Environment** in the dashboard |
| Frontend loads, all calls fail with a CORS error | `FRONTEND_ORIGIN` doesn't list the exact origin you're browsing from | `http://localhost:5173` ≠ `http://127.0.0.1:5173` ≠ your Vercel URL. Comma-separate all of them |

---

## How do I know this actually works?

The backend was tested against **both** Supabase signing schemes, with a real RSA key
pair, a real JWKS HTTP endpoint and real signatures — nothing mocked:

```bash
cd backend_security
python test_asymmetric_jwks.py    # 25/25  new-style RS256 projects
SUPABASE_JWT_SECRET=test-secret-only-for-local-tests python test_jwt_middleware.py   # 23/23  old-style HS256
```

`test_asymmetric_jwks.py` also fires the classic **algorithm-confusion attack** at the
new code path — presenting a token that claims `alg: HS256` but is signed with the
RS256 *public* key. That attack defeats servers which let a token choose both its
algorithm and its key. It is refused here, and the test includes a control proving the
forged token is otherwise perfectly valid, so the refusal is meaningful rather than an
accident of formatting.

End-to-end, a genuine RS256 token against the real deployable backend:

```
{"status": 200, "verdict": "Likely Fake", "confidence": 76.9, "is_fake": true,
 "algorithm_in_token": "RS256"}
```

---

## TL;DR, one last time

```
SUPABASE_PROJECT_URL=https://<your-ref>.supabase.co     <- always
SUPABASE_JWT_SECRET=                                    <- blank if new project (RS256)
SUPABASE_JWT_SECRET=<long random string>                <- if old project (HS256)
```

Not sure which? Paste a real access token into jwt.io and read `alg`. Done.
