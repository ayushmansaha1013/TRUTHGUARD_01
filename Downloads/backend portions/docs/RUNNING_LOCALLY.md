# Running TruthGuard AI on your own laptop

Everything you need, in order. **Path A gets the app on screen in ~2 minutes.** Path B adds real login + the database (~15 minutes). Path C is the optional backend work.

---

## 0. What you need installed (one time)

| Tool | Version | Check with | Get it from |
|---|---|---|---|
| **Node.js** | 18 or newer (20 LTS recommended) | `node --version` | https://nodejs.org → *LTS* button |
| **npm** | comes with Node | `npm --version` | — |
| Python 3 | only for Path C | `python --version` | already on macOS/Linux; Windows: https://python.org (tick *"Add to PATH"*) |
| Git | optional | `git --version` | https://git-scm.com |

Open a terminal first:

- **Windows** → press `Win`, type **PowerShell**, Enter. (Or *Windows Terminal*.)
- **macOS** → `Cmd + Space`, type **Terminal**, Enter.
- **Linux** → `Ctrl + Alt + T`.

> ⚠️ Node 16 or older **will not work** — Vite 5 requires Node 18+. If `node --version` prints `v16.x`, install the LTS build and reopen the terminal.

---

## 1. Get the files onto your laptop

Download the project, then unzip it somewhere with **no spaces in the path** (spaces break some npm scripts on Windows).

Good: `C:\projects\truthguard-ai` or `~/projects/truthguard-ai`
Avoid: `C:\Users\My Name\OneDrive\College Sem 5\SE project (final)\truthguard-ai`

Then move into it:

**Windows (PowerShell)**
```powershell
cd C:\projects\truthguard-ai\frontend
```

**macOS / Linux**
```bash
cd ~/projects/truthguard-ai/frontend
```

> Tip: in PowerShell you can type `cd ` (with a trailing space) and then **drag the folder** from Explorer into the window — it pastes the path for you.

Confirm you are in the right place:
```bash
ls          # macOS/Linux
dir         # Windows
```
You should see `package.json`, `index.html`, `src`, `vite.config.js`, `.env`.

---

## 2. Install the dependencies (one time, ~30–60 s)

```bash
npm install
```

This downloads React, Tailwind, Supabase, Three.js etc. into a new `node_modules/` folder. You will see a progress bar and then something like `added 230 packages in 24s`. Warnings about deprecated sub-packages are normal — ignore them.

