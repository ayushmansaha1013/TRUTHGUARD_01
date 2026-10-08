"""
=============================================================================
main.py — TruthGuard AI Backend (FastAPI)
=============================================================================
Endpoints (the exact contract frontend/src/services/api.js depends on):

    GET  /health                  PUBLIC — uptime probe, no auth, no rate limit
    POST /api/v1/detect-image     multipart, field name "file", jpg/png/webp, <=8 MB
    POST /api/v1/fact-check       JSON {"claim": "..."} 10-1000 chars
    GET  /api/v1/meta             PUBLIC — advertises limits so the UI can match them

Run locally:
    cd backend && uvicorn main:app --reload --port 8000

Run on Render (see render.yaml):
    uvicorn main:app --host 0.0.0.0 --port $PORT --workers 1

DEPLOYMENT NOTES THAT MATTER
  * Render injects $PORT (often 10000). Never hard-code a port on a PaaS.
  * AUTH_ENABLED defaults to TRUE and fails CLOSED: without SUPABASE_JWT_SECRET
    every AI call returns 503, not "open access". To demo without auth you must
    explicitly set AUTH_ENABLED=false.
  * FRONTEND_ORIGIN must be set to your deployed frontend URL or the browser
    will block every call with a CORS error.
=============================================================================
"""

from __future__ import annotations

import io
import os
import sys
import time
from pathlib import Path
from typing import Optional

# -----------------------------------------------------------------------------
# Make `backend_security/` importable.
# WHY: Part C.1 (the JWT middleware) lives in its own folder because the project
# brief asks for it as a standalone, paste-able deliverable with its own tests.
# Duplicating it into backend/ would create two copies to keep in sync, and the
# second one always rots. One source of truth, imported by path.
# -----------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from fastapi import Depends, FastAPI, File, Request, UploadFile, status  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import HTMLResponse, JSONResponse  # noqa: E402

from api.errors import ApiError, error_body, register_error_handlers  # noqa: E402
from api.rate_limit import rate_limit_middleware  # noqa: E402
from config import settings  # noqa: E402
from schemas import (  # noqa: E402
    DetectImageResponse,
    ErrorResponse,
    FactCheckResponse,
    HealthResponse,
    RetrievedContext,
    Source,
)
from services.detection.base import get_engine as get_detection_engine  # noqa: E402
from services.factcheck.base import get_engine as get_factcheck_engine  # noqa: E402

# Part C.1 — the deliverable JWT dependency, imported rather than re-written.
from backend_security.jwt_auth import AUTH_ENABLED, CurrentUser  # noqa: E402

# -----------------------------------------------------------------------------
# Engine singletons.
# WHY resolve once at import: model loading and search-client setup are slow.
# Doing it per request would add seconds to every call. They are stateless after
# construction, so sharing one instance across requests is safe.
# -----------------------------------------------------------------------------
try:
    detection_engine = get_detection_engine(settings.DETECTION_ENGINE)
except Exception as exc:  # a bad env value must not produce a stack trace at boot
    print(f"[startup] DETECTION_ENGINE={settings.DETECTION_ENGINE!r} failed: {exc}", flush=True)
    print("[startup] falling back to 'heuristic'", flush=True)
    detection_engine = get_detection_engine("heuristic")

try:
    factcheck_engine = get_factcheck_engine(settings.FACT_CHECK_ENGINE)
except Exception as exc:
    print(f"[startup] FACT_CHECK_ENGINE={settings.FACT_CHECK_ENGINE!r} failed: {exc}", flush=True)
    print("[startup] falling back to 'mock'", flush=True)
    factcheck_engine = get_factcheck_engine("mock")

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.VERSION,
    description=(
        "Deepfake image detection and claim fact-checking for civic education "
        "(UN SDG 4 & 16). Protected by Supabase JWT Bearer auth."
    ),
    # WHY a custom docs URL: /docs is the first thing an attacker fingerprints.
    # Keeping it available is fine for a college project, but knowing it is
    # configurable is the point.
    docs_url="/docs",
    redoc_url=None,
)

register_error_handlers(app)

