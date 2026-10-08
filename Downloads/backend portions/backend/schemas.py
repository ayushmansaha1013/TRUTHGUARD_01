"""
=============================================================================
schemas.py — the exact response contract the React frontend depends on.
=============================================================================
WHY pydantic models instead of returning plain dicts: FastAPI validates the
response against the model on the way out, so a typo or a missing key becomes a
loud error at development time rather than a blank badge in the UI at
demonstration time. It also generates the /docs schema for free.
=============================================================================
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


# -----------------------------------------------------------------------------
# POST /api/v1/detect-image
# -----------------------------------------------------------------------------
class DetectImageResponse(BaseModel):
    """
    Field names are FROZEN — `frontend/src/services/api.js` and
    `frontend/src/pages/ImageScanner.jsx` read these exact keys.
    """

    verdict: str = Field(..., description="Likely Fake | Uncertain | Likely Real")
    confidence: float = Field(..., ge=0, le=100, description="0-100, how sure the engine is")
    raw_label: str = Field(..., description="Machine label: fake | uncertain | real")
    fake_probability: float = Field(..., ge=0, le=1, description="P(fake) as a 0-1 fraction")
    is_fake: bool = Field(..., description="Convenience boolean for the red/green badge")
    analyzed_in_ms: int = Field(..., ge=0, description="Server-side processing time")

    # --- extras (additive; the frontend ignores what it doesn't know) ---
    engine: str = Field("heuristic", description="Which detector produced this verdict")
    signals: dict[str, Any] = Field(
        default_factory=dict,
        description="Per-signal breakdown — this is what makes the verdict explainable",
    )
    image: dict[str, Any] = Field(default_factory=dict, description="Format, dimensions, size")
    warnings: list[str] = Field(default_factory=list)
    # WHY a disclaimer field: the heuristic engine is forensic signal analysis,
    # not a trained deepfake classifier. Every response states so explicitly, so
    # nobody can mistake a demo verdict for a model's output.
    disclaimer: str | None = None
    mock: bool = Field(False, alias="_mock")

    model_config = {"populate_by_name": True}


# -----------------------------------------------------------------------------
# POST /api/v1/fact-check
# -----------------------------------------------------------------------------
class Source(BaseModel):
    """
    A clickable citation. The frontend renders `url` through <SafeLink>, which
    allow-lists http/https — so a non-http scheme here would be neutralised.
    """

    title: str = ""
    url: str
    snippet: str = ""
    domain: str = ""


class RetrievedContext(BaseModel):
    text: str
    score: float = Field(0.0, ge=0, le=1)
    source: str = ""


class FactCheckResponse(BaseModel):
    verdict: str = Field(
        ..., description="True | Mostly true | Mixed | Unverified | Mostly false | False"
    )
    explanation: str
    sources: list[Source] = Field(default_factory=list)
    retrieved_context: list[RetrievedContext] = Field(default_factory=list)
    checked_in_ms: int = Field(..., ge=0)

    claim: str = ""
    engine: str = "duckduckgo"
    confidence: float = Field(0.0, ge=0, le=100)
    warnings: list[str] = Field(default_factory=list)
    disclaimer: str | None = None
    mock: bool = Field(False, alias="_mock")

    model_config = {"populate_by_name": True}


# -----------------------------------------------------------------------------
# Errors — {"detail": ..., "error_code": ...} on 400/413/415/422/429/502/503/504
# -----------------------------------------------------------------------------
class ErrorResponse(BaseModel):
    """
    WHY a stable machine-readable `error_code` alongside the human `detail`:
    the frontend maps codes to friendly copy and to specific behaviour
    (a 429 starts a 10-second cooldown). Parsing English prose on the client is
    brittle — it breaks the moment someone rewords a message.
    """

    detail: str
    error_code: str


class HealthResponse(BaseModel):
    status: str
    version: str
    services: dict[str, str]
    engines: dict[str, str]
    auth: dict[str, Any]
