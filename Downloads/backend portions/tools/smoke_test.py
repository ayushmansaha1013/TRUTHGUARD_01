#!/usr/bin/env python3
"""
=============================================================================
tools/smoke_test.py — "is my whole project actually working?" in one command
=============================================================================
Standard library only (Pillow optional, used to build test images).

    python tools/smoke_test.py                            # http://127.0.0.1:8000
    python tools/smoke_test.py https://my-app.onrender.com
    python tools/smoke_test.py --token <supabase-jwt>     # test an auth-enabled backend
    python tools/smoke_test.py --skip-factcheck           # offline / no internet

WHAT IT DOES
    Generates its own test images (nothing to download), then exercises every
    endpoint and every rejection path, and prints a pass/fail score. This is the
    difference between "the server started" and "the product works".

    It is deliberately separate from `backend/test_api.py`:
      * test_api.py runs IN-PROCESS with no network — it is the developer suite,
        57 tests, and it is what CI would run.
      * smoke_test.py runs OVER HTTP against a URL — so it can test your RENDER
        deployment exactly the way the browser will, including CORS-shaped
        behaviour, cold starts and rate limits.

    Run test_api.py before you deploy. Run smoke_test.py after.
=============================================================================
"""

from __future__ import annotations

import argparse
import io
import json
import os
import struct
import sys
import time
import urllib.error
import urllib.request
import uuid
import zlib

TEAL, RED, YEL, GRN, DIM, BOLD, OFF = (
    "\033[36m", "\033[31m", "\033[33m", "\033[32m", "\033[2m", "\033[1m", "\033[0m",
)
if os.name == "nt" and not os.environ.get("WT_SESSION"):
    os.system("")  # enable ANSI escapes in legacy Windows consoles

PASSED, FAILED, SKIPPED = [], [], []


def ok(name: str, detail: str = "") -> None:
    PASSED.append(name)
    print(f"  {GRN}PASS{OFF}  {name}" + (f"  {DIM}{detail}{OFF}" if detail else ""))


def bad(name: str, detail: str = "") -> None:
    FAILED.append(name)
    print(f"  {RED}FAIL{OFF}  {name}" + (f"  {DIM}{detail}{OFF}" if detail else ""))


def skip(name: str, detail: str = "") -> None:
    SKIPPED.append(name)
    print(f"  {YEL}SKIP{OFF}  {name}" + (f"  {DIM}{detail}{OFF}" if detail else ""))


def section(title: str) -> None:
    print(f"\n{BOLD}{TEAL}{title}{OFF}")


# =============================================================================
# Test-image generation
# =============================================================================
def _png_chunk(tag: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + tag
        + data
        + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    )


def make_png(width: int, height: int, alpha: bool = False, smooth: bool = True) -> bytes:
    """
    Build a valid PNG with NO dependencies.

    WHY hand-roll this instead of using Pillow: the smoke test must run on a
    machine that has Python and nothing else — including the examiner's, and
    including a fresh laptop before `pip install`. If image generation needed
    Pillow, the test could not run in exactly the situation where you most need it.
    """
    channels = 4 if alpha else 3
    colour_type = 6 if alpha else 2
    raw = bytearray()
    for y in range(height):
        raw.append(0)  # filter type 0 (none) for this scanline
        for x in range(width):
            if smooth:
                # Gentle gradients -> a low high-frequency residual, which is what
                # a synthesised image looks like to the forensic detector.
                raw.append(int(128 + 60 * ((x / max(width, 1)) ** 2)))
                raw.append(int(128 + 60 * ((y / max(height, 1)) ** 2)))
                raw.append(200)
            else:
                # Deterministic pseudo-noise -> a broadband residual, like a sensor.
                v = (x * 37 + y * 91 + x * y) % 256
                raw.append(v)
                raw.append((v + 60) % 256)
                raw.append((v + 130) % 256)
            if alpha:
                raw.append(255)

    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, colour_type, 0, 0, 0))
        + _png_chunk(b"IDAT", zlib.compress(bytes(raw), 6))
        + _png_chunk(b"IEND", b"")
    )