# -----------------------------------------------------------------------------
# CORS (Part C.6)
# WHY an allow-list and not "*": these endpoints accept authenticated uploads on
# a user's behalf. A wildcard would let any website make a signed-in visitor's
# browser call our API using their session token. The allow-list is driven by
# FRONTEND_ORIGIN so production and local dev differ only by env value.
# -----------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ALLOW_ORIGINS,
    allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
    allow_methods=["GET", "POST", "OPTIONS"],
    # WHY Authorization explicitly: the browser preflights custom headers. If
    # Authorization is missing from allow_headers, the preflight fails and every
    # logged-in request dies in the browser — while curl keeps working, which
    # makes this the single most confusing bug in cross-origin deployments.
    allow_headers=["Authorization", "Content-Type", "X-Requested-With"],
    expose_headers=["X-RateLimit-Limit", "Retry-After"],
    max_age=600,
)

app.middleware("http")(rate_limit_middleware)


# =============================================================================
# Audit trail (Part C.5)
# =============================================================================
@app.middleware("http")
async def audit_log(request: Request, call_next):
    """
    Log every AI call: who, what, how long, what came back.

    WHY: an audit trail is the only way to answer "who ran this detection and
    when?" after the fact — which for a misinformation tool aimed at educators is
    a genuine requirement, not decoration. We log the STATUS CODE and the SIZE,
    never the image bytes and never the full claim text.

    WHY not the claim text: claims arrive from students and may contain personal
    or sensitive material. Logging them server-side would create a second, less
    protected copy of user content — the durable record already lives in
    Supabase's `scan_logs` table under RLS, where the user owns it.
    """
    if not request.url.path.startswith(settings.API_PREFIX):
        return await call_next(request)

    started = time.perf_counter()
    user = getattr(request.state, "user", None)
    # WHY getattr with a default: `require_auth` populates request.state.user, but
    # middleware ordering means it may not have run yet for a rejected request.
    who = getattr(user, "id", None) or (
        "anonymous" if not AUTH_ENABLED else "unauthenticated"
    )

    try:
        response = await call_next(request)
    except Exception:
        elapsed = int((time.perf_counter() - started) * 1000)
        # WHY log failures too: an attempted call that errored is still an event
        # worth recording — a spike of 401s is an attack signature.
        print(
            f"[audit] {request.method} {request.url.path} user={who} "
            f"status=500 elapsed_ms={elapsed} outcome=exception",
            flush=True,
        )
        raise

    elapsed = int((time.perf_counter() - started) * 1000)
    print(
        f"[audit] {request.method} {request.url.path} user={who} "
        f"role={getattr(user, 'app_role', '-')} status={response.status_code} "
        f"elapsed_ms={elapsed} engine={detection_engine.name if 'detect' in request.url.path else factcheck_engine.name}",
        flush=True,
    )
    return response


# =============================================================================
# Input validation helpers
# =============================================================================
# WHY magic bytes and not the Content-Type header: the header is set by the
# client and is therefore attacker-controlled. A shell script renamed to
# "photo.jpg" arrives with Content-Type: image/jpeg and passes a header-only
# check. Sniffing the first bytes verifies what the file actually IS.
_MAGIC = (
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
)


