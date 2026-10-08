# Getting Your Website Live — ELI5, Step By Step

**Your situation:** the backend is deployed, Supabase is connected, and the old
Netlify site is deleted. You have `netlify-drop.zip`. This walkthrough takes you from
here to a working live site.

**Total time: about 10 minutes.** Follow the phases in order — the order matters, and
I explain why at each step.

---

## First: what is `netlify-drop.zip`?

**It IS your website.** It is not a folder from `truthguard-ai` that you need to find.
It is the already-built, ready-to-upload version of the frontend — the contents of
`frontend/dist`, which the build process generates.

So: **you do not need to touch any folder in `truthguard-ai` for this.** No Node, no
`npm`, no building. Just the zip.

Inside the zip are 7 files. The one that matters is `config.js`:

```
netlify-drop/
├── config.js          ← THE ONLY FILE YOU EDIT
├── index.html
├── favicon.svg
├── _redirects
└── assets/
    ├── index-*.js     (the app)
    ├── index-*.css    (the styling)
    └── three.module-*.js  (the 3D hero)
```

> **Why a plain `config.js` file and not the usual settings screen?**
> Vite normally bakes settings into the JavaScript **when it builds**. Netlify Drop
> has no build step and no settings screen, so those baked-in values can never be
> changed afterwards. `config.js` is read by the browser **when someone opens the
> site**, so you can change it and re-upload in seconds. That is the whole trick.

---

# PHASE 1 — Find your backend's address (2 minutes)

You said the backend is deployed. Now we need its exact URL.

### Step 1.1 — Find it

- **On Render:** go to dashboard.render.com → click your service → the URL is at the
  top left, looking like `https://truthguard-api.onrender.com`
- **On Railway:** your project → **Settings → Networking → Public Networking** →
  **Generate Domain** if there isn't one → it looks like
  `https://truthguard-production.up.railway.app`

**Copy it.** No trailing slash. Not the frontend URL. Not the Supabase URL.

### Step 1.2 — Test it BEFORE going further

Paste this into a browser tab, with your URL in place:

```
https://your-backend-url.onrender.com/health
```

You must see something like:

```json
{"status":"ok","detection_ready":true,"fact_check_ready":true,...}
```

**Write down whether you saw that.** Three outcomes:

| What you saw | What it means | What to do |
|---|---|---|
| The JSON above | ✅ Backend is alive. Go to Phase 2. | — |
| A 502 / "Application failed to start" | Backend is deployed but crashed | Render → your service → **Logs**. Fix, redeploy |
| Nothing / spins forever | On Render's free tier it **sleeps** after ~15 min | Wait 60 seconds and refresh. That's normal, not broken |
| 404 on `/health` | Wrong URL, or you deployed something else | Re-check the URL in the dashboard |

🚨 **Do not continue to Phase 2 until `/health` returns JSON.** A frontend cannot fix a
backend that isn't answering, and you'll waste an hour blaming the website.

---

# PHASE 2 — Put the website online (4 minutes)

### Step 2.1 — Unzip

Download `netlify-drop.zip` and unzip it. You get a folder containing `config.js`,
`index.html`, `assets`, and so on.

**If your unzip tool makes `netlify-drop/netlify-drop/index.html`,** use the **inner**
folder — the one where `index.html` sits directly next to `config.js`. Getting this
wrong gives you a blank page, so check.

### Step 2.2 — Edit `config.js`

Open `config.js` in Notepad (Windows), TextEdit (Mac) or VS Code. It looks like this:

```js
window.__TRUTHGUARD__ = {
  apiBaseUrl: '',
  supabaseUrl: '',
  supabaseAnonKey: '',
  demoMode: false,
}
```

Fill in the three blanks:

```js
window.__TRUTHGUARD__ = {
  apiBaseUrl: 'https://your-backend-url.onrender.com',
  supabaseUrl: 'https://abcdefghijklm.supabase.co',
  supabaseAnonKey: 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...long...',
  demoMode: false,
}
```

**Where each value comes from:**

