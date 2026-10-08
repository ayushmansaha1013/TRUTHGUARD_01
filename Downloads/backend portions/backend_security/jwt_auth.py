"""
=============================================================================
TruthGuard AI — FastAPI JWT verification middleware (Part C.1 / Part C.7 layer 3)
=============================================================================
Reference implementation for the AI backend teammate.

GOAL
    The existing /api/v1/detect-image and /api/v1/fact-check endpoints are
    currently auth-free. This module adds authentication + role-based access
    control WITHOUT touching any model/inference code: it is a pure FastAPI
    dependency (`Depends(...)`), so the service functions stay exactly as they
    are and simply gain one extra parameter.

WHY THIS IS THE MOST IMPORTANT SECURITY LAYER
    Layers 1 (React route guards) and 2 (Supabase RLS) both live in systems an
    attacker can bypass or talk to directly. The AI endpoints are the expensive,
    abusable resource:
      * Unauthenticated GPU inference is free compute for anyone on the internet
        (crypto-mining-style abuse, or a rival team draining your Render instance hours).
      * A public deepfake detector is a useful tool for the exact people the
        project is trying to educate against.
      * Without a JWT there is no attributable audit trail for AI usage.
    Verifying the Supabase JWT means every inference call is tied to a real,
    revocable user identity.

HOW SUPABASE JWTs WORK (the important detail)
    Supabase signs its access tokens with HS256 using the project's **JWT
    Secret** (Dashboard -> Settings -> API -> JWT Secret / "JWT Settings"). That
    secret is a SERVER-SIDE credential: it must live in the backend's
    environment, never in the frontend bundle, because anyone holding it can
    forge a token for any user (including role='educator').

    A Supabase access token's claims look like:
        {
          "iss": "https://<project-ref>.supabase.co/auth/v1",
          "sub": "<auth.users uuid>",          <- the user id == auth.uid() in RLS
          "aud": "authenticated",
          "exp": 1730000000, "iat": 1729996400,
          "role": "authenticated",             <- PostgREST role, NOT our app role
          "email": "student@college.edu",
          "app_metadata": {"provider": "email", "role": "student"},
          "user_metadata": {"role": "student"}
        }

    NOTE the trap: the top-level `role` claim is Postgres/PostgREST's
    "authenticated" role, not our student/educator role. Our application role is
    in app_metadata.role (the handle_new_user() trigger in supabase/schema.sql
    writes it there) and falls back to user_metadata.role (sent by the client at
    signUp). Prefer app_metadata, and for anything sensitive re-check the DB.

=============================================================================
INSTALL
    pip install "pyjwt[crypto]" httpx
    # cryptography is pulled in by the [crypto] extra; needed for RS256 if you
    # ever switch your Supabase project to asymmetric JWT signing keys.

ENVIRONMENT (add to backend/.env locally, or the Render service's Environment
             tab in production — never commit either)
    SUPABASE_PROJECT_URL=https://<project-ref>.supabase.co
        REQUIRED. Used for the `iss` check, and to locate the public JWKS
        endpoint for projects that sign with asymmetric keys.

    SUPABASE_JWT_SECRET=<legacy JWT secret>
        ONLY needed for projects created before May 2025, which sign tokens
        with HS256. Find it at Settings -> JWT Keys -> "Legacy JWT secret".
        A NEW Supabase project signs with RS256 and needs NO secret at all —
        verification uses the public key from
        <SUPABASE_PROJECT_URL>/auth/v1/.well-known/jwks.json

    SUPABASE_SERVICE_ROLE_KEY=<service_role key>   (optional, for DB role re-check)
    AUTH_ENABLED=true                             (kill switch for local testing)

=============================================================================
INTEGRATION — 3 small edits to the existing app
=============================================================================
1) Drop this file in as `app/security/jwt_auth.py`.

2) In each router, add the dependency. Existing handler bodies DO NOT change:

       from app.security.jwt_auth import CurrentUser, require_auth, require_role

       @router.post("/detect-image")
       async def detect_image(
           file: UploadFile = File(...),
           user: CurrentUser,                          # <-- added line
       ):
           ...  # unchanged inference logic

   ⚠ `CurrentUser` is already `Annotated[AuthUser, Depends(require_auth)]`, so
     write `user: CurrentUser` and NOT `user: CurrentUser = Depends(require_auth)`.
     Doing both makes FastAPI raise:
       AssertionError: Cannot specify `Depends` in `Annotated` and default value together
     If you prefer the explicit style instead, use a plain type:
       user: AuthUser = Depends(require_auth)

   ⚠ Python ordering rule: `CurrentUser` has NO default value, so it must be
     declared BEFORE parameters that do (e.g. `file: UploadFile = File(...)`),
     otherwise you get
       SyntaxError: parameter without a default follows parameter with a default.
     Correct:  async def detect_image(user: CurrentUser, file: UploadFile = File(...))

   Or protect a whole router in one line (cleanest, no per-endpoint edits):

       api_router = APIRouter(
           prefix="/api/v1",
           dependencies=[Depends(require_auth)],       # <-- added line
       )

3) Role-gate anything educator-only:

       @router.get("/analytics/summary")
       async def analytics(user: CurrentEducator):     # 403 for students
           ...

That's it. `require_auth` raises HTTPException(401/403) before the handler runs,
so unauthorised callers never reach the model and never burn GPU time.
=============================================================================
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Annotated, Iterable, Optional

import jwt  # PyJWT
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------
# SECURITY: read from the environment. If this string ever appears in a git diff,
# rotate the secret immediately — a leaked JWT secret = full account forgery.
SUPABASE_JWT_SECRET: str = os.getenv("SUPABASE_JWT_SECRET", "")
SUPABASE_PROJECT_URL: str = os.getenv("SUPABASE_PROJECT_URL", "").rstrip("/")
AUTH_ENABLED: bool = os.getenv("AUTH_ENABLED", "true").lower() not in ("false", "0", "no")

# -----------------------------------------------------------------------------
# Signing algorithms.
#
# WHY TWO SETS AND NOT ONE — this is the single most important configuration
# detail in this file, and getting it wrong produces a wall of 401s that looks
# exactly like a wrong secret:
#
#   * Supabase projects created BEFORE May 2025 sign access tokens with HS256,
#     a symmetric shared secret (SUPABASE_JWT_SECRET).
#   * Supabase projects created AFTER 1 May 2025 are created with an RSA
#     asymmetric key and sign with RS256 by default. There is no shared secret
#     to configure; you verify against the project's PUBLIC key, published at
#         https://<project-ref>.supabase.co/auth/v1/.well-known/jwks.json
#
# A brand-new project therefore CANNOT be verified with SUPABASE_JWT_SECRET at
# all. Supporting only HS256 means "create a Supabase project, sign up, scan" ->
# 401 on every AI call, with an error message ("invalid signature" / "algorithm
# not allowed") that points at the wrong cause.
#
# SECURITY — why reading the token's own `alg` header is still safe here:
# The classic algorithm-confusion attack works by making a verifier treat an
# HMAC secret as an RSA *public* key, so the attacker can forge signatures with
# a value they already know. It succeeds when the code allows the token to CHOOSE
# THE KEY MATERIAL. Here it does not: `alg` selects which of two disjoint,
# explicitly allow-listed verification paths to take. RS256 can only ever be
# verified against a key fetched from Supabase's own JWKS endpoint, and HS256
# only against the configured secret. An attacker cannot make an RS256 token
# verify with the secret, or an HS256 token verify with the public key. Both
# lists stay closed — `none`, HS384/512 and any unlisted algorithm are rejected.
ASYMMETRIC_ALGORITHMS = ["RS256", "ES256", "EdDSA"]   # verified via JWKS public key
SYMMETRIC_ALGORITHMS = ["HS256"]                      # verified via the shared secret
ALLOWED_ALGORITHMS = SYMMETRIC_ALGORITHMS + ASYMMETRIC_ALGORITHMS

# Supabase legacy JWTs use the project-ref audience. Newer projects issue
# "authenticated"; accept it but always require *an* audience match.
ALLOWED_AUDIENCES = ["authenticated"]

# JWKS client, created lazily.
# WHY cache: fetching the public key set on every request would add a network
# round trip to every scan and would hammer Supabase's endpoint. PyJWKClient
# caches by `kid` and only refetches when a key id it has not seen arrives —
# which is also what makes zero-downtime key rotation work.
_jwks_client = None
_jwks_client_url: Optional[str] = None


def _get_jwks_client(url: str):
    global _jwks_client, _jwks_client_url
    if _jwks_client is None or _jwks_client_url != url:
        from jwt import PyJWKClient

        _jwks_client = PyJWKClient(url, cache_keys=True, lifespan=300)
        _jwks_client_url = url
    return _jwks_client


def jwks_url() -> str:
    """Supabase's public JWKS endpoint, derived from the project URL."""
    return f"{SUPABASE_PROJECT_URL}/auth/v1/.well-known/jwks.json"