def _sniff_image_type(data: bytes) -> Optional[str]:
    """Return the true image type from magic bytes, or None."""
    for prefix, mime in _MAGIC:
        if data.startswith(prefix):
            return mime
    # WebP is a RIFF container: "RIFF" .... "WEBP"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def _validate_upload(file: UploadFile, data: bytes) -> None:
    """
    Enforce type, size and decodability BEFORE any analysis runs.

    WHY this order: each check is cheaper than the next, and the most likely
    mistake (wrong file type) should produce the fastest, clearest error. Size is
    checked before decoding because decoding is where a hostile file can cost us
    CPU and memory.
    """
    filename = (file.filename or "").strip()

    # 1. Declared content type
    declared = (file.content_type or "").split(";")[0].strip().lower()
    if declared and declared not in settings.ALLOWED_CONTENT_TYPES:
        raise ApiError(
            415,
            f"Unsupported media type '{declared}'. Allowed: JPG, PNG, WebP.",
            "unsupported_media_type",
        )

    # 2. Extension — WHY check this separately from the MIME type: browsers
    #    sometimes send application/octet-stream for a valid .jpg. If the declared
    #    type is generic we fall back to the extension rather than rejecting a
    #    legitimate photo. Rejecting only when BOTH disagree is the user-friendly
    #    and still-safe rule, because the magic-byte check below is the real gate.
    ext = os.path.splitext(filename)[1].lower()
    if declared in ("", "application/octet-stream") and ext not in settings.ALLOWED_EXTENSIONS:
        raise ApiError(
            415,
            f"Could not determine image type from '{filename or 'upload'}'. Allowed: JPG, PNG, WebP.",
            "unsupported_media_type",
        )

    # 3. Empty body
    if not data:
        raise ApiError(400, "Uploaded file is empty.", "empty_file")

    # 4. Size ceiling — the real control (Part C.3)
    if len(data) > settings.MAX_IMAGE_BYTES:
        raise ApiError(
            413,
            f"Image is {len(data) / 1048576:.1f} MB; the limit is 8 MB. "
            "Please upload a smaller file.",
            "payload_too_large",
        )

    # 5. Magic bytes — the check that cannot be spoofed by a header
    actual = _sniff_image_type(data)
    if actual is None:
        raise ApiError(
            415,
            "File does not contain a recognisable JPG, PNG or WebP image. "
            "The declared type cannot be trusted, so the file's own bytes were checked.",
            "unsupported_media_type",
        )
    if actual in ("image/gif",):
        raise ApiError(415, "GIF images are not supported. Allowed: JPG, PNG, WebP.",
                       "unsupported_media_type")
    if declared and declared != actual:
        # WHY 415 and not a silent accept: a mismatch means either a confused
        # user or a deliberate probe. Refusing is the safe default and the error
        # message tells a legitimate user exactly how to fix it (re-save the file).
        raise ApiError(
            415,
            f"Content-Type says '{declared}' but the file's bytes are '{actual}'. "
            "Re-save the image and try again.",
            "unsupported_media_type",
        )

    # 6. Decode + pixel bomb guard
    try:
        from PIL import Image

        Image.MAX_IMAGE_PIXELS = settings.MAX_PIXELS
        with Image.open(io.BytesIO(data)) as probe:
            probe.verify()  # checksum-level validation without loading pixels
    except Exception:
        raise ApiError(
            400,
            "The image appears to be corrupt or truncated and could not be decoded.",
            "undecodable_image",
        )


def _sanitize_filename(name: str) -> str:
    """
    Reduce a client-supplied filename to something safe to log.

    WHY: the filename is attacker-controlled text that ends up in our audit log
    and in the response. Stripping path separators defeats traversal attempts
    ("../../etc/passwd" as a filename) and stripping control characters defeats
    log injection — a newline in a filename would let an attacker forge whole
    audit lines.
    """
    import re

    base = os.path.basename(name or "upload")
    base = re.sub(r"[\x00-\x1f\x7f]", "", base)          # control chars
    base = re.sub(r"[^\w.\-()+ ]", "_", base)             # path/punctuation noise
    return base[:120] or "upload"


def _strip_control_chars(text: str) -> str:
    """
    Remove ASCII control characters — INCLUDING newline and carriage return —
    from a claim, then collapse runs of whitespace.

    WHY newlines too: a claim is stored in `scan_logs.input_summary` (a single
    text column) and echoed into the server audit log and into search queries. A
    newline in that field would let a user forge whole audit-log lines
    ("user=educator status=200" typed as claim text), and would corrupt any
    CSV/TSV export of the audit trail. Collapsing whitespace also keeps the
    stored summary tidy.

    Note this is defence-in-depth for the DATABASE and LOGS. XSS itself is
    prevented at render time by React's escaping plus the SafeLink allow-list in
    the frontend — two independent layers, neither of which relies on this.

    WHY it is safe to alter the user's text here: a fact-check claim is prose.
    Nobody legitimately needs a carriage return inside one, and the 10-character
    minimum is applied AFTER stripping so padding with control characters cannot
    be used to sneak an empty claim past validation.
    """
    import re

    text = re.sub(r"[\x00-\x1f\x7f]", " ", text)   # all C0 controls + DEL
    return re.sub(r"\s+", " ", text)


