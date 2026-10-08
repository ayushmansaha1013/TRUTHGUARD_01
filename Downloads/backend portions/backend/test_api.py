"""
=============================================================================
backend/test_api.py — contract tests for the deployed API
=============================================================================
WHY THESE EXIST
    The React app depends on exact field names, exact status codes and an exact
    error shape. Those are the things that break silently when someone renames a
    variable the night before a submission. These tests fail loudly instead.

    They run with NO network and NO Supabase:
      * detection uses the real heuristic engine on generated images
      * fact-checking uses the mock engine
      * auth is exercised by monkeypatching, not by calling Supabase

RUN
    cd backend
    pip install -r requirements-dev.txt
    pytest -q
=============================================================================
"""

from __future__ import annotations

import io
import os
import struct
import sys
import zlib
from pathlib import Path

import pytest

# Make `backend/` and the repo root (for backend_security) importable.
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

# WHY set env BEFORE importing main: config.py and backend_security/jwt_auth.py
# both read the environment at import time and cache the result. Importing first
# and configuring after would test a different service than the one deployed.
os.environ.setdefault("AUTH_ENABLED", "false")
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")
os.environ.setdefault("FACT_CHECK_ENGINE", "mock")
os.environ.setdefault("DETECTION_ENGINE", "heuristic")

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402

client = TestClient(main.app)


# -----------------------------------------------------------------------------
# Fixtures: generate real images so the forensic engine has something to chew on
# -----------------------------------------------------------------------------
def _png(width: int, height: int, alpha: bool = False, smooth: bool = True) -> bytes:
    """
    Build a valid PNG.

    WHY numpy+Pillow and not a hand-rolled byte loop: the first version of this
    helper assembled the pixel buffer one `bytes([...])` at a time. At 1024x1024
    that is ~4 million Python-level operations, and it made the whole suite take
    over ten minutes. numpy builds the same array in milliseconds. A test suite
    nobody is willing to run is worth exactly nothing, so test speed is a feature.
    """
    import numpy as np
    from PIL import Image

    ys, xs = np.mgrid[0:height, 0:width]
    if smooth:
        # Gentle gradients: a low high-frequency residual, which is what a
        # synthesised image looks like to the detector.
        r = 128 + 60 * ((xs / max(width, 1)) ** 2)
        g = 128 + 60 * ((ys / max(height, 1)) ** 2)
        b = np.full_like(r, 200.0)
    else:
        # Deterministic pseudo-noise: a broadband residual, like a sensor.
        v = (xs * 37 + ys * 91 + xs * ys) % 256
        r, g, b = v, (v + 60) % 256, (v + 130) % 256

    stack = [r, g, b] + ([np.full_like(r, 255.0)] if alpha else [])
    arr = np.clip(np.stack(stack, axis=-1), 0, 255).astype(np.uint8)

    img = Image.fromarray(arr, "RGBA" if alpha else "RGB")
    buf = io.BytesIO()
    # WHY compress_level=1: default PNG compression on a megapixel image costs
    # seconds and buys nothing — the test asserts on metadata and pixel
    # statistics, not on file size.
    img.save(buf, "PNG", compress_level=1)
    return buf.getvalue()


def _jpeg(width: int = 256, height: int = 192, exif_camera: bool = False) -> bytes:
    """A noisy JPEG; optionally carrying camera EXIF.

    WHY 256x192 by default: every forensic signal under test (block grid, noise
    residual, EXIF) needs well under 64 pixels of context. The original 640x480
    default multiplied the suite's runtime for no additional coverage.
    """
    import numpy as np
    from PIL import Image

    rng = np.random.default_rng(11)
    ys, xs = np.mgrid[0:height, 0:width]
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

    buf = io.BytesIO()
    if exif_camera:
        ex = Image.Exif()
        ex[0x010F] = "Canon"          # Make
        ex[0x0110] = "EOS 800D"       # Model
        img.save(buf, "JPEG", quality=90, exif=ex.tobytes())
    else:
        img.save(buf, "JPEG", quality=90)
    return buf.getvalue()


@pytest.fixture(scope="module")
def camera_jpeg() -> bytes:
    return _jpeg(exif_camera=True)


@pytest.fixture(scope="module")
def gan_like_png() -> bytes:
    # Smooth, square, model-native resolution, with an alpha channel: every
    # container-level signal at once.
    return _png(1024, 1024, alpha=True, smooth=True)


def _upload(data: bytes, filename: str, content_type: str):
    return client.post(
        "/api/v1/detect-image",
        files={"file": (filename, data, content_type)},
    )


# =============================================================================
# 1. The response contract — the thing the React app actually depends on
# =============================================================================
REQUIRED_DETECT_FIELDS = {
    "verdict",
    "confidence",
    "raw_label",
    "fake_probability",
    "is_fake",
    "analyzed_in_ms",
}