# `auto_error=False` so we can produce our own consistent error body that matches
# the project's contract: {"detail": "...", "error_code": "..."}
_bearer = HTTPBearer(auto_error=False, description="Supabase access token (JWT)")

# -----------------------------------------------------------------------------
# Error helpers — keep the existing response contract
# -----------------------------------------------------------------------------
def _unauthorized(detail: str, error_code: str) -> HTTPException:
    """401: the caller is not authenticated (missing/invalid/expired token)."""
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={
            # SECURITY: `WWW-Authenticate` is required by RFC 6750 so clients can
            # tell "you need a token" from "your token is wrong".
            "WWW-Authenticate": f'Bearer error="{error_code}"',
            # Never cache an authenticated error response in a shared proxy.
            "Cache-Control": "no-store",
        },
    )


def _forbidden(detail: str, error_code: str = "insufficient_role") -> HTTPException:
    """403: authenticated, but not allowed to perform this action."""
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=detail,
        headers={"Cache-Control": "no-store"},
    )


# SECURITY: error messages are intentionally generic. Telling an attacker
# "signature invalid" vs "expired" vs "user not found" is an oracle that helps
# them iterate. The precise reason goes to the server log, not the response.
def _log(request: Optional[Request], reason: str) -> None:
    client = request.client.host if request and request.client else "unknown"
    # In production send this to your structured logger / SIEM. This is the
    # server-side half of the audit trail (the DB half is scan_logs).
    print(f"[auth] rejected request from {client}: {reason}", flush=True)


