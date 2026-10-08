# Detection isn't working — diagnose it in 60 seconds

This project now ships its **own backend** (`backend/`, FastAPI). So "nothing detects" is almost always one of four things, in this order:

1. **the backend isn't running** (local) or **isn't deployed / is asleep** (Render)
2. **the frontend is pointing at the wrong URL**
3. **auth is on at one end but not the other**
4. **CORS**

Run the diagnostic first. It answers all four:

```bash
python tools/check_backend.py                       # reads frontend/.env
python tools/check_backend.py http://127.0.0.1:8000 # local backend
python tools/check_backend.py https://truthguard-backend.onrender.com

# or from frontend/
npm run backend:check      # Windows
npm run backend:check3     # macOS / Linux
```

It tests DNS → `/health` → sends a real generated PNG to `detect-image` → `fact-check` → CORS preflight, then prints a numbered **DIAGNOSIS** with the fix. Standard library only.

> Read the diagnosis top to bottom and fix the **first** item only. The rest are usually consequences of it.

Full deployment instructions live in **[`DEPLOY.md`](DEPLOY.md)**. Its §8 has a 16-row troubleshooting table.

---

## The decision tree

```
python tools/check_backend.py
        │
        ├─ "Backend URL is not configured" ──► frontend/.env has no VITE_API_BASE_URL.
        │                                       Set it, restart npm run dev.
        │
        ├─ connection refused / DNS fails ─────► the backend is NOT RUNNING.
        │      (local)                            cd backend
        │                                         pip install -r requirements.txt
        │                                         python -m uvicorn main:app --port 8000
        │      (Render)                           Dashboard → Logs. Redeploy if the
        │                                         build failed; wake it if it slept.
        │
        ├─ 404 on everything ─────────────────► wrong URL, or the service has no app.
        │                                       On Render check Root Directory = backend
        │                                       and the Start Command uses --port $PORT.
        │
        ├─ /health PASS but detect-image 404 ──► path mismatch. This backend serves
        │                                       /api/v1/detect-image exactly; check the
        │                                       URL has no extra path or trailing slash.
        │
        ├─ 503 on every AI call ───────────────► AUTH_ENABLED=true with no
        │                                       SUPABASE_JWT_SECRET. That is the
        │                                       fail-closed behaviour working. Set the
        │                                       secret, or AUTH_ENABLED=false to demo.
        │
        ├─ 401 ────────────────────────────────► auth is ON at the backend but the
        │                                       frontend sends no token: set
        │                                       VITE_DEMO_MODE=false, add the Supabase
        │                                       URL + anon key, REDEPLOY, then SIGN IN.
        │                                       Confirm in DevTools → Network →
        │                                       detect-image → Request Headers →
        │                                       `Authorization: Bearer eyJ…`
        │
        ├─ 413 / 415 / 422 ────────────────────► validation working correctly.
        │                                       Read the `detail` — it names the field.
        │                                       The multipart field MUST be `file`.
        │
        ├─ 429 ────────────────────────────────► rate limited (20 AI calls/minute).
        │                                       Wait for `Retry-After`. Expected if you
        │                                       clicked fast; that is Part C.3 working.
        │
        ├─ 502 / 503 / 504 after working ──────► Render free tier went to sleep
        │                                       (~15 min idle). Open /health in a tab,
        │                                       wait ~40 s, retry.
        │
        └─ all PASS but the browser fails ─────► CORS, or a stale build:
                                                · the error names `Authorization` →
                                                  allow_headers (already set in main.py)
                                                · the error names an origin →
                                                  FRONTEND_ORIGIN must match the
                                                  browser's origin string EXACTLY
                                                · then hard-refresh (Ctrl/Cmd+Shift+R)
                                                  and restart npm run dev
```

---

## "All checks pass but the browser still fails"

1. **Hard refresh** — `Ctrl/Cmd + Shift + R`. Vite caches transformed modules.
2. **Restart `npm run dev`.** `.env` changes are not always hot-applied.
3. **Check the request the browser actually made** — DevTools → Network → `detect-image` → **Request URL**. It must match your `.env` value exactly. If it shows something else, your edit didn't take (wrong file, or unsaved).
4. **Changed a `VITE_*` var on Vercel/Netlify?** Those are inlined into the bundle **at build time**. Editing the dashboard does nothing until you **redeploy**.
5. **College network or VPN?** Try a phone hotspot. Institutional proxies commonly block `*.onrender.com`.
6. **Ad blocker / privacy extension?** Test in a private window.
7. **Local development and tired of CORS?** Add `VITE_USE_DEV_PROXY=true` to `frontend/.env` and restart. The app then calls same-origin `/api/...` and Vite forwards it to the backend, so there is no cross-origin request at all. Dev only — production still exercises the real CORS path.

---

## Prove the backend works without the frontend at all

This separates "backend broken" from "frontend wiring broken" in one step.

```bash
# health + configuration
curl -s http://127.0.0.1:8000/health | python -m json.tool

# a real detection (needs AUTH_ENABLED=false, or pass a Bearer token)
curl -s -X POST http://127.0.0.1:8000/api/v1/detect-image \
     -F "file=@some-photo.jpg" | python -m json.tool

# a real fact-check
curl -s -X POST http://127.0.0.1:8000/api/v1/fact-check \
     -H "Content-Type: application/json" \
     -d '{"claim":"Vaccines cause autism in children"}' | python -m json.tool
```

Or use the interactive docs: **http://127.0.0.1:8000/docs**.

If those work and the browser doesn't, the problem is in the frontend's configuration or CORS — not in the API.

---

## Run without any deployment (offline rehearsal)

Two independent ways, both zero-network:

**A. The real backend, no model, no internet needed for detection**
```bash
cd backend
pip install -r requirements.txt
AUTH_ENABLED=false FACT_CHECK_ENGINE=mock python -m uvicorn main:app --port 8000
```
Detection is genuine image forensics. Fact-checking uses the offline knowledge base.

**B. The standalone stub** (`tools/mock_backend.py`, no pip install at all)
```bash
python tools/mock_backend.py
```
Deterministic verdicts from the filename — `deepfake_ceo.png` → Likely Fake, `family_photo_real.jpg` → Likely Real. Useful for rehearsing the exact demo sequence. **It is a stub, not a detector**; label it as such if you show it.

Either way, `frontend/.env` already points at `http://127.0.0.1:8000`.

---

**Still stuck?** Paste the full output of `python tools/check_backend.py <your-url>`, plus:
- the first red line from the browser Console (F12)
- the failing request's **URL** and **status** from the Network tab
- your Render service's last 20 log lines

That is enough to pinpoint it immediately.