# =============================================================================
# Routes
# =============================================================================
@app.get("/health", response_model=HealthResponse, tags=["system"])
async def health() -> HealthResponse:
    """
    Liveness probe.

    WHY public and unauthenticated: Render's health check, uptime monitors and
    your own `tools/check_backend.py` all need to answer "is it up?" without
    credentials. It exposes version and engine names only — no secrets, no user
    data, no stack traces.

    WHY it reports auth configuration: the most common deployment mistake is
    enabling the backend's JWT middleware while the frontend is still in demo
    mode. Seeing `auth.enabled: true` here explains a wall of 401s instantly.
    """
    return HealthResponse(
        status="ok",
        version=settings.VERSION,
        services={
            "detection": "ready",
            "fact_check": "ready",
        },
        engines={
            "detection": detection_engine.name,
            "detection_needs_download": str(getattr(detection_engine, "needs_download", False)),
            "fact_check": factcheck_engine.name,
        },
        auth={
            "enabled": AUTH_ENABLED,
            "jwt_secret_configured": bool(settings.SUPABASE_JWT_SECRET),
            "supabase_project_configured": bool(settings.SUPABASE_PROJECT_URL),
            "rate_limit_per_minute": settings.RATE_LIMIT_PER_MINUTE
            if settings.RATE_LIMIT_ENABLED
            else None,
        },
    )


@app.get("/api/v1/meta", tags=["system"])
async def meta() -> JSONResponse:
    """
    Advertise the server's limits.

    WHY this endpoint exists: the frontend hard-codes 8 MB and 10-1000 chars for
    instant client-side feedback. If someone changes the server limit, the two
    silently disagree and users get confusing rejections. Exposing the real
    numbers lets the UI read them, and lets you verify the deployed config with
    one curl.
    """
    return JSONResponse(
        {
            "max_image_bytes": settings.MAX_IMAGE_BYTES,
            "allowed_content_types": sorted(settings.ALLOWED_CONTENT_TYPES),
            "claim_min_chars": settings.CLAIM_MIN_CHARS,
            "claim_max_chars": settings.CLAIM_MAX_CHARS,
            "detection_engine": detection_engine.name,
            "fact_check_engine": factcheck_engine.name,
            "rate_limit_per_minute": settings.RATE_LIMIT_PER_MINUTE,
            "version": settings.VERSION,
        }
    )


# WHY `dependencies=[Depends(require_auth)]` at router level rather than a
# `user` parameter on each function: it is impossible to forget. A new route
# added to this router is protected by default, which is the safe direction for a
# mistake to fail in.
from fastapi import APIRouter  # noqa: E402

api_router = APIRouter(prefix=settings.API_PREFIX, tags=["ai"])


@api_router.post(
    "/detect-image",
    response_model=DetectImageResponse,
    responses={413: {"model": ErrorResponse}, 415: {"model": ErrorResponse}, 429: {"model": ErrorResponse}},
    summary="Detect whether an image is a deepfake",
)
async def detect_image(
    request: Request,
    user: CurrentUser,
    file: UploadFile = File(..., description="JPG, PNG or WebP, max 8 MB"),
) -> DetectImageResponse:
    """
    The multipart field MUST be named `file` — that is what the React
    FileDropzone appends and what this signature expects.
    """
    data = await file.read()
    safe_name = _sanitize_filename(file.filename or "")
    _validate_upload(file, data)

    # WHY time the engine separately from validation: `analyzed_in_ms` is shown
    # in the UI as the model's speed. Including upload parsing and validation
    # would misreport it, and those numbers are what you quote in the report.
    started = time.perf_counter()
    try:
        result = detection_engine.detect(data, safe_name)
    except ValueError:
        raise  # handled -> 400 undecodable
    except RuntimeError:
        raise  # handled -> 503 model unavailable
    except Exception as exc:
        print(f"[detect] engine error: {exc.__class__.__name__}: {exc}", flush=True)
        raise ApiError(502, "Detection failed unexpectedly. Please try again.", "detection_failed")
    analyzed_ms = int((time.perf_counter() - started) * 1000)

    return DetectImageResponse(
        verdict=result["verdict"],
        confidence=result["confidence"],
        raw_label=result["raw_label"],
        fake_probability=result["fake_probability"],
        is_fake=result["is_fake"],
        analyzed_in_ms=analyzed_ms,
        engine=result.get("engine", detection_engine.name),
        signals=result.get("signals", {}),
        image=result.get("image", {}),
        warnings=result.get("warnings", []),
        disclaimer=result.get("disclaimer"),
        **({"_mock": True} if settings.DEMO_MODE or detection_engine.name.startswith("mock") else {}),
    )


