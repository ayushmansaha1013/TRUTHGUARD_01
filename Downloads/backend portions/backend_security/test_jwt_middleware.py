"""
test_jwt_middleware.py — proves the Part C.1 / C.7 layer-3 controls actually work.

Run it:
    cd backend_security
    pip install -r requirements.txt
    SUPABASE_JWT_SECRET=test-secret-only-for-local-tests python test_jwt_middleware.py

Expected output: every check PASSes and the script exits 0.
Screenshot this for the report — it is your evidence that the backend rejects
unauthenticated calls and enforces the educator role.
"""

from __future__ import annotations

import io
import os
import sys
import time

# A throwaway secret for local testing ONLY. Real deploys read it from the
# Supabase Dashboard (Settings -> API -> JWT Secret) via the environment.
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-secret-only-for-local-tests")
os.environ.setdefault("AUTH_ENABLED", "true")

import jwt  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from integration_example import app  # noqa: E402
from jwt_auth import SUPABASE_JWT_SECRET, _extract_role  # noqa: E402

SECRET = SUPABASE_JWT_SECRET
AUD = "authenticated"
NOW = int(time.time())

RESULTS: list[tuple[bool, str]] = []


def make_token(role: str = "student", *, exp_offset: int = 3600, sub: str = "user-uuid-123",
               alg: str = "HS256", secret: str = SECRET, aud=AUD) -> str:
    """Forge a token that looks exactly like one Supabase issues."""
    payload = {
        "iss": "https://project-ref.supabase.co/auth/v1",
        "sub": sub,
        "aud": aud,
        "exp": NOW + exp_offset,
        "iat": NOW,
        "role": "authenticated",                 # PostgREST role, NOT the app role
        "email": f"{role}@college.edu",
        "app_metadata": {"provider": "email", "providers": ["email"], "role": role},
        "user_metadata": {"role": role},
    }
    return jwt.encode(payload, secret, algorithm=alg)


def check(name: str, condition: bool, extra: str = "") -> None:
    RESULTS.append((bool(condition), name))
    mark = "PASS" if condition else "FAIL"
    line = f"[{mark}] {name}"
    if extra:
        line += f"  -> {extra}"
    print(line)


client = TestClient(app, raise_server_exceptions=False)

print("=" * 78)
print("TruthGuard AI — backend JWT / RBAC verification")
print("=" * 78)

# ---------------------------------------------------------------- 1. no token
r = client.post("/api/v1/fact-check", json={"claim": "A claim that is definitely long enough"})
check("Unauthenticated POST /api/v1/fact-check -> 401", r.status_code == 401, f"got {r.status_code}")
check("401 body follows the {detail, error_code} contract",
      set(r.json().keys()) >= {"detail", "error_code"}, str(r.json()))
check("401 includes WWW-Authenticate: Bearer",
      "Bearer" in r.headers.get("WWW-Authenticate", ""), r.headers.get("WWW-Authenticate", ""))

# ------------------------------------------------------- 2. no token, multipart
r = client.post("/api/v1/detect-image",
                files={"file": ("test.png", io.BytesIO(b"\x89PNG\r\n\x1a\nfakedata"), "image/png")})
check("Unauthenticated POST /api/v1/detect-image -> 401", r.status_code == 401, f"got {r.status_code}")

# --------------------------------------------------------- 3. garbage token
r = client.post("/api/v1/fact-check",
                headers={"Authorization": "Bearer not.a.real.jwt"},
                json={"claim": "A claim that is definitely long enough"})
check("Garbage token -> 401 (invalid signature)", r.status_code == 401, f"got {r.status_code}")

# ------------------------------------------- 4. token signed with WRONG secret
bad = make_token("educator", secret="attacker-guessed-secret")
r = client.get("/api/v1/analytics/summary", headers={"Authorization": f"Bearer {bad}"})
check("Token signed with a different secret -> 401 (forgery rejected)",
      r.status_code == 401, f"got {r.status_code}")

# ------------------------------------------------------- 5. EXPIRED token
expired = make_token("educator", exp_offset=-120)
r = client.get("/api/v1/analytics/summary", headers={"Authorization": f"Bearer {expired}"})
check("Expired token -> 401 (token_expired)", r.status_code == 401, f"got {r.status_code}")
check("Expired token error_code == token_expired",
      r.json().get("error_code") == "token_expired", str(r.json()))

# -------------------------------------------------- 6. WRONG audience token
wrong_aud = make_token("educator", aud="some-other-app")
r = client.get("/api/v1/analytics/summary", headers={"Authorization": f"Bearer {wrong_aud}"})
check("Token with a foreign audience -> 401", r.status_code == 401, f"got {r.status_code}")