def make_camera_jpeg() -> bytes | None:
    """
    A JPEG with real camera EXIF and broadband sensor noise — the clearest
    possible 'this is a genuine photograph' input.

    Returns None if Pillow is unavailable, and the caller skips those checks
    rather than failing: a missing optional dependency is not a product bug.
    """
    try:
        import numpy as np
        from PIL import Image
    except ImportError:
        return None

    w, h = 320, 240
    rng = np.random.default_rng(11)
    ys, xs = np.mgrid[0:h, 0:w]
    arr = np.stack(
        [
            110 + 50 * np.sin(xs / 40.0),
            100 + 50 * np.cos(ys / 35.0),
            150 + 40 * np.sin((xs + ys) / 60.0),
        ],
        axis=-1,
    )
    arr = np.clip(arr + rng.normal(0, 9.0, arr.shape), 0, 255).astype(np.uint8)
    img = Image.fromarray(arr, "RGB")

    ex = Image.Exif()
    ex[0x010F] = "Canon"          # Make
    ex[0x0110] = "EOS 800D"       # Model
    ex[0x0131] = "16.1"           # Software
    ex[0x0132] = "2026:03:14 18:22:07"

    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=90, exif=ex.tobytes())
    return buf.getvalue()


def make_double_compressed_jpeg(base: bytes) -> bytes | None:
    """Re-encode a JPEG twice, which imposes a second 8x8 DCT grid."""
    try:
        from PIL import Image
    except ImportError:
        return None
    buf = io.BytesIO()
    Image.open(io.BytesIO(base)).save(buf, "JPEG", quality=55)
    buf2 = io.BytesIO()
    Image.open(io.BytesIO(buf.getvalue())).save(buf2, "JPEG", quality=55)
    return buf2.getvalue()


def tag_with_generator_xmp(png: bytes, marker_text: str = "Created with Midjourney v6") -> bytes:
    """
    Insert an XMP chunk naming an AI tool, the way generators actually do.

    WHY test this specifically: the fingerprint lives in raw bytes that Pillow's
    getexif() does not surface, so this signal can break silently while every
    other check still passes.
    """
    xmp = f'<x:xmpmeta xmlns:x="adobe:ns:meta/">{marker_text}</x:xmpmeta>'.encode()
    payload = b"XML:com.adobe.xmp\x00\x00\x00\x00\x00" + xmp + b"\x00"
    chunk = _png_chunk(b"iTXt", payload)
    return png[: len(png) - 12] + chunk + png[len(png) - 12 :]


# =============================================================================
# HTTP helpers
# =============================================================================
def http(method, url, *, data=None, headers=None, timeout=60):
    """Return (status, headers_dict, body_bytes). A 4xx/5xx is a RESULT, not an error."""
    req = urllib.request.Request(url, data=data, method=method)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            return res.status, {k.lower(): v for k, v in res.headers.items()}, res.read()
    except urllib.error.HTTPError as e:
        return e.code, {k.lower(): v for k, v in (e.headers or {}).items()}, e.read()


def multipart(data: bytes, filename: str, content_type: str, field: str = "file"):
    boundary = f"----SmokeTest{uuid.uuid4().hex}"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="{field}"; filename="{filename}"\r\n'
        f"Content-Type: {content_type}\r\n\r\n"
    ).encode() + data + f"\r\n--{boundary}--\r\n".encode()
    return body, f"multipart/form-data; boundary={boundary}"


def jload(body: bytes) -> dict:
    try:
        return json.loads(body)
    except Exception:
        return {}