@api_router.post(
    "/fact-check",
    response_model=FactCheckResponse,
    responses={422: {"model": ErrorResponse}, 429: {"model": ErrorResponse}, 502: {"model": ErrorResponse}},
    summary="Check a textual claim against retrieved sources",
)
async def fact_check(request: Request, user: CurrentUser, payload: dict) -> FactCheckResponse:
    """
    WHY accept a plain dict and validate by hand rather than a pydantic body
    model: pydantic's automatic 422 would report `body.claim: Field required`
    before we can produce our own friendlier message, and we need the 10/1000
    character bounds reported in the exact wording the frontend's validation
    tests assert on. The manual check keeps the contract identical on both sides.
    """
    if not isinstance(payload, dict):
        raise ApiError(400, "Request body must be a JSON object.", "invalid_json")

    claim = payload.get("claim")
    if claim is None:
        raise ApiError(422, "Missing required field 'claim'.", "missing_claim")
    if not isinstance(claim, str):
        raise ApiError(422, "Field 'claim' must be a string.", "validation_error")

    # WHY strip before measuring: otherwise a claim of 3 real characters padded
    # with 10 newlines would pass the 10-character minimum and then arrive at the
    # engine as 3 characters — the bound would be enforced against text the user
    # never actually submitted.
    claim = _strip_control_chars(claim).strip()

    if len(claim) < settings.CLAIM_MIN_CHARS:
        raise ApiError(
            422,
            f"Claim is too short ({len(claim)} characters). Minimum is "
            f"{settings.CLAIM_MIN_CHARS} so there is enough to verify.",
            "claim_too_short",
        )
    if len(claim) > settings.CLAIM_MAX_CHARS:
        raise ApiError(
            422,
            f"Claim is too long ({len(claim)} characters). Maximum is "
            f"{settings.CLAIM_MAX_CHARS}. Please submit one testable statement.",
            "claim_too_long",
        )

    started = time.perf_counter()
    try:
        retrieved = factcheck_engine.retrieve(claim)
    except Exception as exc:
        # WHY 502 and not 500: the failure is in an UPSTREAM dependency (a search
        # provider or an LLM API), not in our code. The distinction tells the user
        # "try again shortly" instead of "the app is broken".
        print(f"[factcheck] retrieval error: {exc.__class__.__name__}: {exc}", flush=True)
        raise ApiError(
            502,
            "Could not reach the fact-check sources. Please try again in a moment.",
            "retrieval_failed",
        )
    checked_ms = int((time.perf_counter() - started) * 1000)

    # The LLM and mock engines may supply their own verdict/explanation; the
    # DuckDuckGo engine returns raw results for the shared scorer to judge.
    warnings = list(retrieved.get("warnings", []))
    if "verdict_override" in retrieved:
        verdict = retrieved["verdict_override"]
        explanation = retrieved.get("explanation_override", "")
        confidence = float(retrieved.get("confidence_override", 0.0) or 0.0)
        rows = retrieved.get("results", [])
    else:
        judged = factcheck_engine.score(claim, retrieved.get("results", []))
        verdict = judged["verdict"]
        explanation = judged["explanation"]
        confidence = judged["confidence"]
        rows = judged["sources"]
        contexts = judged["retrieved_context"]
        return _build_fact_response(
            claim, verdict, explanation, confidence, rows, contexts, checked_ms, warnings, retrieved
        )

    contexts = [
        {
            "text": (r.get("snippet") or r.get("title") or "")[:300],
            "score": float(r.get("score", 0.5)),
            "source": r.get("url", ""),
        }
        for r in rows[:4]
    ]
    return _build_fact_response(
        claim, verdict, explanation, confidence, rows, contexts, checked_ms, warnings, retrieved
    )


def _build_fact_response(claim, verdict, explanation, confidence, rows, contexts, checked_ms, warnings, retrieved):
    """
    Assemble the response, filtering sources down to safe http(s) URLs.

    WHY filter here as well as in the frontend: the frontend's <SafeLink>
    allow-lists http/https, which protects rendering. Filtering server-side too
    means a `javascript:` URL from a scraped page never even reaches a client, so
    the audit log and any future consumer are also clean. Two independent layers,
    either of which alone would prevent the attack.
    """
    from services.factcheck.base import FactCheckEngine

    sources = []
    for r in rows[: settings.FACT_CHECK_MAX_SOURCES]:
        url = str(r.get("url", "")).strip()
        if not url.lower().startswith(("http://", "https://")):
            continue
        sources.append(
            Source(
                title=str(r.get("title", ""))[:200] or FactCheckEngine.domain_of(url),
                url=url[:2000],
                snippet=str(r.get("snippet", ""))[:400],
                domain=r.get("domain") or FactCheckEngine.domain_of(url),
            )
        )

    return FactCheckResponse(
        verdict=verdict,
        explanation=explanation,
        sources=sources,
        retrieved_context=[
            RetrievedContext(
                text=str(c.get("text", ""))[:400],
                score=float(c.get("score", 0.0) or 0.0),
                source=str(c.get("source", ""))[:500],
            )
            for c in contexts[:4]
        ],
        checked_in_ms=checked_ms,
        claim=claim[:200],
        engine=retrieved.get("provider") or factcheck_engine.name,
        confidence=confidence,
        warnings=warnings,
        disclaimer=getattr(factcheck_engine, "DISCLAIMER", None),
        **({"_mock": True} if settings.DEMO_MODE or "mock" in factcheck_engine.name else {}),
    )