class TestDetectImageContract:
    def test_returns_every_field_the_frontend_reads(self, camera_jpeg):
        """
        WHY THIS IS THE MOST IMPORTANT TEST IN THE FILE: the brief fixes these six
        keys. If one disappears, ImageScanner.jsx renders an undefined badge and
        the demo visibly breaks — while the API still returns HTTP 200, so nothing
        else would catch it.
        """
        r = _upload(camera_jpeg, "photo.jpg", "image/jpeg")
        assert r.status_code == 200, r.text
        body = r.json()
        missing = REQUIRED_DETECT_FIELDS - set(body)
        assert not missing, f"response is missing contract fields: {missing}"

    def test_verdict_is_one_of_the_three_ui_states(self, camera_jpeg):
        body = _upload(camera_jpeg, "photo.jpg", "image/jpeg").json()
        assert body["verdict"] in {"Likely Fake", "Uncertain", "Likely Real"}
        assert body["raw_label"] in {"fake", "uncertain", "real"}

    def test_confidence_and_probability_are_in_range(self, camera_jpeg):
        body = _upload(camera_jpeg, "photo.jpg", "image/jpeg").json()
        assert 0.0 <= body["confidence"] <= 100.0
        assert 0.0 <= body["fake_probability"] <= 1.0
        assert isinstance(body["is_fake"], bool)
        assert body["analyzed_in_ms"] >= 0

    def test_is_fake_agrees_with_the_verdict(self, camera_jpeg):
        """WHY: the badge colour and the boolean drive different UI elements. If
        they can disagree, the card says green while the orb pulses red."""
        body = _upload(camera_jpeg, "photo.jpg", "image/jpeg").json()
        assert body["is_fake"] == (body["verdict"] == "Likely Fake")

    def test_every_response_explains_its_engine(self, camera_jpeg):
        """
        WHY: an unexplainable verdict in a misinformation tool is a liability.
        Every response must name the engine that produced it and, for the
        heuristic engine, carry a disclaimer.
        """
        body = _upload(camera_jpeg, "photo.jpg", "image/jpeg").json()
        assert body.get("engine")
        assert body.get("disclaimer"), "heuristic verdicts must be labelled as non-model"

    def test_verdict_is_deterministic(self, camera_jpeg):
        """WHY: a demo must be repeatable. Same bytes in, same verdict out."""
        a = _upload(camera_jpeg, "photo.jpg", "image/jpeg").json()
        b = _upload(camera_jpeg, "photo.jpg", "image/jpeg").json()
        assert a["verdict"] == b["verdict"]
        assert a["fake_probability"] == b["fake_probability"]


class TestDetectionDiscriminates:
    def test_camera_photo_with_exif_is_not_flagged_fake(self, camera_jpeg):
        """
        WHY: this is the false-positive test. Real photos must not be called
        fakes, or the tool is useless and actively misleading. A camera JPEG with
        EXIF provenance and broadband sensor noise is the clearest possible real
        image, so it must land below the "Likely Fake" threshold.
        """
        body = _upload(camera_jpeg, "camera_photo.jpg", "image/jpeg").json()
        assert body["is_fake"] is False, (
            f"a genuine camera JPEG was called fake (p={body['fake_probability']}); "
            f"signals={body['signals']}"
        )

    def test_generator_shaped_png_is_flagged(self, gan_like_png):
        """
        WHY: the false-negative counterpart. A smooth 1024x1024 PNG with an alpha
        channel and no metadata trips every container-level signal, and the
        detector must notice. If this passes while the previous test also passes,
        the engine is discriminating rather than always answering one way.
        """
        body = _upload(gan_like_png, "generated.png", "image/png").json()
        assert body["is_fake"] is True, f"signals={body['signals']}"

    def test_double_compressed_jpeg_shows_a_block_grid(self, camera_jpeg):
        """
        WHY: proves the JPEG re-encoding signal actually fires. Re-saving a JPEG
        at lower quality imposes a second DCT grid; detecting it is the engine's
        strongest forensic signal, and it was silently broken once already (an
        exif_transpose call wiped `img.format`), so it is pinned by a test.
        """
        from PIL import Image

        first = Image.open(io.BytesIO(camera_jpeg))
        buf = io.BytesIO()
        first.save(buf, "JPEG", quality=55)
        second = Image.open(io.BytesIO(buf.getvalue()))
        buf2 = io.BytesIO()
        second.save(buf2, "JPEG", quality=55)

        body = _upload(buf2.getvalue(), "recompressed.jpg", "image/jpeg").json()
        grid = body["signals"].get("jpeg_grid")
        assert grid is not None, "the JPEG block-grid signal did not run at all"
        assert grid["boundary_ratio"] > 1.5, (
            f"re-encoding was not detected: boundary_ratio={grid['boundary_ratio']}"
        )

    def test_format_is_reported_not_unknown(self, camera_jpeg):
        """Regression guard for the exif_transpose bug that erased img.format."""
        body = _upload(camera_jpeg, "photo.jpg", "image/jpeg").json()
        assert body["image"]["format"] == "JPEG"


