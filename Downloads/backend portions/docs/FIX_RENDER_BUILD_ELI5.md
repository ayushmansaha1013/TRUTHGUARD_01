# Fixing the Render Build Failure — ELI5

**Your error, in one sentence:** Render built your app with **Python 3.14**, and three
of your dependencies don't have ready-made packages for 3.14 — so pip tried to *compile*
them from scratch, needed a Rust compiler, and gave up.

**The fix, in one sentence:** tell Render to use **Python 3.11.9** instead.

**Time: 2 minutes.** Then a second, separate thing to fix (page 4) that would have got
you next.

---

# Part 1 — What actually went wrong (ELI5)

### How pip normally installs things

Programmers publish two kinds of package:

- a **ready-made box** (`wheel`) — shaped for your exact Python version, just unpack it
- **flat-pack furniture** (`sdist`) — the raw source, which *you* must assemble

A ready-made box takes 2 seconds. Flat-pack furniture needs the right tools, and can
fail halfway.

### What happened to you

Your `requirements.txt` pins exact versions. Render's log shows what it found:

```
04:19:45  Collecting Pillow==11.1.0
04:19:45    Downloading pillow-11.1.0.tar.gz (46.7 MB)          <- .tar.gz = FLAT-PACK
04:19:48  Collecting numpy==2.2.1
04:19:48    Downloading numpy-2.2.1.tar.gz (20.2 MB)            <- FLAT-PACK
04:25:03    Preparing metadata (pyproject.toml): finished ...   <- 6 minutes assembling
04:25:04    Downloading pydantic_core-2.27.2.tar.gz             <- FLAT-PACK
04:25:06  error: failed to create directory
          `/usr/local/cargo/registry/cache/...`
          Read-only file system (os error 30)
          💥 maturin failed                                     <- the Rust assembler
```

`.tar.gz` instead of `.whl` means "no ready-made box exists, build it yourself".
`maturin` is the Rust build tool. Render's machine doesn't let pip write to the cargo
(Rust) cache directory, so the build died.

**Why were there no ready-made boxes?** Because Render used **Python 3.14.3** —
its default since February 2026 — and numpy, pydantic-core and Pillow released these
versions before 3.14 existed.

I checked PyPI directly:

| Package | Version | 3.11 | 3.12 | 3.13 | **3.14** |
|---|---|---|---|---|---|
| numpy | 2.2.1 | ✅ | ✅ | ✅ | **❌ no wheel** |
| pydantic-core | 2.27.2 | ✅ | ✅ | ✅ | **❌ no wheel** |
| Pillow | 11.1.0 | ✅ | ✅ | ✅ | **❌ no wheel** |
| pydantic | 2.10.4 | ✅ | ✅ | ✅ | ✅ |
| fastapi | 0.115.6 | ✅ | ✅ | ✅ | ✅ |

Nothing is wrong with your code. **PyPI's 3.14 shelf is simply empty for those three.**

### Why didn't my `runtime.txt` work?

`backend/runtime.txt` says `python-3.11.9` — but **Render does not read `runtime.txt`**.
That's a Heroku convention (Heroku has since deprecated it too).

Render reads the Python version from **only two places**:
1. a **`PYTHON_VERSION`** environment variable, or
2. a **`.python-version`** file

…and it was reading neither, so it used its default of 3.14.3. That's the entire bug.

---

# Part 2 — THE FIX: 2 minutes (recommended)

Do this on the service you already have.

### Step 1 — Open the Environment tab

Render dashboard → click your **truthguard** service → **Environment** (left sidebar).

### Step 2 — Add one variable

Click **Add Environment Variable**:

| Key | Value |
|---|---|
| `PYTHON_VERSION` | `3.11.9` |

⚠️ **Type it exactly.** On Render this variable must be **fully qualified** — `3.11`
alone is rejected, `3.11.9` is accepted. That rule is the opposite of Railway's, which
is why people get confused moving between platforms.

### Step 3 — Save

Click **Save Changes**. Render redeploys automatically.

### Step 4 — Watch the log

Open **Logs** and watch for these lines. They're your proof it worked:

