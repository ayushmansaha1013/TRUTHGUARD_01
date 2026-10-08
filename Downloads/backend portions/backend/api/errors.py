"""
=============================================================================
api/errors.py — one error shape for every failure mode.
=============================================================================
WHY: the project brief requires errors to arrive as {"detail", "error_code"}
with specific status codes, and the React app switches behaviour on `error_code`
(a 429 starts a 10-second cooldown; a 503 shows "service unavailable"). FastAPI
produces several *different* error shapes by default — RequestValidationError
gives a list of dicts, HTTPException gives a bare string, Starlette's own errors
give HTML. Left alone, the frontend would have to handle four formats and would
silently show "Unexpected error" for three of them. These handlers normalise all
of them into the one documented contract.
=============================================================================
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from config import settings


class ApiError(Exception):
    """
    Application-level error carrying a status code AND a stable machine code.

    WHY a custom exception instead of raising HTTPException directly: HTTPException
    only carries a string detail, so the stable `error_code` the frontend keys on
    would have to be smuggled inside prose or a dict — which breaks FastAPI's own
    docs and makes the contract implicit. This class makes both fields first-class.
    """

    def __init__(self, status_code: int, detail: str, error_code: str):
        self.status_code = status_code
        self.detail = detail
        self.error_code = error_code
        super().__init__(detail)


# Map HTTP status -> default error_code, so a handler can omit the code and still
# produce a predictable one.
STATUS_CODES: dict[int, str] = {
    400: "bad_request",
    401: "missing_token",
    403: "insufficient_role",
    404: "not_found",
    413: "payload_too_large",
    415: "unsupported_media_type",
    422: "validation_error",
    429: "rate_limited",
    500: "internal_error",
    502: "bad_gateway",
    503: "service_unavailable",
    504: "gateway_timeout",
}


def error_body(detail: str, error_code: str) -> dict:
    return {"detail": detail, "error_code": error_code}


def _safe_detail(exc: Exception) -> str:
    """
    WHY never echo an exception message straight to the client: tracebacks and
    driver errors leak paths, library versions, table names and sometimes
    credentials. In production we return a generic message and log the real one
    server-side, where the audit trail belongs.
    """
    return str(exc)[:300] if settings.DEMO_MODE else "Internal server error."


def register_error_handlers(app: FastAPI) -> None:
    """Attach the normalising handlers. Called once from app.py."""

    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError):
        return JSONResponse(
            status_code=exc.status_code,
            content=error_body(exc.detail, exc.error_code),
            # WHY Retry-After on 429 specifically: it is the standard (RFC 6585)
            # way to tell a client when to come back, and our frontend uses it to
            # size the cooldown instead of hard-coding a guess.
            headers={"Retry-After": "10"} if exc.status_code == 429 else None,
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException):
        detail = exc.detail
        # A dict detail means the raiser already built our shape — pass it through.
        if isinstance(detail, dict) and "error_code" in detail:
            return JSONResponse(status_code=exc.status_code, content=detail)
        code = STATUS_CODES.get(exc.status_code, "http_error")
        return JSONResponse(
            status_code=exc.status_code,
            content=error_body(str(detail), code),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError):
        """
        Flatten pydantic's verbose error list into ONE readable sentence plus a
        machine code.

        WHY flatten: pydantic returns
        [{"type":"string_too_short","loc":["body","claim"],"msg":"...","input":"hi"}]
        which would be rendered raw into a UI banner. Note we keep `loc` — it
        names the offending field, which is the one part genuinely useful to a
        developer — but we drop `input`, because echoing the user's own submitted
        value back into an error response is a reflected-content risk for no gain.
        """
        errors = exc.errors()
        first = errors[0] if errors else {}
        loc = ".".join(str(p) for p in first.get("loc", ()) if p != "body") or "request"
        msg = first.get("msg", "Invalid request")
        detail = f"{loc}: {msg}" + (f" (+{len(errors) - 1} more)" if len(errors) > 1 else "")
        return JSONResponse(
            status_code=422,
            content=error_body(detail, "validation_error"),
        )

    @app.exception_handler(ValueError)
    async def _value_error(_: Request, exc: ValueError):
        # Engines raise ValueError for "this input isn't a decodable image".
        return JSONResponse(
            status_code=400,
            content=error_body(str(exc)[:300], "bad_request"),
        )

    @app.exception_handler(RuntimeError)
    async def _runtime_error(_: Request, exc: RuntimeError):
        # Engines raise RuntimeError for "the model could not be loaded" — that is
        # a service problem, not the client's fault, so 503 is the honest code.
        return JSONResponse(
            status_code=503,
            content=error_body(str(exc)[:300], "service_unavailable"),
        )

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception):
        # WHY log-and-generic: the audit trail (Part C.5) must record what
        # actually happened, while the client must not receive it.
        print(f"[error] unhandled {exc.__class__.__name__}: {exc}", flush=True)
        return JSONResponse(
            status_code=500,
            content=error_body(_safe_detail(exc), "internal_error"),
        )


__all__ = ["ApiError", "register_error_handlers", "STATUS_CODES", "error_body"]
