import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// DEV-ONLY backend proxy target. See `server.proxy` below for why this exists.
const BACKEND_PROXY_TARGET = process.env.BACKEND_PROXY_TARGET || 'http://127.0.0.1:8000'

// SECURITY NOTE (Part C.4 — Secure Environment Variables):
// Vite only exposes env vars that are prefixed with `VITE_`. Everything else in
// .env stays server-side / build-time only, so a Supabase SERVICE_ROLE key or a
// JWT secret can never accidentally be bundled into the browser JS.
// Also: never put anything in .env that you would not be happy for a user to
// read in DevTools. The Supabase *anon* key is public-by-design and is safe,
// because Row Level Security (RLS) — not the key — is what protects the data.
export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0', // bind all interfaces so this works in preview/dev containers
    port: 5173,
    strictPort: false,
    // Vite ≥5.4 validates the incoming Host header (DNS-rebinding protection) and
    // 403s anything not on this list. `true` accepts any host, which is what a
    // sandboxed/tunneled preview needs. For a real deployment prefer an explicit
    // list, e.g. allowedHosts: ['localhost', 'truthguard.vercel.app']
    allowedHosts: true,
    // No `hmr` override: the defaults work for local `npm run dev`. If you serve
    // the dev server through an HTTPS tunnel and hot reload fails to connect,
    // add:  hmr: { protocol: 'wss', clientPort: 443 }

    // ------------------------------------------------------------------
    // DEV-ONLY: forward same-origin API calls to the local backend.
    //
    // WHY: opt in by setting VITE_USE_DEV_PROXY=true in frontend/.env. The app
    // then calls relative paths, the browser sees ONE origin, and there is no
    // CORS preflight at all — which removes the most confusing class of local
    // development failure ("curl works, the browser doesn't").
    //
    // WHY this is dev-only and NOT how production works: `vite preview` and a
    // static host (Vercel/Netlify) do not run this proxy. In production the
    // browser calls the Render URL directly and the backend's CORSMiddleware
    // handles it. Shipping a proxy would hide a real CORS misconfiguration until
    // after deployment, which is exactly the wrong time to discover it.
    // ------------------------------------------------------------------
    proxy: {
      '/api': { target: BACKEND_PROXY_TARGET, changeOrigin: true },
      '/health': { target: BACKEND_PROXY_TARGET, changeOrigin: true },
    },
  },
  preview: {
    host: '0.0.0.0',
    port: 4173,
    allowedHosts: true,
  },
  build: {
    outDir: 'dist',
    sourcemap: false, // SECURITY: don't ship readable source maps in production
    // `three` (~684 kB raw / ~176 kB gzip) is imported with a dynamic import()
    // inside Hero3D, so Vite emits it as a SEPARATE lazy chunk: it is never part
    // of the initial download and is only fetched when a 3D scene actually
    // mounts. The default 500 kB warning is about the *initial* bundle, so we
    // raise the limit rather than "fix" a split that is already correct.
    chunkSizeWarningLimit: 800,
  },
  test: {
    environment: 'jsdom',
    globals: true,
    include: ['src/**/*.test.{js,jsx}'],
    css: false,
  },
})