| Field | Where to get it | Rules |
|---|---|---|
| `apiBaseUrl` | The URL from Step 1.1 — the one you just tested `/health` on | Keep `https://`. **No** trailing `/`. **No** `/api/v1` on the end |
| `supabaseUrl` | Supabase → your project → **Settings → API** → **Project URL** | `https://xxxx.supabase.co` |
| `supabaseAnonKey` | Same screen → **Project API keys** → the **`anon` `public`** one | The long `eyJ...` string. Use **anon**, never `service_role` |

⚠️ **Copy the `anon` key, not `service_role`.** The anon key is safe to publish — it
just names your project; the database itself (Row Level Security) decides who can read
what. The `service_role` key bypasses all of that and must never be in a website file.

⚠️ **Keep the quotes** (`'`) and the **commas** at the end of each line.

💡 **Escape route:** if Supabase login is being stubborn and you just want to demo the
AI, set `demoMode: true` and fill in only `apiBaseUrl`. The site then skips login
entirely and everything except real user accounts still works. You can switch back to
`false` later by editing this same file.

### Step 2.3 — Drop it on Netlify

1. Go to **https://app.netlify.com/drop**
2. **Drag the folder** (the one with `index.html` inside) into the drop zone
3. Wait ~20 seconds
4. Netlify gives you a URL like `https://sparkly-panda-9f3a21.netlify.app`

📋 **COPY THAT URL AND KEEP IT SOMEWHERE.** You need it in the very next step.

💡 **Optional but recommended:** rename it to something you can say out loud.
**Site configuration → General → Change site name** → e.g. `truthguard-demo` →
your URL becomes `https://truthguard-demo.netlify.app`.

Do this **before** Phase 3. Renaming later changes the URL, and then the backend
stops recognising your site.

---

# PHASE 3 — Tell the backend to trust your website (2 minutes)

**Why this is needed:** the browser enforces a rule called CORS. Your website
(`something.netlify.app`) and your backend (`something.onrender.com`) are two different
places, and by default the browser asks the backend *"do you accept requests from that
website?"* The backend currently answers **no** — it only lists `localhost` by default,
because it can't guess your Netlify URL in advance. This is why the order had to be:
deploy the site first, learn its URL, then tell the backend.

**Skipping this step gives you a confusing symptom:** the site loads, login works, but
every scan fails — and `curl` from your laptop works fine, which makes you think the
backend is broken. It isn't. The *browser* is blocking it.

### Step 3.1 — On Render (or Railway), open the Environment variables

Render → your service → **Environment** tab.

### Step 3.2 — Set these

| Variable | Value | Notes |
|---|---|---|
| `FRONTEND_ORIGIN` | `https://truthguard-demo.netlify.app` | **The URL from Step 2.3.** Comma-separate extra origins: `https://truthguard-demo.netlify.app,http://localhost:5173` |
| `AUTH_ENABLED` | `true` | Real login. Set `false` if you'd rather demo without logins |
| `SUPABASE_PROJECT_URL` | `https://abcdefghijklm.supabase.co` | Same as `supabaseUrl` above |
| `SUPABASE_JWT_SECRET` | *(leave blank if your Supabase project is new)* | Only for projects created **before May 2025**. Unsure? See `docs/SUPABASE_ENV_ELI5.md` |

**Rules for `FRONTEND_ORIGIN`:**
- Include `https://`
- **No trailing slash** — `...netlify.app` ✅, `...netlify.app/` ❌
- No wildcards, no `*` — the backend uses an exact-match allow-list
- Multiple sites? Comma-separate them, no spaces needed

### Step 3.3 — Save and wait

Click **Save Changes**. Render automatically redeploys — **wait until it says "Live"**
(2–3 minutes on the free tier).

---

# PHASE 4 — Test it (2 minutes)

### Step 4.1 — Hard refresh

Open your Netlify URL and press **Ctrl + Shift + R** (Windows) or **Cmd + Shift + R**
(Mac). The hard part matters: your browser cached the old version of the site, and a
normal refresh may keep serving it.

### Step 4.2 — Walk through these in order