```
==> Using Python version 3.11.9                 <- was "3.14.3 (default)"
Collecting numpy==2.2.1
  Downloading numpy-2.2.1-cp311-cp311-manylinux...whl    <- .whl  ✅ not .tar.gz
Collecting pydantic-core==2.27.2
  Downloading pydantic_core-2.27.2-cp311-cp311-manylinux...whl
Successfully installed fastapi-0.115.6 ... 
==> Build successful 🎉
```

`cp311` in the filename means "compiled for CPython 3.11". Seeing `.whl` instead of
`.tar.gz` is how you know it's fixed. The build should now take about **60 seconds**
instead of 6 minutes.

### Step 5 — Confirm the service is alive

Open in a browser tab:

```
https://<your-service>.onrender.com/health
```

You want JSON: `{"status":"ok","detection_ready":true,...}`

**If it says `503` instead**, that's Part 4 — a different problem with a different fix.

---

# Part 3 — Config files I've added (so this can't happen again)

I've committed the pin in **three** places, so a rebuild from a fresh service gets it
right even without touching the dashboard:

| File | Contents | Who reads it |
|---|---|---|
| `.python-version` (repo root) | `3.11.9` | Render, Railway |
| `backend/.python-version` | `3.11.9` | Render/Railway when the root dir is `backend` |
| `render.yaml` → `PYTHON_VERSION` | `3.11.9` | Render — **only if** created as a Blueprint |

> **Why all three?** `runtime.txt` was the single source of truth and Render ignores it.
> Any one of these files alone would have saved you; all three means a rebuild from
> scratch works no matter which route you take.

**Note on `.python-version`:** both platforms accept it, but with a difference —
Render allows the patch version to be omitted (`3.11` works), Railway/Nixpacks prefers
major.minor. `3.11.9` is accepted by both, so that's what's committed.

### Optional hardening: make the failure self-explaining

If you'd rather see a clear error than a 6-minute Rust crash, change Render's **Build
Command** to:

```
pip install --only-binary=:all: -r requirements.txt
```

`--only-binary=:all:` forbids source builds. If a wheel is missing, you get
**"Could not find a version that satisfies the requirement numpy==2.2.1"** in about
5 seconds instead of a Rust toolchain failure after six minutes.

The trade-off: it will also block any future dependency published as source-only. All
of yours ship wheels today, so it's safe right now.

---

# Part 4 — ⚠️ The thing that would have bitten you NEXT

Your GitHub repo is at commit `4a8216d`, which is **missing several fixes I made
afterwards**. Two of them matter on a deployed backend:

### 1. `cryptography` is missing from `backend/requirements.txt`

PyJWT needs it to verify **RS256** — which is what Supabase signs tokens with for
**projects created after 1 May 2025**.

Without it, your build succeeds and the service boots, and then **every logged-in AI
call returns 503**, with a message about the public signing key. It looks like a
Supabase misconfiguration. It's a missing dependency.

### 2. The frontend fixes aren't there either

Missing: `public/config.js` (runtime configuration for Netlify Drop), the
`connect-src` fix in `index.html` (without it the browser blocks every call to
`onrender.com`), and `public/_redirects` (without it, refreshing `/dashboard` 404s).

### How to update your repo

I've built **`truthguard-ai.zip`** — the whole project, ready to push. Either:

**Option A — GitHub website (no tools needed)**
1. Unzip it
2. Your repo on GitHub → **Add file → Upload files**
3. Drag the **contents** of the unzipped folder in (not the folder itself)
4. Commit message: `Fix Python version pin + RS256 support` → **Commit changes**

**Option B — git on your laptop**

```bash
git clone https://github.com/ayushmansaha1013/TRUTHGUARD_01
cd TRUTHGUARD_01
# copy the unzipped contents over the top, then:
git add -A
git commit -m "Fix Python version pin + RS256 support"
git push
```

Render redeploys automatically on push. **Then re-add `PYTHON_VERSION=3.11.9`** if the
new `render.yaml` isn't being used — env vars you set in the dashboard survive a code
push, so it should still be there.

---

# Part 5 — Railway instead (or as well)

Railway has the same Python-version trap but a different way out.

### Step 1 — Create the project

Railway dashboard → **New Project → Deploy from GitHub repo** → pick
`TRUTHGUARD_01`.

### Step 2 — Point it at the backend folder

**Settings → Source → Root Directory** → `backend`

Without this, Railway tries to build the whole repo (frontend included) and fails.