# -----------------------------------------------------------------------------
# The authenticated principal
# -----------------------------------------------------------------------------
@dataclass(frozen=True)
class AuthUser:
    """Everything downstream handlers may safely rely on."""

    id: str                       # == auth.uid() in RLS, == auth.users.id
    email: Optional[str]
    app_role: str                 # 'student' | 'educator' (from app_metadata)
    claims: dict                  # full verified payload, for logging/debugging

    def has_role(self, *roles: str) -> bool:
        return self.app_role in roles

    def __str__(self) -> str:     # avoid leaking the token if ever printed
        return f"AuthUser(id={self.id}, role={self.app_role})"


def _extract_role(claims: dict) -> str:
    """
    Resolve the application role from verified claims.
    SECURITY: least privilege — anything unrecognised becomes 'student'.
    app_metadata is written server-side by our Postgres trigger, so it is
    preferred over user_metadata (which the client controls at signUp).
    """
    for source in ("app_metadata", "user_metadata"):
        role = (claims.get(source) or {}).get("role")
        if role in ("student", "educator"):
            return role
    return "student"


def decode_supabase_jwt(token: str) -> dict:
    """
    Verify signature + standard claims and return the payload.
    Raises HTTPException(401) on any failure, 503 if the server is misconfigured.

    Handles BOTH Supabase signing schemes:
      RS256 / ES256 / EdDSA -> verify against the project's public JWKS
      HS256                 -> verify against SUPABASE_JWT_SECRET
    """
    # -------------------------------------------------------------------------
    # 1. Read the (unsigned!) header to learn which scheme this token uses.
    # WHY this is safe: we only use `alg` to pick a verification path, never to
    # decide whether to verify. See the SECURITY note on ALLOWED_ALGORITHMS.
    # -------------------------------------------------------------------------
    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError:
        raise _unauthorized("Malformed authentication token.", "invalid_token")

    alg = str(header.get("alg", ""))

    # SECURITY: reject anything not on the allow-list before doing any work.
    # This is what stops `alg: none` and algorithm-downgrade attempts.
    if alg not in ALLOWED_ALGORITHMS:
        _log(None, f"rejected algorithm {alg!r}")
        raise _unauthorized(
            f"Token algorithm '{alg or 'unknown'}' is not accepted.",
            "invalid_algorithm",
        )

    asymmetric = alg in ASYMMETRIC_ALGORITHMS

    # -------------------------------------------------------------------------
    # 2. Fail CLOSED if the configuration this scheme needs is absent.
    # WHY split by scheme: a brand-new Supabase project uses RS256 and has no
    # shared secret to configure. Requiring SUPABASE_JWT_SECRET in that case
    # would make a correct deployment look broken. Conversely an HS256 project
    # genuinely cannot be verified without the secret.
    # -------------------------------------------------------------------------
    if asymmetric and not SUPABASE_PROJECT_URL:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Authentication is not configured: this token is signed with an "
                "asymmetric key, so SUPABASE_PROJECT_URL must be set to locate "
                "the public JWKS endpoint."
            ),
            headers={"Cache-Control": "no-store"},
        )
    if not asymmetric and not SUPABASE_JWT_SECRET:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Authentication is not configured: this token is signed with the "
                "legacy symmetric key, so SUPABASE_JWT_SECRET must be set."
            ),
            headers={"Cache-Control": "no-store"},
        )

    options = {
        "verify_signature": True,     # the whole point
        "verify_exp": True,           # reject expired tokens
        "verify_iat": True,
        "verify_aud": bool(ALLOWED_AUDIENCES),
        "require": ["exp", "sub"],    # a token without these is not ours
    }
    issuer = f"{SUPABASE_PROJECT_URL}/auth/v1" if SUPABASE_PROJECT_URL else None

    # -------------------------------------------------------------------------
    # 3. Obtain the verification key for this scheme.
    # -------------------------------------------------------------------------
    if asymmetric:
        # WHY the two failure cases are separated so carefully:
        # "we could not REACH Supabase" is an outage — the client's token may be
        # perfectly good, so 503 (try again) is honest, and telling the user
        # their session is invalid would send them re-logging-in forever while
        # the real cause stays hidden in the logs.
        # "we reached Supabase and there is no key for this token" is the
        # client's problem — a stale, forged or foreign token — so 401.
        # Collapsing both into one status code makes a routine key rotation look
        # like an outage, or an outage look like a bad password.
        from jwt import PyJWKClientConnectionError, PyJWKClientError

        try:
            signing_key = _get_jwks_client(jwks_url()).get_signing_key_from_jwt(token)
        except PyJWKClientConnectionError as exc:
            _log(None, f"JWKS unreachable: {exc.__class__.__name__}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    "Could not retrieve the public signing key from Supabase. "
                    "Check SUPABASE_PROJECT_URL and the server's outbound network."
                ),
                headers={"Cache-Control": "no-store"},
            )
        except PyJWKClientError as exc:
            # Reached Supabase, but no published key matches. One benign cause:
            # the token carries no `kid` header. Supabase always sets one, but a
            # token minted by a script may not, and refusing those would be
            # needlessly brittle — if the project publishes exactly ONE signing
            # key, there is no ambiguity about which key to use.
            kid = header.get("kid")
            if kid is None:
                try:
                    keys = _get_jwks_client(jwks_url()).get_signing_keys()
                except Exception:
                    keys = []
                if len(keys) == 1:
                    signing_key = keys[0]
                else:
                    _log(None, f"no kid and {len(keys)} published key(s)")
                    raise _unauthorized("Token is missing a key id.", "unknown_key_id")
            else:
                # SECURITY: a `kid` that is not published is never trusted and
                # never falls back to "just use the only key" — that fallback is
                # exactly how a rotated-and-revoked key keeps working.
                _log(None, f"unknown kid {kid!r}: {exc}")
                raise _unauthorized("Token was signed with an unknown key.", "unknown_key_id")
        verify_key = signing_key.key
        algorithms = [alg]           # pinned to the ONE algorithm we resolved
    else:
        verify_key = SUPABASE_JWT_SECRET
        algorithms = SYMMETRIC_ALGORITHMS

    # -------------------------------------------------------------------------
    # 4. Verify.
    # -------------------------------------------------------------------------
    try:
        claims = jwt.decode(
            token,
            verify_key,
            algorithms=algorithms,   # SECURITY: explicit allow-list, never
                                     # algorithms=["none"] and never "let the
                                     # token pick".
            audience=ALLOWED_AUDIENCES or None,
            issuer=issuer,
            leeway=10,               # small clock-skew tolerance (seconds)
            options=options,
        )
    except jwt.ExpiredSignatureError:
        raise _unauthorized("Session expired. Please sign in again.", "token_expired")
    except jwt.InvalidAudienceError:
        raise _unauthorized("Token was issued for a different service.", "invalid_audience")
    except jwt.InvalidIssuerError:
        raise _unauthorized("Token issuer is not trusted.", "invalid_issuer")
    except jwt.InvalidSignatureError:
        raise _unauthorized("Invalid token signature.", "invalid_signature")
    except jwt.PyJWTError as exc:
        # WHY log the class here: "malformed" covers several distinct causes and
        # the audit trail is the only place the real one is recorded.
        _log(None, f"token rejected by PyJWT ({alg}): {exc.__class__.__name__}")
        raise _unauthorized("Malformed authentication token.", "invalid_token")

    if claims.get("sub") is None:
        raise _unauthorized("Token is missing a subject.", "invalid_token")

    # Belt-and-braces expiry check (PyJWT already did this; cheap to repeat).
    if int(claims.get("exp", 0)) < int(time.time()) - 10:
        raise _unauthorized("Session expired. Please sign in again.", "token_expired")

    return claims