> **This folder was deliberately not included in the download** (it's ~200 MB and platform-specific). `npm install` recreates it. If it *is* there and things behave oddly, delete `node_modules` and `package-lock.json` and run `npm install` again.

---

## 3. PATH A — run it right now (2 minutes, demo mode)

The project ships with a working `frontend/.env` that has **demo mode ON**, so you can see every screen immediately without touching Supabase:

```bash
npm run dev
```

You'll get:
```
  VITE v5.4.21  ready in 400 ms
  ➜  Local:   http://localhost:5173/
```

**Hold `Ctrl` (Windows/Linux) or `Cmd` (macOS) and click the `http://localhost:5173/` link**, or paste it into Chrome/Edge/Firefox.

What you'll see:
- Landing page with the rotating 3D shield, glass cards, scroll progress bar.
- A yellow **DEMO MODE** badge in the navbar.
- You're already "signed in" as an educator, so `/scanner`, `/fact-checker` and `/dashboard` are all reachable.

**The one edit that makes the AI actually work.** Open `frontend/.env` in any text editor (Notepad, VS Code, TextEdit) and replace line 5 with your teammate's real backend URL:

```ini
VITE_API_BASE_URL=https://truthguard-backend.onrender.com
```

Save the file. Vite watches `.env` and **restarts itself automatically** — if it doesn't, press `Ctrl+C` in the terminal and run `npm run dev` again.

Now the Image Scanner and Fact Checker will call the live model. In demo mode no JWT is attached, which is fine *while the backend is still auth-free*. Once your teammate adds the JWT middleware (Path C), demo mode will start getting `401`s — that's your cue to do Path B.

> Render's free tier **sleeps after ~15 minutes of inactivity**. The first request cold-starts the service and can take 30–60 s, during which you may see a mapped `502/503` message. Open the `/health` URL in a browser tab once to wake it, then retry.

**To stop the server:** click into the terminal and press `Ctrl + C`.

---

## 4. PATH B — real login + database (~15 minutes)

This is the configuration you will be graded on.

### 4.1 Create the Supabase project
1. Go to https://supabase.com → **Start your project** → sign in with GitHub (fastest).
2. **New project**. Pick any name, set a **database password** (write it down; the app never needs it), region closest to you (Singapore for India). Free tier is fine. Wait ~2 minutes for it to provision.

### 4.2 Run the database script
3. Left sidebar → **SQL Editor** → **+ New query**.
4. Open `supabase/schema.sql` from the project folder, **copy the entire file**, paste it into the editor, click **Run** (or `Ctrl/Cmd + Enter`).
5. You should see **“Success. No rows returned.”**
6. *(Recommended)* Repeat with `supabase/verify.sql` and compare the output against the `-- EXPECTED:` comments. This is your evidence that RLS is enabled and correctly shaped — screenshot it for the report.

### 4.3 Turn off email confirmation
7. Left sidebar → **Authentication** → **Providers** → **Email**.
8. Switch **Confirm email** to **OFF** → **Save**.

> Why: with confirmation ON, `signUp()` returns no session, so a brand-new user can't immediately satisfy a Row Level Security policy. The app handles that case (it shows a "check your inbox" screen and uses the `set_my_role()` database function), but OFF is much smoother for a live demo.

### 4.4 Copy your keys into `.env`
9. Left sidebar → **Settings** (gear) → **API**. Copy:
   - **Project URL** → looks like `https://abcdefghijklm.supabase.co`
   - **Project API keys → `anon` `public`** → a long string starting `eyJ…`

> 🚨 **Never copy the `service_role` key into the frontend.** It bypasses Row Level Security completely. Only the `anon` key belongs in `.env`, and that is safe *because* RLS — not the key — protects the data.

10. Edit `frontend/.env` so it reads:

```ini
VITE_API_BASE_URL=https://truthguard-backend.onrender.com
VITE_SUPABASE_URL=https://abcdefghijklm.supabase.co
VITE_SUPABASE_ANON_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3Mi...
VITE_DEMO_MODE=false
VITE_RATE_LIMIT_COOLDOWN_SECONDS=10
```

11. Restart the dev server (`Ctrl+C`, then `npm run dev`). The **DEMO MODE badge should disappear.**

### 4.5 Create your two demo accounts
12. In the browser go to `/signup` → **`educator@college.edu`** + a password (6+ chars) → select **Educator** → Create account. You land on the dashboard.
13. Sign out, sign up again → **`student@college.edu`** → leave the role on **Student**. You land on the scanner, and there is **no Dashboard link** in the navbar.
14. Run a few scans / fact-checks as each user so the dashboard has data.
15. Sanity check: Supabase → **Table Editor** → `profiles` should show two rows with the right roles, and `scan_logs` should have one row per analysis.

> Fresh dashboard shows zeros? That's correct until someone submits something. Uncomment the **seed block at the bottom of `schema.sql`** (put your two real account emails in it), run it once, and the dashboard populates instantly.

---

## 5. PATH C — backend JWT test (optional, needs Python)

```bash
cd ../backend_security
pip install -r requirements.txt

# Windows may need:  py -m pip install -r requirements.txt
```

Then:

**macOS / Linux**
```bash
SUPABASE_JWT_SECRET=test-secret-only-for-local-tests python3 test_jwt_middleware.py
```

**Windows PowerShell**
```powershell
$env:SUPABASE_JWT_SECRET="test-secret-only-for-local-tests"; python test_jwt_middleware.py
```

Expected: **`23/23 checks passed.`** — screenshot this. It proves forged, expired, wrong-audience and `alg=none` tokens are all rejected, and that a student gets `403` (not `401`) on an educator endpoint.

This runs entirely on your laptop; it does **not** touch your live Render service. `backend/main.py` already imports `jwt_auth.py` and applies it at router level, so there is nothing left to wire — `backend_security/` is the standalone, documented deliverable with its own test suite.

---

## 6. Other useful commands

Run all of these from the `frontend/` folder.

| Command | What it does |
|---|---|
| `npm run dev` | Dev server on http://localhost:5173 with hot reload. **Day-to-day command.** |
| `npm test` | Runs the 92 automated tests once. Expect `7 files, 92 tests passed`. |
| `npm run test:watch` | Same, but re-runs on every save. |
| `npm run build` | Production build into `frontend/dist/`. Expect `index-*.js` ≈ 469 kB **plus a separate lazy `three.module-*.js` ≈ 684 kB chunk**. |
| `npm run preview` | Serves the production `dist/` build on http://localhost:4173 — test this before you deploy. |

Ctrl + C stops any of them.

---

## 7. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `'npm' is not recognized as an internal or external command` | Node isn't installed, or PATH wasn't picked up | Install Node LTS from nodejs.org, then **close and reopen** the terminal |
| `npm: command not found` on macOS | Same | Reopen Terminal; if it persists, install via https://nodejs.org (not the App Store) |
| `The engine "node" is incompatible` / syntax errors in `vite` | Node 16 or older | Upgrade to Node 20 LTS |
| Port 5173 already in use | Another dev server running | Vite auto-picks 5174 — just use the URL it prints. Or kill the old one: Windows `netstat -ano \| findstr :5173` then `taskkill /PID <pid> /F`; macOS/Linux `lsof -ti:5173 \| xargs kill` |
| `EACCES` / `EPERM` on `npm install` | Permissions, or OneDrive/antivirus locking files | Move the project out of OneDrive (`C:\projects\...`). On macOS/Linux never use `sudo npm install` — fix the folder ownership instead |
| Browser opens but the page is blank | Console error | Open DevTools (`F12`) → **Console** tab and read the first red line |
| Yellow **DEMO MODE** badge still showing | `VITE_DEMO_MODE=true`, or `.env` not saved | Set it to `false`, save, restart the dev server |
| Console: `[TruthGuard] Supabase is not configured` | URL/anon key empty or mistyped | Re-check both values from Supabase → Settings → API. No quotes, no trailing spaces, no line breaks inside the key |
| Login/signup does nothing | `schema.sql` not run, or email confirmation still ON | Run the SQL; turn **Confirm email** OFF |
| **Nothing detects / every scan fails** | **`.env` still has the placeholder backend URL** | **Run `python tools/check_backend.py` — see [`docs/WHY_NOT_DETECTING.md`](WHY_NOT_DETECTING.md). Or run `python tools/mock_backend.py` to get a working contract-accurate backend instantly.** |
| Every AI call returns `401` | Backend has the JWT middleware but you're in demo mode | Do Path B, or set `AUTH_ENABLED=false` on the backend for local testing |
| `429 Too many requests` | You hit the backend rate limit | Expected — the button locks for 10 s. This is the Part C.3 control working |
| `502 / 503` from the AI backend | Render free tier is asleep (cold start) | Open the `/health` URL in a tab, wait ~40 s, retry |
| Dashboard says "Database objects are missing" | `schema.sql` wasn't run in *this* project | Run it in the SQL Editor, then click ↻ Refresh |
| Dashboard shows rows but "Submitted by" is blank | The `educators_select_all_profiles` policy is missing (older schema version) | Re-run `supabase/schema.sql` — it's safe to re-run |
| No 3D hero, just a CSS one | No WebGL, GPU blocklisted, or **Reduce motion** is on | Chrome → ⋮ → More tools → **Rendering** → set *WebGL* to enabled; check your OS accessibility settings for "Reduce motion" |
| Everything looks unstyled | Tailwind/PostCSS didn't build | Delete `node_modules`, run `npm install` again, then `npm run dev` |

---

## 8. Before the demo — 60-second checklist

- [ ] `frontend/.env` has your **real** backend URL, your Supabase URL + **anon** key, and `VITE_DEMO_MODE=false`
- [ ] `supabase/schema.sql` has been run (check Table Editor shows `profiles`, `scan_logs`, `educator_scan_logs`)
- [ ] **Confirm email** is OFF in Supabase Auth
- [ ] Two accounts exist: one **educator**, one **student**
- [ ] A few scans/fact-checks have been submitted so the dashboard isn't empty
- [ ] Your Render service is **awake** — open its `/health` URL in a tab 2 minutes before you present
- [ ] `npm test` → 92 passed, and `npm run build` → no errors
- [ ] Browser zoom at 100%, DevTools closed, one tab only
- [ ] **`.env` is not in your git repo** — `git status` should not list it

Then: `npm run dev` → open http://localhost:5173 → present.

**Fallback if the internet dies in the room:** run `python tools/mock_backend.py`, set `VITE_API_BASE_URL=http://127.0.0.1:8000` and `VITE_DEMO_MODE=true`, restart, and the *entire* product still works — uploads, verdicts, the 3D flip, fact-checks with citations, the dashboard. (The mock is a stub, not a model: label it as such if you show it.) See `docs/WHY_NOT_DETECTING.md`.