# =============================================================================
# 2. Validation — the server-side half of Part C.3
# =============================================================================
class TestUploadValidation:
    def test_rejects_a_non_image_renamed_to_jpg(self):
        """
        WHY: the Content-Type header is set by the client and is therefore a lie
        the client can tell. This asserts the server checks the BYTES instead —
        the control that actually matters.
        """
        r = _upload(b"#!/bin/sh\nrm -rf /\n" + b"A" * 200, "shell.jpg", "image/jpeg")
        assert r.status_code == 415
        assert r.json()["error_code"] == "unsupported_media_type"

    def test_rejects_a_wrongly_declared_real_image(self, camera_jpeg):
        """WHY: a genuine JPEG announced as text/plain is still a mismatch, and
        accepting it would mean trusting the header we just said was untrustworthy."""
        r = _upload(camera_jpeg, "photo.jpg", "text/plain")
        assert r.status_code == 415

    def test_rejects_an_oversized_image(self):
        """
        WHY: the 8 MB ceiling is a DoS control on a free-tier instance, not a UX
        nicety. It must be enforced server-side regardless of what the browser
        promised.

        WHY the test pads a small PNG instead of generating a huge one: the size
        check runs BEFORE decoding, so the bytes after the PNG header are never
        interpreted. Building a real 8 MB image took ~13 minutes of the suite for
        no additional coverage. (And generating one at all would risk tripping
        Pillow's own decompression-bomb guard rather than testing our limit.)
        """
        small = _png(64, 64)
        oversized = small + b"\x00" * (8 * 1024 * 1024 + 1 - len(small))
        assert len(oversized) > 8 * 1024 * 1024

        r = client.post(
            "/api/v1/detect-image",
            files={"file": ("big.png", oversized, "image/png")},
        )
        assert r.status_code == 413
        assert r.json()["error_code"] == "payload_too_large"
        assert "8 MB" in r.json()["detail"]

    def test_rejects_a_missing_file_field(self):
        """WHY: the frontend must send the field named exactly `file`. A wrong
        name should produce a clear 422, not a 500 stack trace."""
        r = client.post(
            "/api/v1/detect-image",
            files={"wrong_name": ("photo.jpg", _jpeg(64, 64), "image/jpeg")},
        )
        assert r.status_code == 422
        assert r.json()["error_code"] == "validation_error"

    def test_rejects_an_empty_upload(self):
        r = _upload(b"", "empty.png", "image/png")
        assert r.status_code in (400, 415, 422)

    def test_filename_traversal_is_neutralised(self):
        """
        WHY: the filename is attacker-controlled text that lands in the audit log
        and in the response. A path separator must not survive into either.
        """
        r = _upload(_jpeg(64, 64), "../../../../etc/passwd", "image/jpeg")
        assert r.status_code in (200, 415)
        if r.status_code == 200:
            name = r.json()["image"]["filename"]
            assert "/" not in name and "\\" not in name
            assert ".." not in name


class TestFactCheckValidation:
    def _post(self, payload):
        return client.post("/api/v1/fact-check", json=payload)

    @pytest.mark.parametrize(
        "claim,expected_code",
        [
            ("short", "claim_too_short"),
            ("x" * 1001, "claim_too_long"),
        ],
    )
    def test_claim_length_bounds_match_the_frontend(self, claim, expected_code):
        """
        WHY: the brief fixes 10-1000 characters and the React validator enforces
        the same bounds client-side. If these drift apart, a user gets past the
        form and is then rejected by the server — the worst kind of bug to demo.
        """
        r = self._post({"claim": claim})
        assert r.status_code == 422
        assert r.json()["error_code"] == expected_code

    def test_missing_claim_field(self):
        r = self._post({})
        assert r.status_code == 422
        assert r.json()["error_code"] == "missing_claim"

    def test_claim_must_be_a_string(self):
        r = self._post({"claim": 12345})
        assert r.status_code == 422
        assert r.json()["error_code"] == "validation_error"

    def test_control_characters_are_stripped(self):
        """
        WHY: claims are stored in scan_logs and echoed into prompts. A newline or
        NUL would let a user forge audit-log lines. This is defence-in-depth for
        the LOGS — XSS itself is prevented at render time by React's escaping.
        """
        r = self._post({"claim": "Vaccines\x00 cause\n autism\r\n in children"})
        assert r.status_code == 200
        returned = r.json()["claim"]
        assert "\x00" not in returned
        assert "\n" not in returned and "\r" not in returned
        # WHY assert the semantic content survived: stripping must sanitise, not
        # destroy. If this ever returns an empty string the "minimum 10 characters"
        # rule would be enforced against text the user never submitted.
        assert "Vaccines" in returned and "autism" in returned

    def test_returns_every_field_the_frontend_reads(self):
        """The fact-check contract, asserted the same way as the image one."""
        r = self._post({"claim": "Vaccines cause autism in children"})
        assert r.status_code == 200, r.text
        body = r.json()
        for field in ("verdict", "explanation", "sources", "retrieved_context", "checked_in_ms"):
            assert field in body, f"missing contract field: {field}"
        assert body["checked_in_ms"] >= 0
        assert isinstance(body["sources"], list)

    def test_sources_are_http_only(self):
        """
        WHY: the frontend renders these through <SafeLink>, which allow-lists
        http/https. Filtering server-side too means a javascript: URL from a
        scraped page never reaches a client at all — two independent layers,
        either of which alone would prevent the attack.
        """
        r = self._post({"claim": "Vaccines cause autism in children"})
        for src in r.json()["sources"]:
            assert src["url"].lower().startswith(("http://", "https://")), src["url"]

    def test_mock_engine_labels_itself(self):
        """WHY: a stub verdict that looks like a real one is the single most
        misleading thing this project could produce. It must announce itself."""
        body = self._post({"claim": "Vaccines cause autism in children"}).json()
        assert body.get("_mock") is True or "mock" in body.get("engine", "")
        assert body.get("disclaimer")


