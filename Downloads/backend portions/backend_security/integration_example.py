"""
=============================================================================
integration_example.py — the EXACT diff for the existing TruthGuard AI backend
=============================================================================
This is a self-contained illustration of how `jwt_auth.py` drops into the
already-deployed FastAPI app. The teammate does NOT need to rewrite the model
code: compare the handler bodies below with the current ones — they are
identical, plus one `user` parameter (or one router-level `dependencies=[...]`).

Run this file locally to see it work end to end:
    pip install "fastapi[standard]" "pyjwt[crypto]"
    AUTH_ENABLED=false python integration_example.py     # auth off, quick smoke test
    python integration_example.py                        # auth ON -> 401 without a token

Then test with a REAL token (copy it from the browser):
    Frontend -> DevTools -> Application -> Local Storage -> truthguard-auth-token
    -> access_token

    curl -i -X POST http://127.0.0.1:8000/api/v1/fact-check \
         -H "Authorization: Bearer <access_token>" \
         -H "Content-Type: application/json" \
         -d '{"claim": "The Eiffel Tower was built in 1889 for the World Fair"}'
=============================================================================
"""

from __future__ import annotations

import time
from typing import List

from fastapi import APIRouter, Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from jwt_auth import (
    CurrentEducator,
    CurrentUser,
    require_auth,
    require_role,
)

MAX_IMAGE_BYTES = 8 * 1024 * 1024
ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}


# -----------------------------------------------------------------------------
# Response models — unchanged from the live backend contract
# -----------------------------------------------------------------------------
class ImageVerdict(BaseModel):
    verdict: str
    confidence: float
    raw_label: str
    fake_probability: float
    is_fake: bool
    analyzed_in_ms: int


class FactCheckRequest(BaseModel):
    # Server-side validation (Part C.2, layer 2). The frontend checks this too,
    # but the backend MUST check independently — client checks are bypassable.
    claim: str = Field(..., min_length=10, max_length=1000)


class FactCheckResponse(BaseModel):
    verdict: str
    explanation: str
    sources: List[str]
    retrieved_context: List[dict]
    checked_in_ms: int


# -----------------------------------------------------------------------------
# ★ THE ONLY REAL CHANGE: the router now carries a global auth dependency.
#   Every route registered on `api_router` requires a valid Supabase JWT.
#   No service/inference logic was modified.
# -----------------------------------------------------------------------------
api_router = APIRouter(
    prefix="/api/v1",
    dependencies=[Depends(require_auth)],          # <-- 1 line, protects everything
    tags=["detection"],
)


@api_router.post("/detect-image", response_model=ImageVerdict)
async def detect_image(
    user: CurrentUser,                             # <-- added (no default => must come first)
    file: UploadFile = File(...),
) -> ImageVerdict:
    started = time.perf_counter()

    # --- Server-side input validation (Part C.2, layer 2) ---
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported media type '{file.content_type}'. Allowed: jpg, png, webp.",
        )

    payload = await file.read()
    if len(payload) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="Image exceeds the 8 MB limit.",
                            headers={"Retry-After": "0"})
    if not payload:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    # SECURITY: the uploaded filename is attacker-controlled. Never use it to
    # build a filesystem path (path traversal: "../../../etc/passwd"). Pass bytes
    # to the model, or sanitise with os.path.basename + an allow-list first.
    safe_name = (file.filename or "upload").replace("/", "_").replace("\\", "_")[-100:]

    # =========================================================================
    # >>> YOUR EXISTING INFERENCE CALL GOES HERE, COMPLETELY UNCHANGED <<<
    #     e.g. label, prob = deepfake_model.predict(BytesIO(payload))
    #     Stubbed below so this file runs standalone.
    # =========================================================================
    fake_probability = 0.942
    is_fake = fake_probability >= 0.5
    verdict = "Likely Fake" if fake_probability >= 0.8 else "Uncertain" if fake_probability >= 0.4 else "Likely Real"

    elapsed_ms = int((time.perf_counter() - started) * 1000) + 1800

    # Server-side half of the AUDIT TRAIL (Part C.6). scan_logs is also written
    # by the frontend; logging here too means the record exists even if the
    # client is a script. Never log the image bytes — only metadata.
    print(f"[audit] user={user.id} email={user.email} action=detect-image "
          f"file={safe_name} bytes={len(payload)} verdict={verdict} "
          f"ms={elapsed_ms}", flush=True)

    return ImageVerdict(
        verdict=verdict,
        confidence=round(max(fake_probability, 1 - fake_probability) * 100, 1),
        raw_label="fake" if is_fake else "real",
        fake_probability=fake_probability,
        is_fake=is_fake,
        analyzed_in_ms=elapsed_ms,
    )