app.include_router(api_router)


# -----------------------------------------------------------------------------
# Root page.
# WHY a human-readable root instead of a bare {"detail":"Not Found"}: someone
# opening your Render URL in a browser during marking should immediately learn
# what the service is, that it is healthy, and where the docs are. It also makes
# a 404-on-root diagnosis unambiguous.
# -----------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def root() -> HTMLResponse:
    return HTMLResponse(
        f"""<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{settings.APP_NAME} — API</title>
<style>
 body{{background:#0A192F;color:#E6F1FF;font:16px/1.65 -apple-system,Segoe UI,Roboto,sans-serif;
      margin:0;padding:3rem 1.5rem;display:flex;justify-content:center}}
 main{{max-width:44rem;width:100%}}
 h1{{font-size:1.9rem;margin:0 0 .2rem;color:#64FFDA}}
 code{{background:#112240;color:#64FFDA;padding:.15rem .45rem;border-radius:6px;font-size:.9rem}}
 table{{border-collapse:collapse;width:100%;margin:1.2rem 0}}
 td,th{{text-align:left;padding:.55rem .7rem;border-bottom:1px solid #1d3557;font-size:.92rem}}
 th{{color:#8892B0;font-weight:600;text-transform:uppercase;font-size:.72rem;letter-spacing:.08em}}
 .ok{{color:#64FFDA}} .warn{{color:#FFD166}}
 a{{color:#64FFDA}}
 .note{{background:#112240;border-left:3px solid #64FFDA;padding:.9rem 1.1rem;border-radius:8px;
        color:#8892B0;font-size:.9rem;margin-top:1.4rem}}
</style><main>
 <h1>TruthGuard AI · Backend API</h1>
 <p style="color:#8892B0;margin-top:0">Deepfake detection &amp; claim fact-checking ·
    v{settings.VERSION} · <span class="ok">running</span></p>
 <table>
   <tr><th>Endpoint</th><th>Method</th><th>Auth</th></tr>
   <tr><td><code>/health</code></td><td>GET</td><td class="ok">public</td></tr>
   <tr><td><code>/api/v1/meta</code></td><td>GET</td><td class="ok">public</td></tr>
   <tr><td><code>/api/v1/detect-image</code></td><td>POST</td><td class="warn">Bearer JWT</td></tr>
   <tr><td><code>/api/v1/fact-check</code></td><td>POST</td><td class="warn">Bearer JWT</td></tr>
 </table>
 <p>Interactive docs: <a href="/docs">/docs</a></p>
 <p>Detection engine <code>{detection_engine.name}</code> ·
    Fact-check engine <code>{factcheck_engine.name}</code> ·
    Auth <code>{'enabled' if AUTH_ENABLED else 'DISABLED'}</code></p>
 <div class="note">This service is the API half of the project. The React interface is deployed
 separately — set <code>FRONTEND_ORIGIN</code> on this service to its URL or the browser will
 block cross-origin calls.</div>
</main></html>"""
    )


# -----------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn

    # WHY read $PORT: Render (and Heroku, Fly, Railway) inject the port they want
    # the process to bind. Hard-coding 8000 makes the service boot successfully
    # and then fail its health check forever, which reads as a mystery crash.
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(
        "main:app",
        host="0.0.0.0",   # WHY 0.0.0.0: binding 127.0.0.1 inside a container
                          # makes it unreachable from outside, so the platform
                          # sees nothing listening and kills the deploy.
        port=port,
        workers=1,        # WHY 1: the in-memory rate limiter is per-process. See
                          # api/rate_limit.py before raising this.
        reload=False,
    )