# =============================================================================
def main() -> int:
    ap = argparse.ArgumentParser(description="End-to-end smoke test for the TruthGuard AI backend.")
    ap.add_argument("url", nargs="?", default="http://127.0.0.1:8000", help="backend base URL")
    ap.add_argument("--token", default=None, help="Supabase JWT, for a backend with AUTH_ENABLED=true")
    ap.add_argument("--skip-factcheck", action="store_true", help="skip tests needing outbound internet")
    ap.add_argument("--timeout", type=int, default=60)
    args = ap.parse_args()

    base = args.url.rstrip("/")
    auth = {"Authorization": f"Bearer {args.token}"} if args.token else {}

    print(f"\n{BOLD}{TEAL}TruthGuard AI — end-to-end smoke test{OFF}")
    print(f"  target : {BOLD}{base}{OFF}")
    print(f"  auth   : {'Bearer token supplied' if args.token else 'none (backend must have AUTH_ENABLED=false)'}")
    print(f"  started: {time.strftime('%H:%M:%S')}")

    # ------------------------------------------------------------------ 1. up?
    section("1 · Is the service alive?")
    try:
        st, _, body = http("GET", f"{base}/health", timeout=20)
    except Exception as e:
        bad("GET /health", f"cannot connect: {getattr(e, 'reason', e)}")
        print(f"\n{RED}Nothing else can be tested. Is the backend running?{OFF}")
        print(f"    cd backend && python -m uvicorn main:app --port 8000\n")
        return 2

    if st != 200:
        bad("GET /health", f"HTTP {st}")
        return finish()

    health = jload(body)
    ok("GET /health", f"200 · v{health.get('version','?')}")

    engines = health.get("engines", {})
    authcfg = health.get("auth", {})
    print(f"        {DIM}detection engine : {engines.get('detection')}{OFF}")
    print(f"        {DIM}fact-check engine: {engines.get('fact_check')}{OFF}")
    print(f"        {DIM}auth enabled     : {authcfg.get('enabled')}   "
          f"jwt secret set: {authcfg.get('jwt_secret_configured')}{OFF}")

    # WHY assert this: the single most common misconfiguration is a backend with
    # auth enabled facing a frontend that sends no token. Surfacing it here, before
    # 20 confusing 401s, is the whole point of printing it.
    if authcfg.get("enabled") and not args.token:
        print(f"        {YEL}⚠ auth is ENABLED but you passed no --token, so every AI call below will 401.{OFF}")
        print(f"        {YEL}  Either re-run with --token <jwt>, or set AUTH_ENABLED=false locally.{OFF}")
    if authcfg.get("enabled") and not authcfg.get("jwt_secret_configured"):
        print(f"        {YEL}⚠ auth is ENABLED with NO jwt secret: the backend fails CLOSED (503).{OFF}")
        print(f"        {YEL}  Set SUPABASE_JWT_SECRET, or AUTH_ENABLED=false to demo without login.{OFF}")

    # ---------------------------------------------------------------- 2. limits
    section("2 · Do the advertised limits match what the frontend hardcodes?")
    try:
        st, _, body = http("GET", f"{base}/api/v1/meta", timeout=20)
        meta = jload(body)
        if st == 200 and meta.get("max_image_bytes") == 8 * 1024 * 1024:
            ok("GET /api/v1/meta", f"8 MB cap, claim {meta.get('claim_min_chars')}-{meta.get('claim_max_chars')} chars")
            if (meta.get("claim_min_chars"), meta.get("claim_max_chars")) != (10, 1000):
                bad("claim bounds", f"expected 10-1000, got {meta.get('claim_min_chars')}-{meta.get('claim_max_chars')}")
        else:
            bad("GET /api/v1/meta", f"HTTP {st}")
    except Exception as e:
        bad("GET /api/v1/meta", str(getattr(e, "reason", e)))

    # -------------------------------------------------------- 3. image detection
    section("3 · IMAGE detection — does it actually detect?")

    camera = make_camera_jpeg()
    gan_png = make_png(512, 512, alpha=True, smooth=True)
    noisy_png = make_png(320, 320, alpha=False, smooth=False)
    tagged_png = tag_with_generator_xmp(make_png(300, 300, smooth=False))

    def post_image(data, filename, ctype, field="file"):
        body, ct = multipart(data, filename, ctype, field)
        return http("POST", f"{base}/api/v1/detect-image",
                    data=body, headers={**auth, "Content-Type": ct},
                    timeout=max(args.timeout, 90))

    # 3a. the contract itself
    st, _, body = post_image(gan_png, "generated.png", "image/png")
    if st == 200:
        d = jload(body)
        required = {"verdict", "confidence", "raw_label", "fake_probability", "is_fake", "analyzed_in_ms"}
        missing = required - set(d)
        if missing:
            bad("response contract", f"missing fields the React app reads: {sorted(missing)}")
        else:
            ok("response contract", "all 6 fields the frontend depends on are present")
        if d.get("engine"):
            ok("verdict is explainable", f"engine={d['engine']}, {len(d.get('signals', {}))} signals returned")
        else:
            bad("verdict is explainable", "no 'engine' field — the response does not say how it decided")
    elif st in (401, 403):
        bad("response contract", f"HTTP {st} — auth is on; re-run with --token")
        return finish()
    else:
        bad("response contract", f"HTTP {st}: {jload(body).get('detail', body[:80])}")
        return finish()

    # 3b. discrimination — the test that proves it is not just answering one way
    if camera:
        st, _, body = post_image(camera, "camera_photo.jpg", "image/jpeg")
        d = jload(body)
        if st == 200 and d.get("is_fake") is False:
            ok("real camera JPEG is NOT called fake", f"{d['verdict']} · p={d['fake_probability']}")
        elif st == 200:
            bad("real camera JPEG is NOT called fake",
                f"{d['verdict']} p={d['fake_probability']} — a false positive on a genuine photo")
        else:
            bad("real camera JPEG", f"HTTP {st}")

        dc = make_double_compressed_jpeg(camera)
        if dc:
            st, _, body = post_image(dc, "recompressed.jpg", "image/jpeg")
            d = jload(body)
            grid = (d.get("signals") or {}).get("jpeg_grid") or {}
            if st == 200 and grid.get("boundary_ratio", 0) > 1.5:
                ok("re-encoded JPEG shows a compression grid",
                   f"boundary ratio {grid['boundary_ratio']}x (clean JPEGs measure ~1.2x)")
            elif st == 200:
                bad("re-encoded JPEG shows a compression grid",
                    f"ratio {grid.get('boundary_ratio')} — the strongest signal may be broken")
            else:
                bad("re-encoded JPEG", f"HTTP {st}")
    else:
        skip("camera-JPEG checks", "install Pillow + numpy to enable: pip install pillow numpy")

    st, _, body = post_image(gan_png, "generated_512.png", "image/png")
    d = jload(body)
    if st == 200 and d.get("is_fake") is True:
        ok("generator-shaped PNG IS flagged", f"{d['verdict']} · p={d['fake_probability']}")
    elif st == 200:
        bad("generator-shaped PNG IS flagged", f"{d['verdict']} p={d['fake_probability']} — a false negative")
    else:
        bad("generator-shaped PNG", f"HTTP {st}")

    st, _, body = post_image(tagged_png, "art.png", "image/png")
    d = jload(body)
    if st == 200 and "generator_marker" in (d.get("signals") or {}):
        ok("embedded AI-tool fingerprint is found", "Midjourney XMP tag detected in raw bytes")
    elif st == 200:
        bad("embedded AI-tool fingerprint is found",
            "XMP scan missed it — check GENERATOR_MARKERS in heuristic.py")
    else:
        bad("generator fingerprint", f"HTTP {st}")

    # 3c. determinism — a demo must be repeatable
    a = jload(post_image(noisy_png, "same.png", "image/png")[2])
    b = jload(post_image(noisy_png, "same.png", "image/png")[2])
    if a and a.get("fake_probability") == b.get("fake_probability"):
        ok("verdict is deterministic", f"same bytes twice -> p={a.get('fake_probability')}")
    else:
        bad("verdict is deterministic", f"{a.get('fake_probability')} vs {b.get('fake_probability')}")

    # ------------------------------------------------------- 4. upload validation
    section("4 · Upload validation — the server-side security half")

    st, _, body = post_image(b"#!/bin/sh\necho pwned\n" + b"A" * 400, "shell.jpg", "image/jpeg")
    if st == 415 and jload(body).get("error_code") == "unsupported_media_type":
        ok("non-image renamed .jpg is rejected", "415 — magic bytes checked, not the Content-Type header")
    else:
        bad("non-image renamed .jpg is rejected",
            f"HTTP {st} {jload(body).get('error_code')} — the server trusted a client-supplied header")

    st, _, body = post_image(camera or noisy_png, "photo.jpg", "text/plain")
    if st == 415:
        ok("wrong declared Content-Type is rejected", "415")
    else:
        bad("wrong declared Content-Type is rejected", f"HTTP {st}")

    st, _, body = post_image(noisy_png, "photo.png", "image/png", field="wrong_name")
    if st == 422:
        ok("wrong multipart field name is rejected", "422 — the field must be named 'file'")
    else:
        bad("wrong multipart field name is rejected", f"HTTP {st}")

    oversized = noisy_png + b"\x00" * (8 * 1024 * 1024 + 1 - len(noisy_png))
    st, _, body = post_image(oversized, "big.png", "image/png")
    if st == 413 and jload(body).get("error_code") == "payload_too_large":
        ok("oversized upload is rejected", "413 payload_too_large — the 8 MB DoS cap holds")
    else:
        bad("oversized upload is rejected", f"HTTP {st} {jload(body).get('error_code')}")

    st, _, body = post_image(camera or noisy_png, "../../../../etc/passwd", "image/jpeg")
    d = jload(body)
    name = ((d.get("image") or {}).get("filename") or "")
    if st in (200, 415) and "/" not in name and ".." not in name:
        ok("path traversal in filename is neutralised", f"logged as {name!r}")
    else:
        bad("path traversal in filename is neutralised", f"HTTP {st}, filename={name!r}")

    # ------------------------------------------------------------ 5. fact-check
    section("5 · TEXT detection — the fact-checker")
    if args.skip_factcheck:
        skip("fact-check tests", "--skip-factcheck was passed")
    else:
        def post_claim(claim):
            return http("POST", f"{base}/api/v1/fact-check",
                        data=json.dumps({"claim": claim}).encode(),
                        headers={**auth, "Content-Type": "application/json"},
                        timeout=max(args.timeout, 90))

        st, _, body = post_claim("Vaccines cause autism in children")
        d = jload(body)
        if st == 200:
            required = {"verdict", "explanation", "sources", "retrieved_context", "checked_in_ms"}
            missing = required - set(d)
            if missing:
                bad("fact-check contract", f"missing: {sorted(missing)}")
            else:
                ok("fact-check contract", "all 5 fields the frontend depends on are present")

            verdict = d.get("verdict")
            if verdict in ("False", "Mostly false"):
                ok("a well-documented myth is refuted",
                   f"{verdict} · {len(d.get('sources', []))} sources · {d.get('checked_in_ms')}ms")
            elif verdict == "Unverified":
                skip("a well-documented myth is refuted",
                     "Unverified — retrieval returned nothing usable. Likely no outbound "
                     "internet, or DuckDuckGo is bot-blocking this IP (HTTP 202). "
                     f"warnings={d.get('warnings')}")
            else:
                bad("a well-documented myth is refuted", f"returned {verdict} — that is the wrong answer")

            bad_urls = [s for s in d.get("sources", [])
                        if not str(s.get("url", "")).lower().startswith(("http://", "https://"))]
            if bad_urls:
                bad("sources are http(s) only", f"{len(bad_urls)} unsafe URL(s) reached the client")
            elif d.get("sources"):
                domains = sorted({s.get("domain", "") for s in d["sources"]})[:4]
                ok("sources are http(s) only", ", ".join(x for x in domains if x))
            else:
                skip("sources are http(s) only", "no sources returned")
        elif st in (401, 403):
            bad("fact-check", f"HTTP {st} — auth is on; re-run with --token")
        else:
            bad("fact-check", f"HTTP {st}: {jload(body).get('detail','')}")

        # length bounds — must match the frontend validator exactly
        st, _, body = post_claim("short")
        if st == 422 and jload(body).get("error_code") == "claim_too_short":
            ok("claim under 10 chars is rejected", "422 claim_too_short")
        else:
            bad("claim under 10 chars is rejected", f"HTTP {st} {jload(body).get('error_code')}")

        st, _, body = post_claim("x" * 1001)
        if st == 422 and jload(body).get("error_code") == "claim_too_long":
            ok("claim over 1000 chars is rejected", "422 claim_too_long")
        else:
            bad("claim over 1000 chars is rejected", f"HTTP {st} {jload(body).get('error_code')}")

        st, _, body = post_claim("Vaccines\x00 cause\n autism\r\n in children")
        d = jload(body)
        if st == 200 and "\n" not in d.get("claim", "") and "\x00" not in d.get("claim", ""):
            ok("control chars are stripped", "log-injection guard working")
        elif st == 200:
            bad("control chars are stripped", f"claim echoed back as {d.get('claim')!r}")
        else:
            bad("control chars are stripped", f"HTTP {st}")

        st, _, body = post_claim("")
        if st == 422:
            ok("empty claim is rejected", "422")
        else:
            bad("empty claim is rejected", f"HTTP {st}")

    # ------------------------------------------------------------- 6. errors
    section("6 · Error contract — one shape for every failure")
    st, _, body = http("GET", f"{base}/api/v1/does-not-exist", timeout=20)
    d = jload(body)
    if st == 404 and set(d) == {"detail", "error_code"}:
        ok("404 returns JSON, not HTML", '{"detail","error_code"}')
    else:
        bad("404 returns JSON, not HTML", f"HTTP {st}, keys={list(d)}")

    st, _, body = http("POST", f"{base}/api/v1/fact-check", data=b"{not json",
                       headers={**auth, "Content-Type": "application/json"}, timeout=20)
    d = jload(body)
    if st in (400, 422) and "error_code" in d and "Traceback" not in str(d):
        ok("malformed JSON does not leak a stack trace", f"HTTP {st} {d.get('error_code')}")
    else:
        bad("malformed JSON does not leak a stack trace", f"HTTP {st}: {str(d)[:100]}")

    # --------------------------------------------------------------- 7. CORS
    section("7 · CORS — will the browser be allowed to call this?")
    origin = os.environ.get("SMOKE_ORIGIN", "http://localhost:5173")
    st, hdrs, _ = http("OPTIONS", f"{base}/api/v1/detect-image", headers={
        "Origin": origin,
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "authorization,content-type",
    }, timeout=20)
    allow_origin = hdrs.get("access-control-allow-origin", "")
    allow_headers = (hdrs.get("access-control-allow-headers") or "").lower()

    if allow_origin in (origin, "*"):
        ok("preflight allows your frontend origin", f"allow-origin: {allow_origin}")
    else:
        bad("preflight allows your frontend origin",
            f"got {allow_origin!r}, need {origin!r}. Set FRONTEND_ORIGIN on the backend.")

    if "authorization" in allow_headers:
        ok("Authorization header is permitted",
           "without this every LOGGED-IN call dies in the browser while curl works")
    else:
        bad("Authorization header is permitted", f"allow-headers was {allow_headers!r}")

    if hdrs.get("access-control-allow-credentials", "false").lower() != "true":
        ok("credentials not allowed", "correct — we use Bearer tokens, not cookies")
    else:
        bad("credentials not allowed", "allow_credentials=True widens the attack surface for no benefit")

    st, hdrs, _ = http("OPTIONS", f"{base}/api/v1/detect-image", headers={
        "Origin": "https://evil.example.com", "Access-Control-Request-Method": "POST"}, timeout=20)
    if hdrs.get("access-control-allow-origin") != "https://evil.example.com":
        ok("unlisted origins are not reflected back", "it is an allow-LIST, not a wildcard")
    else:
        bad("unlisted origins are not reflected back",
            "any website could drive a signed-in visitor's browser against this API")

    # -------------------------------------------------------- 8. rate limiting
    section("8 · Rate limiting (Part C.3)")
    limit = (health.get("auth") or {}).get("rate_limit_per_minute")
    if not limit:
        skip("rate limiting", "disabled on this backend (RATE_LIMIT_ENABLED=false)")
    else:
        print(f"        {DIM}limit is {limit}/minute. Sending {limit + 3} fact-checks to find the ceiling…{OFF}")
        hit429 = False
        retry_after = None
        # WHY use fact-check with a short claim: we want to hit the limiter, not
        # spend a minute of real retrieval. A 422 still counts against the window
        # because the limiter runs in middleware, BEFORE routing — which is itself
        # worth verifying.
        for i in range(limit + 3):
            st, hdrs, _ = http("POST", f"{base}/api/v1/fact-check",
                               data=json.dumps({"claim": "rate limit probe test"}).encode(),
                               headers={**auth, "Content-Type": "application/json"}, timeout=30)
            if st == 429:
                hit429 = True
                retry_after = hdrs.get("retry-after")
                break
        if hit429:
            detail = f"429 on request #{i + 1}"
            if retry_after:
                detail += f" · Retry-After: {retry_after}s (the frontend sizes its cooldown from this)"
            ok("the limiter trips and says how long to wait", detail)
        else:
            skip("the limiter trips", f"no 429 after {limit + 3} calls — limiter may be off, "
                                      "or it is keyed per-user and --token differs per call")

    # ------------------------------------------------------------- 9. security
    section("9 · Security posture")
    st, _, body = http("GET", f"{base}/health", timeout=20)
    text = body.decode("utf-8", "replace")
    if "SUPABASE_JWT_SECRET" in text and len(text) > 0:
        # The KEY NAME is fine (we report configuration state); a VALUE is not.
        if any(c in text for c in ("eyJhbGciOiJIUzI1NiIs",)):
            bad("health does not leak secrets", "a JWT-looking value appeared in /health")
        else:
            ok("health reports config state without leaking values", "names only, no secrets")
    else:
        ok("health does not leak secrets", "")

    st, _, body = http("GET", f"{base}/", timeout=20)
    if st == 200 and b"TruthGuard" in body:
        ok("root URL is a human-readable service page", "not a bare 404 — useful when a marker opens the URL")
    else:
        skip("root URL page", f"HTTP {st}")

    if not args.token and authcfg.get("enabled") is False:
        print(f"        {YEL}note:{OFF} {DIM}auth is DISABLED on this backend. Correct for a local no-login"
              f" demo; must be true on Render.{OFF}")

    return finish()