@api_router.post("/fact-check", response_model=FactCheckResponse)
async def fact_check(
    user: CurrentUser,                             # <-- added
    body: FactCheckRequest,
) -> FactCheckResponse:
    started = time.perf_counter()

    # SECURITY (log injection): strip control characters before the claim is
    # printed or stored. A raw "\n[fake] admin approved" inside a claim could
    # otherwise forge log lines and poison the audit trail.
    clean_claim = "".join(ch for ch in body.claim if ch.isprintable() or ch in " \n\t").strip()
    if not (10 <= len(clean_claim) <= 1000):
        raise HTTPException(status_code=422, detail="Claim must be 10–1000 characters after sanitisation.")

    # =========================================================================
    # >>> YOUR EXISTING RAG / FACT-CHECK PIPELINE GOES HERE, UNCHANGED <<<
    # =========================================================================
    elapsed_ms = int((time.perf_counter() - started) * 1000) + 2100

    print(f"[audit] user={user.id} email={user.email} action=fact-check "
          f"claim_len={len(clean_claim)} ms={elapsed_ms}", flush=True)

    return FactCheckResponse(
        verdict="True",
        explanation="(stub) Replace with your real RAG explanation.",
        sources=["https://example.org/source-1", "https://example.org/source-2"],
        retrieved_context=[{"text": "(stub) retrieved passage", "score": 0.87}],
        checked_in_ms=elapsed_ms,
    )


# -----------------------------------------------------------------------------
# Example of an EDUCATOR-ONLY endpoint (Part C.7, layer 3 RBAC).
# A student's token is valid but yields 403 — not 401.
# -----------------------------------------------------------------------------
@api_router.get("/analytics/summary")
async def analytics_summary(user: CurrentEducator) -> dict:
    return {
        "ok": True,
        "message": f"Hello educator {user.email}",
        "note": "Students receive HTTP 403 here, enforced by require_role('educator').",
    }


# -----------------------------------------------------------------------------
# App wiring
# -----------------------------------------------------------------------------
app = FastAPI(
    title="TruthGuard AI — Detection Backend",
    version="1.1.0",
    docs_url="/docs",
    redoc_url=None,          # SECURITY: fewer exposed surfaces in production
)

# SECURITY: explicit CORS allow-list. Never combine "*" with credentials.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        # add your deployed frontend origin here
    ],
    allow_credentials=False,  # we authenticate with Bearer tokens, not cookies
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
    max_age=600,
)

app.include_router(api_router)


@app.get("/health")
async def health() -> dict:
    """Public on purpose: uptime probes must not need a token."""
    return {"status": "ok", "services": {"detection": "ready", "fact_check": "ready"}}


@app.exception_handler(HTTPException)
async def http_exception_handler(_, exc: HTTPException):
    """Normalise every error to the documented {detail, error_code} contract.

    The frontend's services/api.js reads `error_code`, so keeping this shape
    consistent (including for 401/403) is what lets the UI show the right
    message — e.g. starting the 429 cooldown, or prompting a re-login on 401.
    """
    from fastapi.responses import JSONResponse

    # 401s carry the RFC 6750 code in WWW-Authenticate; reuse it if present.
    code = ""
    www = (exc.headers or {}).get("WWW-Authenticate", "")
    if 'error="' in www:
        code = www.split('error="')[-1].rstrip('"')
    if not code:
        code = _STATUS_CODES.get(exc.status_code, f"http_{exc.status_code}")

    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "error_code": code},
        headers=exc.headers,
    )


_STATUS_CODES = {
    400: "bad_request",
    401: "unauthorized",
    403: "insufficient_role",
    413: "payload_too_large",
    415: "unsupported_media_type",
    422: "validation_error",
    429: "rate_limited",
    502: "bad_gateway",
    503: "service_unavailable",
    504: "gateway_timeout",
}


if __name__ == "__main__":
    import uvicorn

    print("TruthGuard backend stub — try:")
    print("  curl -i http://127.0.0.1:8000/api/v1/fact-check "
          "-H 'Content-Type: application/json' -d '{\"claim\":\"a long enough claim\"}'")
    print("  -> expect 401 {\"detail\":\"Authentication required...\",\"error_code\":\"missing_token\"}")
    uvicorn.run(app, host="0.0.0.0", port=8000)
