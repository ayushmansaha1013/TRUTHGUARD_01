"""
=============================================================================
detection/base.py — the engine interface + the registry that selects one.
=============================================================================
WHY a strategy pattern: the project brief fixes the RESPONSE CONTRACT, not the
model behind it. Detection is the one part of this system a team is expected to
improve over time. By hiding every engine behind `detect(data, filename)` and
selecting it from an environment variable, swapping a heuristic for a trained
classifier is a config change on Render — not a refactor, and not a frontend
change. The React app never learns which engine ran, except via `engine` in the
JSON, which exists purely for the demo narration.
=============================================================================
"""

from __future__ import annotations

import abc
import time
from typing import Any


class DetectionEngine(abc.ABC):
    """Common interface for every deepfake detector in this project."""

    #: Human-readable name returned in the response's `engine` field.
    name: str = "base"

    #: True when the engine needs to download weights before first use.
    needs_download: bool = False

    @abc.abstractmethod
    def detect(self, image_bytes: bytes, filename: str) -> dict[str, Any]:
        """
        Analyse one image.

        Returns a dict with AT LEAST:
            verdict           "Likely Fake" | "Uncertain" | "Likely Real"
            confidence        0-100 float
            raw_label         "fake" | "uncertain" | "real"
            fake_probability  0-1 float
            is_fake           bool
            signals           dict of the evidence that produced the verdict
        `analyzed_in_ms` is filled in by the caller, not here.
        """
        raise NotImplementedError

    # -- shared helpers -----------------------------------------------------
    @staticmethod
    def classify(fake_probability: float) -> tuple[str, str, bool]:
        """
        Map a probability to the three-state verdict the UI's badges expect.

        WHY three states and not two: a binary real/fake verdict forces the
        system to be confidently wrong on ambiguous images. An explicit
        "Uncertain" band is the honest answer, and it is also what makes the
        yellow badge and the Hick's-Law-driven single focal gauge meaningful.
        The thresholds are deliberately wide (0.30-0.70) because a forensic
        heuristic in the middle of its range genuinely cannot tell you more.
        """
        if fake_probability >= 0.70:
            return "Likely Fake", "fake", True
        if fake_probability <= 0.30:
            return "Likely Real", "real", False
        return "Uncertain", "uncertain", False

    @staticmethod
    def confidence_from_probability(p: float) -> float:
        """
        Confidence = distance from the 50/50 boundary, expressed 0-100.

        WHY: "confidence" must answer "how sure are you?", not "how fake is
        it?". A p of 0.02 and a p of 0.98 are both *high* confidence; 0.5 is
        none at all. `50 + |p - 0.5| * 100` gives exactly that, and it means the
        ConfidenceRing always reads sensibly against the badge colour.
        """
        return round(50.0 + abs(p - 0.5) * 100.0, 1)

    @staticmethod
    def timed(fn, *args, **kwargs) -> tuple[Any, int]:
        """Run `fn` and return (result, elapsed_ms). Keeps timing out of engines."""
        started = time.perf_counter()
        out = fn(*args, **kwargs)
        return out, int((time.perf_counter() - started) * 1000)


# -----------------------------------------------------------------------------
# Registry
# -----------------------------------------------------------------------------
def get_engine(name: str) -> DetectionEngine:
    """
    Resolve an engine by name. Called once at import time in app.py.

    WHY lazy import inside the function: the transformer engine imports torch,
    which is ~2 GB and is NOT in requirements.txt. Importing it unconditionally
    would crash the default deployment. Importing only when asked keeps the
    standard install small and the failure mode explicit.
    """
    key = (name or "heuristic").strip().lower()

    if key in ("heuristic", "forensic", "default", ""):
        from .heuristic import HeuristicEngine

        return HeuristicEngine()

    if key in ("transformer", "hf", "model", "swin"):
        from .transformer_engine import TransformerEngine

        return TransformerEngine()

    if key in ("mock", "stub", "demo"):
        from .mock_engine import MockEngine

        return MockEngine()

    raise ValueError(
        f"Unknown DETECTION_ENGINE={name!r}. Expected 'heuristic', 'transformer' or 'mock'."
    )


__all__ = ["DetectionEngine", "get_engine"]