# =============================================================================
# 3. Error shape — {"detail", "error_code"} on every failure
# =============================================================================
class TestErrorContract:
    def test_unknown_route_returns_json_not_html(self):
        """
        WHY: Starlette's default 404 is HTML. The frontend parses JSON and would
        show "Unexpected error" with no useful message. Every failure path must
        return the same shape as every success path.
        """
        r = client.get("/api/v1/does-not-exist")
        assert r.status_code == 404
        body = r.json()
        assert set(body) == {"detail", "error_code"}

    def test_wrong_content_type_on_fact_check(self):
        r = client.post(
            "/api/v1/fact-check",
            content=b"claim=hello+there",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert r.status_code in (415, 422)
        assert "error_code" in r.json()

    def test_malformed_json_returns_our_shape_not_a_stack_trace(self):
        r = client.post(
            "/api/v1/fact-check", content=b"{not json", headers={"Content-Type": "application/json"}
        )
        assert r.status_code in (400, 422)
        body = r.json()
        assert "detail" in body and "error_code" in body
        assert "Traceback" not in str(body)


# =============================================================================
# 4. System endpoints
# =============================================================================
class TestSystemEndpoints:
    def test_health_is_public_and_reports_configuration(self):
        """
        WHY public: Render's health check and uptime monitors must reach it with
        no credentials. WHY it reports auth state: the most common deployment
        mistake is a backend with JWT middleware facing a frontend still in demo
        mode, and this endpoint explains a wall of 401s in one look.
        """
        r = client.get("/health")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok"
        assert "auth" in body and "engines" in body
        assert "SUPABASE_JWT_SECRET" not in str(body), "health must never leak config values"

    def test_meta_advertises_the_limits_the_frontend_hardcodes(self):
        r = client.get("/api/v1/meta")
        assert r.status_code == 200
        body = r.json()
        assert body["max_image_bytes"] == 8 * 1024 * 1024
        assert body["claim_min_chars"] == 10
        assert body["claim_max_chars"] == 1000

    def test_root_page_is_human_readable(self):
        r = client.get("/")
        assert r.status_code == 200
        assert "TruthGuard" in r.text


# =============================================================================
# 5. CORS — Part C.6
# =============================================================================
class TestCors:
    def test_allowed_origin_gets_the_header(self):
        r = client.options(
            "/api/v1/detect-image",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "authorization,content-type",
            },
        )
        assert r.status_code in (200, 204)
        assert r.headers.get("access-control-allow-origin") == "http://localhost:5173"

    def test_authorization_header_is_permitted(self):
        """
        WHY this specific assertion: if `Authorization` is missing from
        allow_headers, the preflight fails and EVERY logged-in request dies in the
        browser while curl keeps working — the most confusing bug in cross-origin
        deployments, and the one most likely to bite during the demo.
        """
        r = client.options(
            "/api/v1/fact-check",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "authorization,content-type",
            },
        )
        allowed = (r.headers.get("access-control-allow-headers") or "").lower()
        assert "authorization" in allowed, f"allow-headers was: {allowed!r}"

    def test_credentials_are_not_allowed_with_a_specific_origin(self):
        """WHY: we authenticate with Bearer tokens, not cookies. Allowing
        credentials would widen the attack surface for no benefit."""
        r = client.options(
            "/api/v1/detect-image",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "POST",
            },
        )
        assert r.headers.get("access-control-allow-credentials", "false").lower() != "true"

    def test_unlisted_origin_is_not_echoed_back(self):
        """
        WHY: this is what makes it an allow-LIST rather than a wildcard. If any
        origin were reflected, any website could drive a signed-in visitor's
        browser against our API using their token.
        """
        r = client.options(
            "/api/v1/detect-image",
            headers={
                "Origin": "https://evil.example.com",
                "Access-Control-Request-Method": "POST",
            },
        )
        assert r.headers.get("access-control-allow-origin") != "https://evil.example.com"


