"""
=============================================================================
api/rate_limit.py — fixed-window rate limiter (Part C.3, server side)
=============================================================================
WHY RATE LIMIT AN AI ENDPOINT AT ALL
    These routes are expensive: image decoding plus forensic analysis, or an
    outbound search and (optionally) an LLM call. Without a limit, one client —
    malicious or merely buggy in a retry loop — can exhaust a free-tier Render
    instance's CPU for everyone, and can run up a bill on any paid provider.
    Rate limiting is therefore both an availability control and a cost control.

WHY THE SERVER CHECK IS THE ONE THAT MATTERS
    The frontend already blocks re-submission for 10 seconds after a 429. That
    check exists for UX — instant feedback without a wasted round trip. It is not
    a security control: anyone can call the API with curl and skip React
    entirely. The limit here is enforced on every request regardless of client.

WHY A FIXED WINDOW AND NOT A TOKEN BUCKET
    A token bucket is smoother, but a fixed window is ~20 lines, has no
    dependency, and is trivially explainable in a viva. Its known weakness is a
    burst of up to 2x the limit straddling a window boundary; for a demo service
    that is an acceptable trade, and it is noted here rather than hidden.

WHY IN-MEMORY IS A LIMITATION, STATED PLAINLY
    The counter lives in a dict, so it is per-process. Render's free tier runs one
    process, which makes this correct. With --workers 2 the effective limit
    doubles; with two instances it doubles again. Scale beyond one process and
    this MUST move to Redis (INCR + EXPIRE gives the same semantics in two
    commands).
=============================================================================
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from fastapi import Request
from fastapi.responses import JSONResponse

from api.errors import error_body
from config import settings

_WINDOW = 60.0  # seconds


class SlidingWindowCounter:
    """
    Per-client request timestamps inside a rolling window.

    WHY sliding rather than fixed-in-practice: we keep the actual timestamps and
    drop the expired ones, so the "boundary burst" weakness above is largely
    avoided while the code stays small. The cost is memory proportional to
    requests per client per minute — bounded and negligible here.
    """

    def __init__(self, limit: int, window: float = _WINDOW):
        self.limit = limit
        self.window = window
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str) -> tuple[bool, int]:
        """Return (allowed, retry_after_seconds)."""
        now = time.monotonic()
        with self._lock:
            bucket = self._hits[key]
            while bucket and now - bucket[0] > self.window:
                bucket.popleft()
            if len(bucket) >= self.limit:
                # WHY compute retry_after from the OLDEST hit: that is the exact
                # moment a slot frees up. Sending an honest Retry-After lets the
                # frontend size its cooldown to reality instead of guessing 10s.
                return False, max(1, int(self.window - (now - bucket[0])) + 1)
            bucket.append(now)
            return True, 0

    def prune(self) -> None:
        """
        Drop idle clients.

        WHY: `defaultdict` never forgets a key, so a long-lived process would
        accumulate one empty deque per IP it ever saw. On a free-tier instance
        with 512 MB that is a slow leak, and calling this from the request path
        (rarely) costs nothing.
        """
        now = time.monotonic()
        with self._lock:
            for key in [k for k, v in self._hits.items() if not v or now - v[-1] > self.window * 2]:
                self._hits.pop(key, None)


# One limiter for AI routes. Keyed by client identity, see _client_key().
ai_limiter = SlidingWindowCounter(limit=settings.RATE_LIMIT_PER_MINUTE)
_prune_counter = {"n": 0}


def _client_key(request: Request) -> str:
    """
    Identify the client for limiting purposes.

    WHY prefer the JWT subject when present: an IP shared by a whole college NAT
    would otherwise pool every student into one bucket, so twenty classmates
    scanning at once would trip the limit together. Keying on the authenticated
    user id gives each student their own budget, and falls back to IP for
    unauthenticated traffic.

    WHY trust X-Forwarded-For only in front of a known proxy: behind Render's
    load balancer the real client IP arrives in that header, and the socket peer
    is the proxy. But the header is trivially spoofable if the service is ever
    exposed directly, so this is a rate-limiting convenience, NOT an
    authentication mechanism — the JWT is the thing that decides identity.
    """
    state_user = getattr(request.state, "user_id", None)
    if state_user:
        return f"u:{state_user}"

    fwd = request.headers.get("x-forwarded-for", "")
    if fwd:
        return f"ip:{fwd.split(',')[0].strip()}"
    peer = request.client.host if request.client else "unknown"
    return f"ip:{peer}"


async def rate_limit_middleware(request: Request, call_next):
    """
    Applied as an HTTP middleware, but only counts the expensive AI routes.

    WHY not limit everything: /health is polled by Render's own health check and
    by uptime monitors. Rate-limiting it would cause the platform to mark a
    healthy service as dead and restart it in a loop — a self-inflicted outage.
    """
    if not settings.RATE_LIMIT_ENABLED:
        return await call_next(request)

    path = request.url.path
    is_ai_route = path.startswith(f"{settings.API_PREFIX}/detect-image") or path.startswith(
        f"{settings.API_PREFIX}/fact-check"
    )
    if not is_ai_route or request.method == "OPTIONS":
        # WHY skip OPTIONS: the CORS preflight is sent by the browser before the
        # real request. Counting it would halve every user's effective budget.
        return await call_next(request)

    _prune_counter["n"] += 1
    if _prune_counter["n"] % 200 == 0:
        ai_limiter.prune()

    allowed, retry_after = ai_limiter.check(_client_key(request))
    if not allowed:
        # WHY JSONResponse and not raise: middleware runs outside the exception
        # handlers' scope in some Starlette versions, so returning the response
        # directly is the reliable way to keep the error contract consistent.
        return JSONResponse(
            status_code=429,
            content=error_body(
                f"Too many requests. Please wait {retry_after}s before trying again.",
                "rate_limited",
            ),
            headers={"Retry-After": str(retry_after)},
        )

    response = await call_next(request)
    # Surface the budget so the frontend can show it if it wants to.
    response.headers["X-RateLimit-Limit"] = str(ai_limiter.limit)
    return response


__all__ = ["rate_limit_middleware", "ai_limiter", "SlidingWindowCounter"]