async def require_auth(
    request: Request,
    credentials: Annotated[
        Optional[HTTPAuthorizationCredentials], Depends(_bearer)
    ] = None,
) -> AuthUser:
    """
    FastAPI dependency: reject the request unless it carries a valid Supabase JWT.

    This is the drop-in addition the frontend's api.js is already sending:
        Authorization: Bearer <supabase access token>
    """
    if not AUTH_ENABLED:
        # Local-dev escape hatch. SECURITY: it is OFF unless explicitly set, and
        # must never be enabled in a deployed environment.
        return AuthUser(id="dev-local", email=None, app_role="educator", claims={})

    if credentials is None or not credentials.credentials:
        _log(request, "missing Authorization header")
        raise _unauthorized(
            "Authentication required. Sign in to TruthGuard AI to use this endpoint.",
            "missing_token",
        )

    # SECURITY: enforce the scheme. A token passed as `Basic ...` or a bare
    # string should not be silently accepted.
    if credentials.scheme.lower() != "bearer":
        _log(request, f"wrong auth scheme: {credentials.scheme}")
        raise _unauthorized("Use 'Authorization: Bearer <token>'.", "invalid_scheme")

    token = credentials.credentials.strip()
    if not token or token.count(".") != 2:  # a JWT is always header.payload.signature
        _log(request, "malformed token")
        raise _unauthorized("Malformed authentication token.", "invalid_token")

    claims = decode_supabase_jwt(token)
    user = AuthUser(
        id=str(claims["sub"]),
        email=claims.get("email"),
        app_role=_extract_role(claims),
        claims=claims,
    )

    # Attach to request state so logging middleware can record who did what
    # without threading the user through every function signature.
    request.state.user = user
    return user