# =============================================================================
# 6. Rate limiting — Part C.3
# =============================================================================
class TestRateLimiting:
    def test_limiter_blocks_after_the_limit_and_sends_retry_after(self):
        """
        WHY tested at unit level rather than through the app: the middleware is
        disabled for the rest of this suite (RATE_LIMIT_ENABLED=false) so the other
        tests don't trip it. This exercises the counter directly.
        """
        from api.rate_limit import SlidingWindowCounter

        limiter = SlidingWindowCounter(limit=3, window=60.0)
        results = [limiter.check("u:test")[0] for _ in range(5)]
        assert results == [True, True, True, False, False]

        allowed, retry = limiter.check("u:test")
        assert allowed is False
        assert retry >= 1, "a rejected call must tell the client how long to wait"

    def test_limit_is_per_client_not_global(self):
        """
        WHY: the limiter keys on the JWT subject when present. Without that, an
        entire college NAT would share one IP bucket and twenty students scanning
        at once would trip the limit together — the feature would look broken
        during a class demo.
        """
        from api.rate_limit import SlidingWindowCounter

        limiter = SlidingWindowCounter(limit=2, window=60.0)
        assert limiter.check("u:alice")[0] is True
        assert limiter.check("u:alice")[0] is True
        assert limiter.check("u:alice")[0] is False
        assert limiter.check("u:bob")[0] is True, "a different user must have their own budget"