### Step 3 — Set the Python version

**Variables → New Variable**:

| Key | Value |
|---|---|
| `NIXPACKS_PYTHON_VERSION` | `3.11` |

⚠️ **Major.minor only** — `3.11`, **not** `3.11.9`. Railway/Nixpacks resolves patch
versions separately and a patch pin can silently fall back or fail. This is the exact
opposite of Render, where `3.11` alone is invalid.

Railway also reads `runtime.txt` (`python-3.11.9`) and `.python-version`, both of which
now exist in `backend/` — so even without this variable it should resolve correctly.

### Step 4 — Add the rest of the variables

Same names as Render:

```
FRONTEND_ORIGIN=https://your-site.netlify.app
AUTH_ENABLED=true
SUPABASE_PROJECT_URL=https://<your-ref>.supabase.co
SUPABASE_JWT_SECRET=            (blank if your project is new)
DETECTION_ENGINE=heuristic
FACT_CHECK_ENGINE=duckduckgo
RATE_LIMIT_ENABLED=true
RATE_LIMIT_PER_MINUTE=20
PYTHONUNBUFFERED=1
```

### Step 5 — Get a public URL

**Settings → Networking → Public Networking → Generate Domain.**

### Step 6 — Set the start command

If Railway doesn't pick up the `Procfile` automatically:

```
uvicorn main:app --host 0.0.0.0 --port $PORT --workers 1
```

### Render vs Railway, for your decision

| | Render (free) | Railway (trial) |
|---|---|---|
| Sleeps when idle | **Yes**, ~15 min → 30–60 s cold start | No |
| Needs a card | No | No |
| Python version var | `PYTHON_VERSION=3.11.9` | `NIXPACKS_PYTHON_VERSION=3.11` |
| Build config file | `render.yaml` | `railway.yaml` |

Use **one**, not both. For a live demo, Railway's lack of cold starts is a real
advantage — a 60-second wait mid-presentation looks like a crash.

---

# Part 6 — Troubleshooting: the NEXT errors

| Symptom in the log | Meaning | Fix |
|---|---|---|
| `Downloading ...tar.gz` then `maturin failed` / `Read-only file system` | Python is still 3.14 — the pin didn't apply | Confirm `PYTHON_VERSION=3.11.9` is on **this** service. Env vars set before you edited them need a redeploy |
| `==> Using Python version 3.14.3 (default)` | No pin seen at all | Same as above. Check it's in the **Environment** tab, not just in the repo |
| `error: metadata-generation-failed` | Same root cause | Same |
| Build succeeds, `/health` returns **503** | Auth fail-closed: RS256 token but no `SUPABASE_PROJECT_URL`, **or** `cryptography` missing from requirements (Part 4) | Re-push the updated repo, and set `SUPABASE_PROJECT_URL` |
| Build succeeds, then `ModuleNotFoundError: No module named 'backend_security'` | `main.py` imports the JWT middleware from a sibling folder | Set **Root Directory = `backend`**, and make sure `backend_security/` is in the repo (it is). Render clones the whole repo, so the path resolves |
| Service starts then immediately restarts in a loop | Start command missing or wrong | Set `uvicorn main:app --host 0.0.0.0 --port $PORT --workers 1` |
| `/health` 200 but the site says "Failed to fetch" | CORS | `FRONTEND_ORIGIN` must be your exact Netlify URL, no trailing slash |
| First request takes 45–60 s | Free tier woke from sleep. Normal | Open `/health` 2 minutes before demoing |

---

# Part 7 — The 60-second version

**Fix the build:**
1. Render dashboard → your service → **Environment**
2. Add `PYTHON_VERSION` = `3.11.9`
3. Save → watch for `cp311...whl` and `Build successful`
4. Open `/health` → expect JSON

**Then, because your repo is stale:**
5. Unzip `truthguard-ai.zip`
6. Push its contents to your GitHub repo (upload files, or `git add -A && git push`)
7. Same `PYTHON_VERSION` fix applies to Railway, but as `NIXPACKS_PYTHON_VERSION=3.11`

**Why it broke:** Render defaulted to Python 3.14, which has no ready-made packages for
numpy, pydantic-core or Pillow, so pip tried to compile them and ran out of Rust
toolchain. `runtime.txt` would have said otherwise, but Render doesn't read it.
