"""
=============================================================================
config.py — every tunable lives here, read once from the environment.
=============================================================================
WHY: a deployment platform (Render) injects configuration through environment
variables, never through edited source files. Centralising them means the same
container runs locally, in CI, and in production with no code changes — only
different env values. This also keeps secrets out of the repository.
=============================================================================
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

# -----------------------------------------------------------------------------
# Load backend/.env BEFORE any os.getenv() below or in backend_security.
#
# WHY THIS IS HERE AT ALL: uvicorn does not read .env, and neither does plain
# os.getenv(). Without these four lines the documented workflow
# (`cp .env.example .env`, edit, run) silently does nothing — every value falls
# back to its default and the developer debugs the wrong thing.
#
# WHY override=False: a deployment platform (Render) injects configuration
# through real environment variables. Those MUST win over anything in a file, or
# a stale .env committed by accident would override production secrets. Local
# files win only when the platform has not spoken.
#
# WHY search the parent directory too: this module is imported both when the CWD
# is `backend/` and when it is the repo root (the test suite does the latter).
# -----------------------------------------------------------------------------
try:
    from dotenv import load_dotenv

    for _candidate in (Path(__file__).resolve().parent / ".env",
                       Path(__file__).resolve().parent.parent / ".env"):
        if _candidate.is_file():
            load_dotenv(_candidate, override=False)
            break
except ImportError:
    # python-dotenv is a convenience, not a dependency the service cannot run
    # without: on Render every value comes from the dashboard anyway.
    pass


def _flag(name: str, default: bool = False) -> bool:
    """Parse a boolean env var the way humans actually write them."""
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def _csv(name: str, default: str) -> list[str]:
    """Comma-separated env var -> trimmed, non-empty list."""
    return [p.strip() for p in os.getenv(name, default).split(",") if p.strip()]


class Settings:
    # --- Service identity ---------------------------------------------------
    APP_NAME: str = "TruthGuard AI Backend"
    VERSION: str = "1.0.0"
    API_PREFIX: str = "/api/v1"

    # --- Upload limits (mirrors the frontend's client-side validation) ------
    # WHY 8 MB: the project brief. Enforcing it on BOTH sides matters — the
    # browser check is for UX (instant feedback, no wasted upload), the server
    # check is the security control (a request can be crafted to skip the UI).
    MAX_IMAGE_BYTES: int = 8 * 1024 * 1024
    ALLOWED_CONTENT_TYPES: set[str] = {"image/jpeg", "image/png", "image/webp"}
    ALLOWED_EXTENSIONS: set[str] = {".jpg", ".jpeg", ".png", ".webp"}
    # WHY also cap pixel count: a 500x500 8 MB PNG can decode to gigabytes of
    # RAM ("decompression bomb"). Pillow has a built-in guard, but we set an
    # explicit ceiling so a free-tier Render instance cannot be OOM-killed by
    # one hostile upload.
    MAX_PIXELS: int = 64_000_000  # 64 megapixels

    # --- Claim limits -------------------------------------------------------
    CLAIM_MIN_CHARS: int = 10
    CLAIM_MAX_CHARS: int = 1000

    # --- Engine selection (swap without touching code) ----------------------
    # "heuristic"   -> image-forensics signals, no model download, works free
    # "transformer" -> a real deepfake classifier from Hugging Face (optional)
    DETECTION_ENGINE: str = os.getenv("DETECTION_ENGINE", "heuristic").lower()
    TRANSFORMER_MODEL: str = os.getenv(
        "TRANSFORMER_MODEL", "swinv2/Detect-fake-images-cifarSwinV2"
    )

    # "duckduckgo" -> free web search, no API key
    # "mock"       -> offline canned results (demo / no internet)
    # "llm"        -> Groq or OpenRouter, needs an API key
    FACT_CHECK_ENGINE: str = os.getenv("FACT_CHECK_ENGINE", "duckduckgo").lower()
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    GROQ_MODEL: str = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    GROQ_URL: str = os.getenv(
        "GROQ_URL", "https://api.groq.com/openai/v1/chat/completions"
    )
    FACT_CHECK_MAX_SOURCES: int = 6
    FACT_CHECK_TIMEOUT: float = float(os.getenv("FACT_CHECK_TIMEOUT", "12"))

    # --- CORS (Part C.6) ----------------------------------------------------
    # WHY not "*": a wildcard is acceptable for a truly public read-only API,
    # but ours accepts authenticated uploads and is graded on security. An
    # explicit allow-list means a malicious site cannot make a logged-in
    # visitor's browser call our endpoints using their session.
    # On Render: set FRONTEND_ORIGIN=https://your-app.vercel.app
    CORS_ALLOW_ORIGINS: list[str] = _csv(
        "FRONTEND_ORIGIN",
        "http://localhost:5173,http://127.0.0.1:5173,http://localhost:4173,"
        "http://127.0.0.1:4173",
    )
    # WHY allow_credentials=False: we authenticate with Bearer tokens in a
    # header, not cookies. Browsers reject `allow_origins=["*"]` together with
    # `allow_credentials=True`, and we don't need credentials at all.
    CORS_ALLOW_CREDENTIALS: bool = False

    # --- Auth (Part C.1) ----------------------------------------------------
    # WHY default True (fail CLOSED): if the JWT secret is missing, refusing
    # every request is safe; silently accepting unauthenticated traffic is not.
    # For a no-auth demo you must explicitly opt out with AUTH_ENABLED=false.
    AUTH_ENABLED: bool = _flag("AUTH_ENABLED", True)
    SUPABASE_JWT_SECRET: str = os.getenv("SUPABASE_JWT_SECRET", "")
    SUPABASE_PROJECT_URL: str = os.getenv("SUPABASE_PROJECT_URL", "").rstrip("/")

    # --- Rate limiting ------------------------------------------------------
    RATE_LIMIT_ENABLED: bool = _flag("RATE_LIMIT_ENABLED", True)
    RATE_LIMIT_PER_MINUTE: int = int(os.getenv("RATE_LIMIT_PER_MINUTE", "20"))
    # WHY an in-memory limiter: Render's free tier is a single process, so a
    # dict is sufficient and adds no dependency. With multiple workers or a
    # second instance you MUST move this to Redis — the counter would otherwise
    # be per-process and the effective limit would multiply.
    # NOTE: Render's free web services also sleep when idle, so a real
    # deployment should rely on an edge limiter too.

    # --- Misc ---------------------------------------------------------------
    DEMO_MODE: bool = _flag("DEMO_MODE", False)  # returns a "_mock": true flag
    LOG_JSON: bool = _flag("LOG_JSON", False)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached so repeated imports don't re-read the environment."""
    return Settings()


settings = get_settings()