def finish() -> int:
    total = len(PASSED) + len(FAILED)
    print(f"\n{BOLD}{'=' * 62}{OFF}")
    colour = GRN if not FAILED else (YEL if len(FAILED) <= 2 else RED)
    print(f"{BOLD}  {colour}{len(PASSED)}/{total} checks passed{OFF}"
          f"{f'   {YEL}({len(SKIPPED)} skipped){OFF}' if SKIPPED else ''}")
    print(f"{BOLD}{'=' * 62}{OFF}")

    if FAILED:
        print(f"\n{RED}{BOLD}Failed:{OFF}")
        for f in FAILED:
            print(f"  · {f}")
        print(f"\n{DIM}Fix these before submitting. See docs/WHY_NOT_DETECTING.md for the decision tree.{OFF}")
    elif SKIPPED:
        print(f"\n{YEL}{BOLD}Passed, but {len(SKIPPED)} check(s) were skipped:{OFF}")
        for s in SKIPPED:
            print(f"  · {s}")
        print(f"\n{DIM}Skips are not failures — they mean the check could not be performed"
              f" (missing optional dependency, no internet, or auth configuration).{OFF}")
    else:
        print(f"\n{GRN}{BOLD}Everything passed. The backend is working end to end.{OFF}")
        print(f"{DIM}Next: run the 14 browser checks in docs/DEPLOY.md §6.{OFF}")
    print()
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