| # | Do this | You should see |
|---|---|---|
| 1 | Open your Netlify URL | Landing page with the 3D hero, teal accents |
| 2 | Click **Sign Up**, choose **Student** | Account created, taken to the scanner |
| 3 | Open **Image Scanner**, drag any photo in | Spinner, then a verdict badge + confidence ring |
| 4 | Open **Fact Checker**, type a claim (10–1000 chars) | "Analyzing sources…" then verdict, explanation, clickable sources |
| 5 | Sign out, sign up again as **Educator** | Dashboard loads with stat cards + a table |
| 6 | Refresh while on `/dashboard` | Page reloads correctly (**not** a 404) |

If all six pass, you are done. 🎉

---

# PHASE 5 — Changing anything later

⚠️ **Do NOT drop the folder on `app.netlify.com/drop` again.** That creates a **brand
new site with a new URL**, and your backend no longer recognises it.

**To update the existing site:** open your Netlify site → **Deploys** tab → scroll to
the bottom to *"Need to update your site? Drag and drop your site output folder
here"* → drop the folder there. Same URL, updated files.

Then **hard-refresh** the page. That's it.

---

# Troubleshooting, ELI5

| What you see | What it actually means | Fix |
|---|---|---|
| **"Backend URL is not configured"** | `apiBaseUrl` in `config.js` is still empty, or you hard-refreshed before re-uploading | Edit `config.js`, re-drop, **hard refresh** |
| **"Failed to fetch" / "Network error"** | Backend unreachable, or CORS says no | Test `/health` in a tab. If that works, it's CORS → do Phase 3 |
| **Console: "Refused to connect … Content Security Policy"** | The backend is on a host not on the allow-list — e.g. you used a different host from Render/Railway | Tell me the host and I'll add it, or edit `connect-src` in `frontend/index.html` |
| **Everything works but scans fail right after login** | `AUTH_ENABLED=true` and the token can't be verified | Check `SUPABASE_PROJECT_URL`. Blank `SUPABASE_JWT_SECRET` is correct for new projects |
| **`401 unknown_key_id` or `invalid_signature`** | Your browser is still holding a login token signed with an old key | **Log out and log back in** |
| **Login says "Email not confirmed"** | Supabase's email confirmation is on | Supabase → **Authentication → Providers → Email** → turn **Confirm email** OFF |
| **Blank white page** | You dropped the outer folder, so `index.html` isn't at the root | Re-drop the **inner** folder — the one where `index.html` sits directly beside `config.js` |
| **Refreshing `/dashboard` gives "Page not found"** | The SPA redirect didn't ship | Re-download the zip — `_redirects` is inside it now |
| **First request takes 45–60 seconds, then everything is fast** | Render's free tier sleeps when idle. Normal | Open `/health` in a tab **2 minutes before** you demo, to wake it |
| **Rate limit message** | 20 AI requests per minute | Wait 10 seconds — there's a built-in cooldown timer |

---

# The 60-second version

1. Open `https://your-backend/health` → must show JSON
2. Unzip `netlify-drop.zip` → open `config.js` → paste **3 values** (backend URL, Supabase URL, Supabase **anon** key)
3. Drag the folder onto **app.netlify.com/drop** → **copy the URL it gives you**
4. Backend → **Environment** → `FRONTEND_ORIGIN` = that URL → **Save** → wait for "Live"
5. Open your site → **Ctrl + Shift + R** → sign up → scan an image → fact-check a claim

---

# Answers to the two things you asked

**"What do I paste?"** — Into `config.js` at the top of the zip:

```js
window.__TRUTHGUARD__ = {
  apiBaseUrl: 'https://<your-backend>.onrender.com',
  supabaseUrl: 'https://<your-ref>.supabase.co',
  supabaseAnonKey: '<the anon public key>',
  demoMode: false,
}
```

Three values. All are public and safe to have in a website file — which is exactly why
this approach works with no settings screen and no build step.

**"Which folder of truthguard?"** — **None of them.** `netlify-drop.zip` *is* the built
website; it is what `truthguard-ai/frontend/dist` would contain after a build, which is
a generated folder you don't have and don't need. The only file inside the zip you
touch is `config.js`. The only file inside `truthguard-ai` that matches it is
`frontend/public/config.js` — and you only need that one if you're building from source
instead of using the zip.