def require_role(*allowed):
    """
    Dependency FACTORY for role-based access control.

        @router.get("/analytics", dependencies=[Depends(require_role("educator"))])
        async def analytics(user: AuthUser = Depends(require_role("educator", "admin"))):

    It composes on top of require_auth, so an unauthenticated caller gets 401
    and an authenticated-but-wrong-role caller gets 403 — the two cases must be
    distinguishable for good UX and correct auditing.
    """
    # Accept require_role("educator") or require_role(["educator", "admin"]).
    flat: set[str] = set()
    for item in allowed:
        if isinstance(item, str):
            flat.add(item.strip())
        elif isinstance(item, (list, tuple, set, frozenset)):
            flat.update(str(r).strip() for r in item)
    if not flat:
        raise ValueError("require_role() needs at least one role")

    async def _guard(user: AuthUser = Depends(require_auth)) -> AuthUser:
        if user.app_role not in flat:
            # SECURITY: we log the attempt (unauthorised access attempts are the
            # signal worth keeping) but the response discloses only the
            # requirement, never other users' data.
            print(
                f"[auth] RBAC denial: user={user.id} role={user.app_role} "
                f"required={sorted(flat)}",
                flush=True,
            )
            raise _forbidden(
                f"This endpoint requires one of these roles: {', '.join(sorted(flat))}.",
                "insufficient_role",
            )
        return user

    return _guard


