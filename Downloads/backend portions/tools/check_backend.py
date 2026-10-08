#!/usr/bin/env python3
"""
=============================================================================
check_backend.py — "why is nothing detecting?" in one command
=============================================================================
Standard library only. No pip install needed. Python 3.8+.

USAGE
    python tools/check_backend.py                     # reads frontend/.env
    python tools/check_backend.py https://truthguard-backend.onrender.com
    python tools/check_backend.py --origin http://localhost:5173

It runs 7 checks against your deployed FastAPI backend and then prints a
DIAGNOSIS that maps the failure to the exact fix. Run it before touching any
frontend code — 9 times out of 10 the problem is the URL, CORS, or a sleeping
Render service, not React.
=============================================================================
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import socket
import struct
import sys
import urllib.error
import urllib.request
import zlib
from urllib.parse import urlparse

TEAL, RED, YEL, DIM, BOLD, OFF = (
    "\033[36m", "\033[31m", "\033[33m", "\033[2m", "\033[1m", "\033[0m",
)
if os.name == "nt" and not os.environ.get("WT_SESSION"):
    os.system("")  # enables ANSI escapes in legacy Windows consoles

PASS, FAIL, WARN = f"{TEAL}PASS{OFF}", f"{RED}FAIL{OFF}", f"{YEL}WARN{OFF}"

findings: list[tuple[str, str]] = []
# Mutable holder so the nested try-blocks in main() can flag "the app answered".
_state = {"app_reachable": False}


def note(kind: str, msg: str) -> None:
    findings.append((kind, msg))


def head(label: str, status: str, detail: str = "") -> None:
    line = f"  [{status}] {label}"
    if detail:
        line += f"  {DIM}{detail}{OFF}"
    print(line)


# -----------------------------------------------------------------------------
# A real, tiny, valid 8x8 PNG built from scratch (no Pillow dependency).
# Sent as multipart/form-data exactly like the browser does.
# -----------------------------------------------------------------------------
def make_png(width: int = 8, height: int = 8) -> bytes:
    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    raw = b""
    for y in range(height):
        raw += b"\x00"  # filter type 0 (none) per scanline
        for x in range(width):
            raw += bytes(((x * 28) % 256, (y * 40) % 256, 190))

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )


def http(method: str, url: str, *, data=None, headers=None, timeout=25):
    """Return (status, headers_dict, body_bytes) or raise urllib.error.URLError."""
    req = urllib.request.Request(url, data=data, method=method)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            return res.status, {k.lower(): v for k, v in res.headers.items()}, res.read()
    except urllib.error.HTTPError as e:  # a 4xx/5xx IS a response — very informative
        return e.code, {k.lower(): v for k, v in (e.headers or {}).items()}, e.read()


def read_env_url() -> str | None:
    here = os.path.dirname(os.path.abspath(__file__))
    env_path = os.path.normpath(os.path.join(here, "..", "frontend", ".env"))
    if not os.path.exists(env_path):
        return None
    for line in open(env_path, encoding="utf-8"):
        m = re.match(r"\s*VITE_API_BASE_URL\s*=\s*(.+?)\s*$", line)
        if m:
            return m.group(1).strip().strip("'\"")
    return None


# =============================================================================
def main() -> int:
    ap = argparse.ArgumentParser(description="Diagnose the TruthGuard AI backend connection.")
    ap.add_argument("url", nargs="?", help="backend base URL (else read from frontend/.env)")
    ap.add_argument("--origin", default="http://localhost:5173",
                    help="frontend origin used for the CORS preflight check")
    ap.add_argument("--timeout", type=int, default=25)
    args = ap.parse_args()

    base = (args.url or read_env_url() or "").rstrip("/")

    print(f"\n{BOLD}{TEAL}TruthGuard AI — backend connectivity check{OFF}\n")

    # ---------------------------------------------------------- 0. got a URL?
    if not base:
        head("Backend URL configured", FAIL, "no VITE_API_BASE_URL found")
        print(f"\n{RED}Nothing to test.{OFF} Set VITE_API_BASE_URL in frontend/.env, or pass a URL:\n")
        print("    python tools/check_backend.py https://YOUR-BACKEND.onrender.com\n")
        return 2

    print(f"  Target : {BOLD}{base}{OFF}")
    print(f"  Origin : {args.origin}   (for the CORS check)\n")

    if not base.startswith(("http://", "https://")):
        head("URL format", FAIL, "must start with http:// or https://")
        note("url", "VITE_API_BASE_URL must include the scheme, e.g. https://me-gt.hf.space")
        return finish(2)

    parsed = urlparse(base)
    if parsed.path not in ("", "/"):
        head("URL shape", WARN, f"has a path '{parsed.path}' — usually the base URL should be bare")
        note("url", "Drop any trailing path: use https://me-gt.hf.space, not .../api or .../docs")

    if "username-truthguard-backend" in base:
        head("Placeholder URL still in use", FAIL, "this is the shipped example, not your Space")
        note("placeholder",
             "frontend/.env still contains the PLACEHOLDER 'username-truthguard-backend.hf.space'. "
             "Replace it with your real deployed backend URL.")

    # ------------------------------------------------------------- 1. DNS/TCP
    try:
        ip = socket.gethostbyname(parsed.hostname)
        head("DNS resolves", PASS, f"{parsed.hostname} -> {ip}")
    except OSError as e:
        head("DNS resolves", FAIL, str(e))
        note("dns", f"{parsed.hostname} does not resolve. Check the spelling of the Space name.")
        return finish(2)

    # NOTE: *.hf.space is a WILDCARD DNS zone — every subdomain resolves, even
    # ones that don't exist. So a green DNS check proves nothing on its own.
    if parsed.hostname.endswith(".hf.space"):
        print(f"        {DIM}(*.hf.space is a wildcard zone, so DNS always resolves. "
              f"The real test is the HTTP response below.){OFF}")

    # ------------------------------------------------------------- 2. /health
    print()
    try:
        st, hdrs, body = http("GET", f"{base}/health", timeout=args.timeout)
        if st != 404:
            _state["app_reachable"] = True
        if st == 200:
            head("GET /health", PASS, f"200 in {_size(body)}")
            try:
                print(f"        {DIM}{json.loads(body)}{OFF}")
            except Exception:
                pass
        elif st == 404:
            head("GET /health", FAIL, "404 — no application is running at this URL")
            note("noapp",
                 "The host answered 404, so nothing is deployed there. On Hugging Face this means "
                 "the Space name is wrong, the Space is still building, or it was deleted/renamed.")
        elif st in (401, 403):
            head("GET /health", WARN, f"{st} — /health is behind auth")
            note("healthauth",
                 "/health should stay PUBLIC so uptime probes work. Move it outside the "
                 "dependencies=[Depends(require_auth)] router (see backend_security/integration_example.py).")
        elif st in (502, 503, 504):
            head("GET /health", WARN, f"{st} — gateway/app not ready")
            note("cold",
                 f"HTTP {st} from the HF proxy usually means the Space is ASLEEP or still starting. "
                 "Open the Space URL in a browser tab, wait for it to wake (~40 s), then re-run this.")
        else:
            head("GET /health", WARN, f"unexpected {st}")
            note("healthother", f"/health returned {st}: {body[:160]!r}")
    except urllib.error.URLError as e:
        head("GET /health", FAIL, f"connection error: {e.reason}")
        note("unreachable",
             f"Could not connect to {parsed.hostname}: {e.reason}. Check your internet, "
             "any VPN/college proxy, and that the Space is running (not paused).")
    except TimeoutError:
        head("GET /health", FAIL, f"timed out after {args.timeout}s")
        note("timeout", "The server accepted the connection but never replied — classic cold start. Retry in 60s.")

    # ------------------------------------------- 3. detect-image (the real test)
    print()
    png = make_png()
    boundary = "----TruthGuardDiagBoundary7d4a1b"
    multipart = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="diag.png"\r\n'
        f"Content-Type: image/png\r\n\r\n"
    ).encode() + png + f"\r\n--{boundary}--\r\n".encode()

    try:
        st, hdrs, body = http(
            "POST", f"{base}/api/v1/detect-image",
            data=multipart,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            timeout=max(args.timeout, 60),
        )
        text = body.decode("utf-8", "replace")
        if st != 404:
            _state["app_reachable"] = True
        if st == 200:
            head("POST /api/v1/detect-image", PASS, "200 — detection works, unauthenticated")
            print(f"        {DIM}{text[:220]}{OFF}")
            note("ok", "The backend is live and accepting images. If the browser still fails, it is CORS or the .env URL.")
        elif st in (401, 403):
            head("POST /api/v1/detect-image", WARN, f"{st} — JWT middleware is ACTIVE")
            note("jwt",
                 f"The backend now requires a Supabase JWT (that is Part C.1 working correctly). "
                 f"Fix: in frontend/.env set VITE_DEMO_MODE=false and fill in VITE_SUPABASE_URL + "
                 f"VITE_SUPABASE_ANON_KEY, then SIGN IN in the app. Demo mode sends no token, so it gets {st}.")
        elif st == 404:
            if _state["app_reachable"]:
                # /health answered but this path did not -> a genuine routing mismatch.
                head("POST /api/v1/detect-image", FAIL, "404 — route not found")
                note("route404",
                     "The app is there but this path is not. Check the router prefix: the frontend "
                     "calls /api/v1/detect-image exactly. If your routes are /detect-image, either "
                     "add the /api/v1 prefix on the backend or tell me and I will change the paths.")
            else:
                # Nothing is deployed at all; finding #1 already says so. Don't
                # pile a second, misleading "wrong path" conclusion on top.
                head("POST /api/v1/detect-image", FAIL, "404 — nothing deployed at this URL")
        elif st == 422:
            head("POST /api/v1/detect-image", WARN, "422 — reached the route, rejected the body")
            print(f"        {DIM}{text[:220]}{OFF}")
            note("field422",
                 "A 422 means the path is CORRECT but validation failed. Most common cause: the "
                 "multipart field is not named 'file'. Confirm your signature is "
                 "`file: UploadFile = File(...)`.")
        elif st == 415:
            head("POST /api/v1/detect-image", WARN, "415 — content type rejected")
            note("ctype", "The backend rejected image/png. Check its ALLOWED_CONTENT_TYPES list.")
        elif st == 429:
            head("POST /api/v1/detect-image", WARN, "429 — rate limited")
            note("rate", "You are being rate limited. Wait a minute and re-run.")
        elif st >= 500:
            head("POST /api/v1/detect-image", FAIL, f"{st} — server-side error")
            print(f"        {DIM}{text[:220]}{OFF}")
            note("server5xx",
                 f"The route exists but the model code threw ({st}). Check the Space logs: "
                 "HF Space -> Settings/Logs. Often a missing model weight or an OOM on the free tier.")
        else:
            head("POST /api/v1/detect-image", WARN, f"unexpected {st}")
            print(f"        {DIM}{text[:220]}{OFF}")
    except urllib.error.URLError as e:
        head("POST /api/v1/detect-image", FAIL, f"connection error: {e.reason}")
        note("unreachable", f"Cannot reach the host: {e.reason}")
    except TimeoutError:
        head("POST /api/v1/detect-image", FAIL, "timed out")
        note("timeout", "Inference took too long. Free-tier HF Spaces can be very slow on a cold model.")

    # ------------------------------------------------------ 4. fact-check route
    print()
    try:
        st, hdrs, body = http(
            "POST", f"{base}/api/v1/fact-check",
            data=json.dumps({"claim": "The Eiffel Tower was built in 1889 for the World Fair"}).encode(),
            headers={"Content-Type": "application/json"},
            timeout=max(args.timeout, 60),
        )
        text = body.decode("utf-8", "replace")
        label = {200: PASS}.get(st, WARN if st in (401, 403, 422) else FAIL)
        head("POST /api/v1/fact-check", label, f"{st}")
        print(f"        {DIM}{text[:200]}{OFF}")
        if st == 404 and _state["app_reachable"]:
            note("fc404", "The fact-check route is missing or at a different path.")
    except (urllib.error.URLError, TimeoutError) as e:
        head("POST /api/v1/fact-check", FAIL, str(getattr(e, "reason", e)))

    # ------------------------------------------------------------------ 5. CORS
    print()
    try:
        st, hdrs, _ = http(
            "OPTIONS", f"{base}/api/v1/detect-image",
            headers={
                "Origin": args.origin,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "authorization,content-type",
            },
            timeout=args.timeout,
        )
        allow_origin = hdrs.get("access-control-allow-origin", "")
        allow_methods = hdrs.get("access-control-allow-methods", "")
        # A preflight only really succeeded on a 2xx FROM YOUR APP. Hugging Face's
        # edge proxy answers OPTIONS itself — with correct-looking CORS headers —
        # even for a Space that does not exist, which would otherwise read as a
        # green CORS check on a 404 backend. So: no CORS verdict unless the app
        # itself is demonstrably reachable.
        if not _state['app_reachable']:
            head("CORS preflight", WARN, "unproven — no endpoint responded, so this is the proxy talking")
            note("cors404",
                 "CORS cannot be verified until the backend actually responds. Hugging Face's edge "
                 "proxy answers OPTIONS preflights generically (allow-origin: " + allow_origin + "), "
                 "which looks like a pass but proves nothing. Re-run once the Space is deployed.")
        elif st not in (200, 204):
            head("CORS preflight", WARN, f"preflight returned {st}, so CORS is unproven")
            if st == 404:
                note("cors404",
                     "CORS could not be verified because the endpoint 404s. Re-run this check "
                     "once the backend is actually deployed.")
        elif allow_origin in ("*", args.origin):
            head("CORS preflight", PASS, f"allow-origin: {allow_origin}")
        elif not allow_origin:
            head("CORS preflight", FAIL, "no Access-Control-Allow-Origin header")
            note("cors",
                 f"The browser will BLOCK every call from {args.origin} even though the API works "
                 "with curl. Fix on the backend: add CORSMiddleware with your frontend origin in "
                 "allow_origins (snippet at the bottom of backend_security/jwt_auth.py). "
                 "Note: the Authorization header must be in allow_headers.")
        else:
            head("CORS preflight", WARN, f"{st}; allow-origin={allow_origin or '(none)'}; methods={allow_methods or '(none)'}")
            if allow_origin and allow_origin != args.origin:
                note("cors",
                     f"CORS allows '{allow_origin}' but your app runs at '{args.origin}'. "
                     "Add your origin to allow_origins.")
    except (urllib.error.URLError, TimeoutError) as e:
        head("CORS preflight", WARN, f"could not test: {getattr(e, 'reason', e)}")

    return finish(0)


def _size(b: bytes) -> str:
    return f"{len(b)} B" if len(b) < 1024 else f"{len(b)/1024:.1f} kB"


def finish(code: int) -> int:
    print(f"\n{BOLD}DIAGNOSIS{OFF}")
    if not findings:
        print(f"  {TEAL}No problems detected — the backend looks healthy.{OFF}")
        print("  If the browser still fails, hard-refresh (Ctrl/Cmd+Shift+R) and check that")
        print("  VITE_API_BASE_URL in frontend/.env has no trailing slash or typo, then")
        print("  restart `npm run dev` so Vite re-reads .env.")
        return 0

    order = {"placeholder": 0, "url": 0, "dns": 0, "cors404": 1, "noapp": 1, "unreachable": 1, "timeout": 1,
             "cold": 2, "cors": 2, "jwt": 3, "route404": 3, "field422": 4, "ctype": 4,
             "server5xx": 5, "healthauth": 6, "rate": 6, "fc404": 6, "healthother": 7}
    for i, (kind, msg) in enumerate(sorted(findings, key=lambda f: order.get(f[0], 9)), 1):
        print(f"\n  {YEL}{i}.{OFF} {msg}")
    print()
    return code or 1


if __name__ == "__main__":
    sys.exit(main())