# =============================================================================
# 7. Auth — Part C.1
# =============================================================================
class TestAuthentication:
    """
    WHY these tests spawn a real server instead of using dependency_overrides:
    an override replaces the dependency wholesale, so it tests the override, not
    the wiring — and (observed during development) FastAPI re-resolved the
    override function's own annotations in a scope where `Request` was not a
    string that could be evaluated, turning every POST into a spurious 422. That
    is a broken test, not a broken API: the same POST returns 200 with no
    override applied.

    What we actually need to prove is that the DEPLOYED configuration fails
    closed, which can only be tested by running the app under those conditions.
    Each test below boots a subprocess with specific env vars, asserts, and shuts
    it down. `backend_security/test_jwt_middleware.py` separately proves the token
    verification itself with 23 tests.
    """

    @staticmethod
    def _boot(port: int, env: dict, timeout: float = 25.0):
        """Start uvicorn in a subprocess and wait until /health answers."""
        import json as _json
        import subprocess
        import time
        import urllib.error
        import urllib.request

        full = dict(os.environ)
        full.update({k: str(v) for k, v in env.items()})
        proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1",
             "--port", str(port), "--log-level", "warning"],
            cwd=str(HERE), env=full,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=3) as r:
                    if r.status == 200:
                        return proc
            except (urllib.error.URLError, ConnectionError, TimeoutError):
                pass
            if proc.poll() is not None:
                raise RuntimeError(f"server on port {port} exited during boot")
            time.sleep(0.4)
        proc.terminate()
        raise RuntimeError(f"server on port {port} did not become healthy in {timeout}s")

    @staticmethod
    def _post(port: int, path: str, token: str | None = None):
        import json as _json
        import urllib.error
        import urllib.request

        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}{path}",
            data=_json.dumps({"claim": "Vaccines cause autism in children"}).encode(),
            headers=headers, method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return r.status, _json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, _json.loads(e.read())

    def test_ai_routes_require_auth_when_enabled(self):
        """The core Part C.1 assertion: no token, no detection."""
        proc = self._boot(8231, {
            "AUTH_ENABLED": "true",
            "SUPABASE_JWT_SECRET": "test-secret-for-the-contract-tests",
            "SUPABASE_PROJECT_URL": "https://example.supabase.co",
            "RATE_LIMIT_ENABLED": "false",
            "FACT_CHECK_ENGINE": "mock",
        })
        try:
            status, body = self._post(8231, "/api/v1/fact-check")
            assert status == 401, f"expected 401 without a token, got {status}: {body}"
            assert body["error_code"] == "missing_token"
            assert set(body) == {"detail", "error_code"}, "401 must use the shared error shape"
        finally:
            proc.terminate()

    def test_a_garbage_token_is_rejected(self):
        """WHY: a well-formed header containing junk must not slip through. This
        is the case a naive `if 'Authorization' in headers` check would pass."""
        proc = self._boot(8232, {
            "AUTH_ENABLED": "true",
            "SUPABASE_JWT_SECRET": "test-secret-for-the-contract-tests",
            "SUPABASE_PROJECT_URL": "https://example.supabase.co",
            "RATE_LIMIT_ENABLED": "false",
            "FACT_CHECK_ENGINE": "mock",
        })
        try:
            status, body = self._post(8232, "/api/v1/fact-check", token="not.a.real.jwt")
            assert status == 401, f"expected 401, got {status}: {body}"
            # WHY assert on observed behaviour rather than the intuitive code name:
            # backend_security/jwt_auth.py maps a malformed token to
            # `missing_token` ("Malformed authentication token."), not
            # `invalid_token`. The frontend treats every 401 identically — sign in
            # again — so the distinction is cosmetic, and a test that asserted the
            # *expected-looking* code would fail against a correct deliverable.
            assert body["error_code"] in {"missing_token", "invalid_token", "token_invalid", "invalid_scheme"}
            assert set(body) == {"detail", "error_code"}
        finally:
            proc.terminate()

    def test_fails_closed_when_the_jwt_secret_is_missing(self):
        """
        THE security test that matters most.

        WHY: if a secret is never configured, the only safe behaviour is to refuse
        every request. Silently accepting unauthenticated traffic because a
        variable was unset is how a "protected" API ends up public — and on a PaaS
        a missing env var is the single most likely misconfiguration.
        """
        proc = self._boot(8233, {
            "AUTH_ENABLED": "true",
            "SUPABASE_JWT_SECRET": "",          # deliberately absent
            "SUPABASE_PROJECT_URL": "",
            "RATE_LIMIT_ENABLED": "false",
            "FACT_CHECK_ENGINE": "mock",
        })
        try:
            status, body = self._post(8233, "/api/v1/fact-check")
            assert status in (401, 503), f"expected refusal, got {status}: {body}"
            assert status != 200, "the API served an AI call with no JWT secret configured"
        finally:
            proc.terminate()

    def test_health_meta_and_root_stay_public_under_auth(self):
        """
        WHY: if /health required a token, Render's health check would fail, the
        platform would consider the service dead, and it would restart it in a
        loop — a self-inflicted outage caused by securing one endpoint too many.
        """
        import urllib.request

        proc = self._boot(8234, {
            "AUTH_ENABLED": "true",
            "SUPABASE_JWT_SECRET": "test-secret-for-the-contract-tests",
            "SUPABASE_PROJECT_URL": "https://example.supabase.co",
            "RATE_LIMIT_ENABLED": "false",
            "FACT_CHECK_ENGINE": "mock",
        })
        try:
            for path in ("/health", "/api/v1/meta", "/"):
                with urllib.request.urlopen(f"http://127.0.0.1:8234{path}", timeout=10) as r:
                    assert r.status == 200, f"{path} should be public, got {r.status}"
        finally:
            proc.terminate()

    def test_the_ai_routes_actually_declare_the_auth_dependency(self):
        """
        WHY a static test alongside the runtime ones: this asserts the wiring
        itself, with no server and no network. If someone deletes the `user:
        CurrentUser` parameter from a route, this fails immediately, whereas the
        runtime tests would only catch it for the routes they happen to call.
        """
        from backend_security.jwt_auth import require_auth

        def _all_routes(app):
            """
            Flatten the route tree.

            WHY this needs a helper at all: since FastAPI 0.142 an included router
            is mounted as a lazy `_IncludedRouter` whose `path` is None and whose
            children are reachable only via `original_router`. Iterating
            `app.routes` and matching on `.path` therefore silently finds nothing,
            and a test written that way fails with StopIteration rather than
            telling you the protection is missing — the worst kind of test bug,
            because it looks like an application bug.
            """
            out = []
            for r in app.routes:
                if getattr(r, "path", None):
                    out.append(r)
                inner = getattr(r, "original_router", None)
                if inner is not None and hasattr(inner, "routes"):
                    out.extend(x for x in inner.routes if getattr(x, "path", None))
            return out

        def _declares_auth(route) -> bool:
            """True if require_auth appears anywhere in this route's dependency tree."""
            seen = [route.dependant.call]
            queue = list(route.dependant.dependencies)
            while queue:
                dep = queue.pop()
                seen.append(dep.call)
                queue.extend(dep.dependencies)
            return require_auth in seen

        routes = _all_routes(main.app)

        for path in ("/api/v1/detect-image", "/api/v1/fact-check"):
            route = next((r for r in routes if r.path == path), None)
            assert route is not None, f"{path} was not registered on the app at all"
            assert _declares_auth(route), f"{path} is not protected by require_auth"

        for path in ("/health", "/api/v1/meta"):
            route = next((r for r in routes if r.path == path), None)
            assert route is not None, f"{path} was not registered"
            assert not _declares_auth(route), f"{path} must stay public — Render health-checks it"