# Convenient type aliases for handler signatures.
CurrentUser = Annotated[AuthUser, Depends(require_auth)]
CurrentEducator = Annotated[AuthUser, Depends(require_role("educator"))]


# =============================================================================
# OPTIONAL HARDENING 1 — verify the role against the DATABASE, not just the JWT
# =============================================================================
# A JWT role claim is only as fresh as the moment it was issued (up to ~1 hour).
# If you demote a user mid-session, their old token still says "educator".
# For genuinely sensitive endpoints, re-check the profiles row using the
# service_role key (server-side only!) or a short-lived direct DB connection.
#
#   import httpx
#   SUPABASE_URL = os.getenv("SUPABASE_PROJECT_URL", "")
#   SERVICE_ROLE = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")   # NEVER in frontend
#
#   async def db_role(user_id: str) -> str:
#       async with httpx.AsyncClient(timeout=5) as client:
#           r = await client.get(
#               f"{SUPABASE_URL}/rest/v1/profiles",
#               params={"id": f"eq.{user_id}", "select": "role"},
#               headers={"apikey": SERVICE_ROLE, "Authorization": f"Bearer {SERVICE_ROLE}"},
#           )
#           r.raise_for_status()
#           rows = r.json()
#       return rows[0]["role"] if rows else "student"
#
# SECURITY: the service_role key bypasses RLS entirely. Keep it in the backend
# environment only, and scope its use to this one read. If it leaks, the whole
# database is exposed.
# =============================================================================


# =============================================================================
# OPTIONAL HARDENING 2 — CORS
# =============================================================================
# The browser frontend is a different origin, so the backend needs CORS. Use an
# explicit allow-list; `allow_origins=["*"]` together with credentials is a
# common misconfiguration that lets any site call your API from a victim's
# browser.
#
#   from fastapi.middleware.cors import CORSMiddleware
#
#   app.add_middleware(
#       CORSMiddleware,
#       allow_origins=[
#           "http://localhost:5173",
#           "https://your-vercel-app.vercel.app",
#       ],
#       allow_credentials=False,          # we use Bearer tokens, not cookies
#       allow_methods=["GET", "POST", "OPTIONS"],
#       allow_headers=["Authorization", "Content-Type"],
#       max_age=600,
#   )
# =============================================================================
