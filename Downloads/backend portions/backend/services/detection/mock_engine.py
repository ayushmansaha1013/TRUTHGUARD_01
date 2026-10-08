"""
=============================================================================
detection/mock_engine.py — deterministic stub (DETECTION_ENGINE=mock)
=============================================================================
WHY: lets you rehearse the demo with no internet and no image-processing risk.
The verdict is derived from the filename and a hash of the bytes, so it is
REPEATABLE — the same file always gives the same answer, which is what you want
when presenting to an examiner.

    screenshot_deepfake.png  -> Likely Fake   (red badge, orb pulses)
    family_photo_real.jpg    -> Likely Real   (green badge)
    anything else            -> Uncertain     (yellow badge)

Every response carries "_mock": true and a disclaimer. Never present these
verdicts as detection.
=============================================================================
"""

from __future__ import annotations

import hashlib
from typing import Any

from .base import DetectionEngine

FAKE_KEYS = ("deepfake", "fake", "generated", "aigen", "ai-gen", "synthetic", "gan", "deep-fake")
REAL_KEYS = ("real", "authentic", "original", "family", "photo", "selfie", "camera", "raw")


class MockEngine(DetectionEngine):
    name = "mock-stub"
    needs_download = False

    DISCLAIMER = (
        "MOCK ENGINE: no analysis was performed. The verdict is a deterministic "
        "stub derived from the filename and a hash of the bytes. It must not be "
        "presented as deepfake detection."
    )

    def detect(self, image_bytes: bytes, filename: str = "") -> dict[str, Any]:
        name = (filename or "").lower()
        digest = int(hashlib.sha256(image_bytes).hexdigest(), 16)

        if any(k in name for k in FAKE_KEYS):
            p = 0.88 + (digest % 100) / 1000.0
        elif any(k in name for k in REAL_KEYS):
            p = 0.04 + (digest % 80) / 1000.0
        else:
            p = 0.35 + (digest % 300) / 1000.0   # stays inside the Uncertain band

        p = float(max(0.001, min(0.999, p)))
        verdict, raw_label, is_fake = self.classify(p)

        return {
            "verdict": verdict,
            "confidence": self.confidence_from_probability(p),
            "raw_label": raw_label,
            "fake_probability": round(p, 3),
            "is_fake": is_fake,
            "engine": self.name,
            "disclaimer": self.DISCLAIMER,
            "signals": {
                "filename": filename,
                "sha256_prefix": hashlib.sha256(image_bytes).hexdigest()[:16],
                "note": "stub verdict — no image analysis performed",
            },
            "warnings": ["Mock engine: no detection was performed."],
        }


__all__ = ["MockEngine"]