# ------------------------------------------------ 7. algorithm confusion attack
unsigned = jwt.encode({"sub": "attacker", "exp": NOW + 3600, "aud": AUD,
                       "app_metadata": {"role": "educator"}}, key="", algorithm="none")
r = client.get("/api/v1/analytics/summary", headers={"Authorization": f"Bearer {unsigned}"})
check("alg=none token -> 401 (algorithm confusion blocked)", r.status_code == 401, f"got {r.status_code}")

# ------------------------------------------------------ 8. VALID student token
student = make_token("student")
r = client.post("/api/v1/fact-check",
                headers={"Authorization": f"Bearer {student}"},
                json={"claim": "The Eiffel Tower was built in 1889 for the World Fair"})
check("Valid student token -> 200 on /api/v1/fact-check", r.status_code == 200, f"got {r.status_code}")
check("Fact-check response contract intact",
      set(r.json().keys()) >= {"verdict", "explanation", "sources", "checked_in_ms"},
      str(list(r.json().keys())))

r = client.post("/api/v1/detect-image",
                headers={"Authorization": f"Bearer {student}"},
                files={"file": ("photo.png", io.BytesIO(b"\x89PNG\r\n\x1a\n" + b"x" * 64), "image/png")})
check("Valid student token -> 200 on /api/v1/detect-image", r.status_code == 200, f"got {r.status_code}")
check("Image verdict contract intact",
      set(r.json().keys()) >= {"verdict", "confidence", "raw_label", "fake_probability",
                              "is_fake", "analyzed_in_ms"}, str(list(r.json().keys())))

# ------------------------------------- 9. STUDENT hitting an educator endpoint
r = client.get("/api/v1/analytics/summary", headers={"Authorization": f"Bearer {student}"})
check("Student on educator-only endpoint -> 403 (NOT 401)", r.status_code == 403, f"got {r.status_code}")
check("403 does not leak other users' data",
      "college.edu" not in r.text.replace("student@college.edu", ""), r.text[:120])

# --------------------------------------------- 10. EDUCATOR on same endpoint
educator = make_token("educator")
r = client.get("/api/v1/analytics/summary", headers={"Authorization": f"Bearer {educator}"})
check("Educator on educator-only endpoint -> 200", r.status_code == 200, f"got {r.status_code}")

# --------------------------------------- 11. unknown role downgrades to student
check("Unrecognised role claim downgrades to 'student' (least privilege)",
      _extract_role({"app_metadata": {"role": "superadmin"}}) == "student",
      _extract_role({"app_metadata": {"role": "superadmin"}}))
check("Missing role claim defaults to 'student'", _extract_role({}) == "student")

# ---------------------------------------------- 12. server-side validation still runs
r = client.post("/api/v1/fact-check", headers={"Authorization": f"Bearer {student}"},
                json={"claim": "short"})
check("Claim under 10 chars -> 422 even WITH a valid token", r.status_code == 422, f"got {r.status_code}")

r = client.post("/api/v1/detect-image", headers={"Authorization": f"Bearer {student}"},
                files={"file": ("evil.txt", io.BytesIO(b"hello"), "text/plain")})
check("Non-image content type -> 415 even WITH a valid token", r.status_code == 415, f"got {r.status_code}")

r = client.post("/api/v1/detect-image", headers={"Authorization": f"Bearer {student}"},
                files={"file": ("huge.png", io.BytesIO(b"\x89PNG" + b"x" * (9 * 1024 * 1024)), "image/png")})
check("Oversized image (>8MB) -> 413 even WITH a valid token", r.status_code == 413, f"got {r.status_code}")

# ------------------------------------------------------ 13. /health stays public
r = client.get("/health")
check("/health is public (no token needed) -> 200", r.status_code == 200, f"got {r.status_code}")

# --------------------------------------------------------------------- summary
print("=" * 78)
passed = sum(1 for ok, _ in RESULTS if ok)
failed = [name for ok, name in RESULTS if not ok]
print(f"{passed}/{len(RESULTS)} checks passed.")
if failed:
    print("\nFAILED:")
    for f in failed:
        print(f"  - {f}")
    sys.exit(1)
print("\nAll backend authentication + RBAC controls verified. ✅")
print("Evidence for the report: unauthenticated calls are rejected before any")
print("inference runs, forged/expired/algorithm-confused tokens are rejected,")
print("and students receive 403 on educator-only endpoints.")
