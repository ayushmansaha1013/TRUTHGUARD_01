/* ===========================================================================
 * config.js — RUNTIME configuration for TruthGuard AI
 * ===========================================================================
 *
 * You can point the whole app at your own services by editing the FOUR lines
 * marked below. No build step, no npm, no Node — edit this file, re-upload the
 * folder, refresh.
 *
 * WHY THIS FILE EXISTS
 * --------------------
 * Vite replaces every `import.meta.env.VITE_*` value at BUILD time. The built
 * JavaScript in `dist/` therefore has those values hard-coded into it: a bundle
 * built before the URL was configured can never be fixed afterwards, and a
 * bundle built against localhost can never be pointed at Render.
 *
 * That is fine on a Git-connected host, where you set variables once and the
 * host builds for you. It is a dead end on **Netlify Drop** and every other
 * "upload a prebuilt folder" host, where there is no build step and no
 * environment-variable screen.
 *
 * This file is fetched by the browser at RUNTIME, before the app bundle runs.
 *
 * PRECEDENCE (per value)
 * ----------------------
 *   1. a non-empty value in this file      <- wins
 *   2. the value baked in at build time    <- VITE_* from .env
 *   3. nothing configured                  -> the app says so, loudly, and why
 *
 * ==================== WHAT TO PUT IN EACH FIELD ============================
 *
 *  apiBaseUrl        REQUIRED for the Image Scanner and Fact Checker.
 *                    Your DEPLOYED BACKEND. Not the frontend. Not Supabase.
 *                      Render  -> https://<your-service>.onrender.com
 *                      Railway -> https://<your-service>.up.railway.app
 *                      Local   -> http://localhost:8000
 *                    Rules: include https://, NO trailing slash, NO /api/v1.
 *                    Check it first: open <that-url>/health in a browser tab.
 *                    You must see JSON like {"status":"ok",...}. If you do not,
 *                    fix the backend before touching the frontend — no frontend
 *                    setting can compensate for a backend that is not up.
 *
 *  supabaseUrl       Supabase -> Settings -> API -> Project URL
 *                      https://<your-project-ref>.supabase.co
 *
 *  supabaseAnonKey   Supabase -> Settings -> API -> Project API keys -> `anon` `public`
 *                      A long string starting with eyJ...
 *                    This one is SAFE to be public. It identifies the project;
 *                    it does not authorise access. Row Level Security in the
 *                    database decides what each user may read or write. The
 *                    `service_role` key is the dangerous one — NEVER put that
 *                    here, or anywhere a browser can read.
 *
 *  demoMode          true  -> skip login entirely (no Supabase needed)
 *                    false -> require real sign-in (needed for the educator
 *                             dashboard and the RLS demo)
 *
 * If Supabase login is not working but you want to demo the AI, set demoMode to
 * true and fill in only apiBaseUrl. Everything except real accounts still works.
 * ===========================================================================
 */

window.__TRUTHGUARD__ = {
  //                      ↓↓↓  FILL THESE IN  ↓↓↓
  apiBaseUrl: '',
  supabaseUrl: '',
  supabaseAnonKey: '',

  // 'true' or 'false' (string or boolean both work)
  demoMode: false,
}