class TestEngineBehaviour:
    def test_probability_is_never_absolute(self):
        """
        WHY: no heuristic is entitled to certainty. Capping at 0.93 keeps the
        confidence gauge honest and stops one strong signal (e.g. a Midjourney tag
        on an otherwise normal photo) producing a 100% claim we cannot defend.
        """
        from services.detection.heuristic import HeuristicEngine

        eng = HeuristicEngine()
        for data, name in [
            (_png(1024, 1024, alpha=True), "generated.png"),
            (_jpeg(exif_camera=True), "camera_photo.jpg"),
        ]:
            out = eng.detect(data, name)
            assert 0.0 < out["fake_probability"] < 1.0
            assert out["confidence"] < 100.0

    def test_generator_metadata_is_detected(self):
        """WHY: an XMP fingerprint is the closest thing to direct evidence this
        engine can find, and it lives in raw bytes that Pillow does not surface —
        so it is easy to break without noticing."""
        from services.detection.heuristic import HeuristicEngine

        png = _png(300, 300, smooth=False)
        xmp = b'<x:xmpmeta>Created with Midjourney v6</x:xmpmeta>'
        marker = b"iTXtXML:com.adobe.xmp\x00\x00\x00\x00\x00" + xmp + b"\x00"
        chunk = (
            struct.pack(">I", len(marker))
            + b"iTXt"
            + marker
            + struct.pack(">I", zlib.crc32(b"iTXt" + marker) & 0xFFFFFFFF)
        )
        tagged = png[: len(png) - 12] + chunk + png[len(png) - 12 :]

        out = HeuristicEngine().detect(tagged, "art.png")
        assert "generator_marker" in out["signals"]
        assert out["is_fake"] is True

    def test_undecodable_bytes_raise_valueerror_not_a_crash(self):
        """WHY: routes translate ValueError into a clean 400. An engine that
        leaked a raw exception would produce a 500 with a stack trace."""
        from services.detection.heuristic import HeuristicEngine

        with pytest.raises(ValueError):
            HeuristicEngine().detect(b"not an image at all", "x.png")

    def test_jpeg_grid_signal_is_skipped_for_png(self):
        """
        WHY: a JPEG-specific measurement on a PNG produces a number that means
        nothing. Absence of evidence must be reported as absence, never as a
        neutral 0 that silently biases the weighted sum.
        """
        from services.detection.heuristic import HeuristicEngine

        out = HeuristicEngine().detect(_png(400, 400), "x.png")
        assert "jpeg_grid" not in out["signals"]


# =============================================================================
# 9. The fact-check scorer's judgement
# =============================================================================
class TestFactCheckScorer:
    """
    WHY these are unit tests on the scorer: they pin the behaviours that decide
    whether the product tells the truth. Each one was a real, observed failure
    during development, which is why it now has a test.
    """

    def _score(self, sources, claim="Vaccines cause autism in children"):
        from services.factcheck.base import FactCheckEngine

        return FactCheckEngine.score(claim, sources)

    def test_a_negated_quote_does_not_count_as_support(self):
        """
        THE most important correctness test in this file.

        A real CDC snippet reads:
            The claim "vaccines do not cause autism" is not an evidence-based claim
        A naive matcher counts "cause"/"autism" as SUPPORT for the myth and would
        tell a student the opposite of the truth. This asserts that quoted spans
        and explicit negation are handled.
        """
        out = self._score(
            [
                {
                    "title": "Autism and Vaccines | CDC",
                    "url": "https://www.cdc.gov/vaccine-safety/about/autism.html",
                    "snippet": 'The claim "vaccines do not cause autism" is not an '
                    "evidence-based claim because studies have not ruled out the possibility.",
                }
            ]
        )
        assert out["verdict"] in {"False", "Mostly false", "Unverified"}
        assert out["verdict"] not in {"True", "Mostly true"}
        assert out["sources"][0]["support_hits"] == 0

    def test_a_debunk_is_read_as_refutation(self):
        out = self._score(
            [
                {
                    "title": "Debunking False Vaccine Claim",
                    "url": "https://www.factcheck.org/2017/11/debunking-false-vaccine-claim/",
                    "snippet": "The myth that vaccines cause autism is false and has been "
                    "thoroughly debunked. There is no evidence supporting it.",
                }
            ]
        )
        assert out["verdict"] == "False"

    def test_genuine_supporting_evidence_scores_true(self):
        out = self._score(
            [
                {
                    "title": "Eiffel Tower",
                    "url": "https://www.britannica.com/topic/Eiffel-Tower-Paris-France",
                    "snippet": "The tower was completed in 1889 and is confirmed as the "
                    "entrance arch to the Exposition Universelle. Records show it was built "
                    "for the World's Fair and the evidence supports this.",
                }
            ],
            claim="The Eiffel Tower was built in 1889 for the World Fair",
        )
        assert out["verdict"] in {"True", "Mostly true"}

    def test_strong_causal_evidence_is_recognised(self):
        """
        WHY: a measured failure. "Smoking causes lung cancer" scored FALSE because
        authoritative sources say "a leading cause of" rather than literally
        "true". The scorer had no vocabulary for causal evidence at all.
        """
        out = self._score(
            [
                {
                    "title": "Smoking and cancer",
                    "url": "https://www.cdc.gov/tobacco/campaign/tips/diseases/cancer.html",
                    "snippet": "Smoking is a leading cause of lung cancer and a major risk "
                    "factor for death. Studies show it increases the risk of disease.",
                }
            ],
            claim="Smoking causes lung cancer",
        )
        assert out["verdict"] in {"True", "Mostly true"}

    def test_thin_evidence_does_not_produce_a_confident_verdict(self):
        """
        WHY: two snippets containing the word "not" once produced a confident
        FALSE for a claim that is actually TRUE ("bananas are berries"). Keyword
        scoring cannot fix that, so it must at least be humble about it.
        """
        out = self._score(
            [
                {"title": "A", "url": "https://example.com/a", "snippet": "possibly not"},
                {"title": "B", "url": "https://example.com/b", "snippet": "unclear"},
            ],
            claim="Bananas are a type of berry while strawberries are not",
        )
        assert out["confidence"] < 70.0
        assert "thin corroboration" in out["explanation"] or out["verdict"] == "Unverified"

    def test_no_evidence_returns_unverified_not_a_guess(self):
        out = self._score([], claim="Something entirely novel and unrecorded")
        assert out["verdict"] == "Unverified"
        assert out["confidence"] == 0.0

    def test_domain_trust_uses_longest_suffix_match(self):
        """WHY: `health.nih.gov` must inherit `nih.gov`'s rating, and `bbc.co.uk`
        must not accidentally match `co.uk`."""
        from services.factcheck.base import FactCheckEngine as F

        assert F.trust_of("https://health.nih.gov/x") >= 4
        assert F.trust_of("https://www.bbc.co.uk/news") >= 3
        assert F.trust_of("https://randomblog.example/x") == 1

    def test_explanation_cites_the_strongest_source(self):
        """WHY: the brief requires the UI to justify its verdict. A badge with no
        reasoning is not a fact-check."""
        out = self._score(
            [
                {
                    "title": "t",
                    "url": "https://www.who.int/x",
                    "snippet": "This is false and has been debunked with no evidence.",
                }
            ]
        )
        assert "who.int" in out["explanation"]


# =============================================================================
# 10. Retrieval-layer robustness (no network required)
# =============================================================================
class TestRetrievalHelpers:
    def test_openalex_inverted_abstract_is_reconstructed(self):
        """
        WHY: OpenAlex ships abstracts as {word: [positions]}. Without inverting
        it there is no text to judge, so a scholarly source would arrive as a
        citation with no evidence attached.
        """
        from services.factcheck.duckduckgo_engine import DuckDuckGoEngine as E

        inverted = {"the": [0, 3], "vaccine": [1], "is": [2], "safe": [4]}
        out = E._uninvert(inverted)
        assert out == "the vaccine is the safe"

    def test_ddg_redirect_urls_are_unwrapped(self):
        """WHY: DuckDuckGo wraps results as /l/?uddg=<encoded>. Left wrapped, the
        UI would show a redirect URL instead of the real source, and a marker
        clicking it would land on DuckDuckGo rather than the citation."""
        from services.factcheck.duckduckgo_engine import DuckDuckGoEngine as E

        wrapped = "//duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.cdc.gov%2Fvaccines&rut=abc"
        assert E._unwrap_ddg_redirect(wrapped) == "https://www.cdc.gov/vaccines"
        assert E._unwrap_ddg_redirect("https://example.com/x") == "https://example.com/x"
        assert E._unwrap_ddg_redirect("/l/invalid") == ""
        assert E._unwrap_ddg_redirect("javascript:alert(1)") == ""

    def test_irrelevant_results_are_dropped_but_never_all(self):
        """
        WHY both halves: a measured failure returned a Wikipedia article about CATS
        for a claim about garlic (noise that can flip a verdict), and the first
        version of the filter then dropped EVERY result for another claim, leaving
        the user with an empty source list. A noise filter may reduce, never
        annihilate.
        """
        from services.factcheck.duckduckgo_engine import DuckDuckGoEngine as E

        claim = "Drinking garlic water cures viral infections within two days"
        results = [
            {"title": "Common cold", "url": "https://en.wikipedia.org/wiki/Common_cold",
             "snippet": "Garlic has been proposed as a remedy for viral infections of the respiratory tract."},
            {"title": "Cat", "url": "https://en.wikipedia.org/wiki/Cat",
             "snippet": "The domestic cat is a small carnivorous mammal with retractable claws."},
        ]
        kept = E._drop_irrelevant(claim, results)
        urls = [r["url"] for r in kept]
        assert "https://en.wikipedia.org/wiki/Cat" not in urls, "irrelevant result survived"
        assert kept, "the relevance filter emptied the result set"

        # Nothing overlaps at all -> must still return something.
        unrelated = [{"title": "Zzz", "url": "https://example.com/z", "snippet": "qqq www eee"}]
        assert E._drop_irrelevant(claim, unrelated), "filter annihilated every result"

    def test_per_domain_cap_allows_distinct_reference_articles(self):
        """
        WHY: three links to the same news story is duplication and must be capped;
        three DIFFERENT encyclopaedic articles are corroboration. Capping them
        alike destroyed the evidence for a true claim.
        """
        from services.factcheck.duckduckgo_engine import DuckDuckGoEngine as E

        news = [
            {"title": f"same story {i}", "url": f"https://news.example.com/a{i}", "snippet": "x"}
            for i in range(5)
        ]
        wiki = [
            {"title": t, "url": f"https://en.wikipedia.org/wiki/{t}", "snippet": "y"}
            for t in ("Eiffel_Tower", "Exposition_Universelle", "Gustave_Eiffel", "Paris")
        ]
        assert len(E._dedupe(news)) == 2, "one outlet should not dominate the evidence"
        assert len(E._dedupe(wiki)) >= 3, "distinct reference articles must not be discarded"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
