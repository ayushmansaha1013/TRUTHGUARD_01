"""
test_asymmetric_jwks.py — proves the RS256 / JWKS verification path works, and
that the classic JWT algorithm-confusion attack is still refused on it.

WHY THIS FILE EXISTS
--------------------
Supabase projects created after 1 May 2025 sign access tokens with an RSA
asymmetric key (RS256), not the legacy HS256 shared secret. A project like that
has NO JWT secret to configure, so an HS256-only backend would reject every
valid token with a 401 — a failure that looks identical to "wrong secret" and
costs hours to diagnose.

Enabling RS256 means the verifier now reads the `alg` header of an untrusted
token to choose a verification path, which is exactly the shape of the
algorithm-confusion vulnerability. This file is the evidence that doing so is
safe here: `alg` only selects between two disjoint, explicitly allow-listed
paths, and neither can be made to verify with the other's key material.

HOW IT WORKS
------------
A real RSA key pair is generated in-process and a throwaway HTTP server serves
its public half at the same URL shape Supabase uses:

    <project-url>/auth/v1/.well-known/jwks.json

Nothing is mocked: PyJWKClient does a genuine HTTP fetch, parses a genuine JWKS
document and verifies a genuine RS256 signature.

Run it:
    cd backend_security
    pip install "pyjwt[crypto]" httpx fastapi
    python test_asymmetric_jwks.py

Expected output: all checks PASS and exit code 0.
"""

from __future__ import annotations

import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

# ---------------------------------------------------------------------------
# 1. Generate the RSA key pair BEFORE importing the app, because the app reads
#    its configuration at import time.
# ---------------------------------------------------------------------------
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

KEY_ID = "test-key-1"

_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_private_pem = _private_key.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.NoEncryption(),
)
_public_numbers = _private_key.public_key().public_numbers()


def _b64u(raw: bytes) -> str:
    import base64

    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _unb64u(text: str) -> bytes:
    import base64

    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _int_to_b64u(value: int) -> str:
    length = (value.bit_length() + 7) // 8
    return _b64u(value.to_bytes(length, "big"))


JWKS_DOCUMENT = {
    "keys": [
        {
            "kty": "RSA",
            "kid": KEY_ID,
            "use": "sig",
            "alg": "RS256",
            "n": _int_to_b64u(_public_numbers.n),
            "e": _int_to_b64u(_public_numbers.e),
        }
    ]
}


# ---------------------------------------------------------------------------
# 2. A throwaway JWKS server, so PyJWKClient fetches over real HTTP.
# ---------------------------------------------------------------------------
FETCH_COUNT = {"n": 0}


class _JWKSHandler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        if self.path.endswith("/.well-known/jwks.json"):
            FETCH_COUNT["n"] += 1
            body = json.dumps(JWKS_DOCUMENT).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *args):  # silence the test output
        pass


_server = HTTPServer(("127.0.0.1", 0), _JWKSHandler)
PORT = _server.server_address[1]
threading.Thread(target=_server.serve_forever, daemon=True).start()

PROJECT_URL = f"http://127.0.0.1:{PORT}"

# The asymmetric project has NO shared secret. Leave SUPABASE_JWT_SECRET unset
# on purpose: that is the realistic new-project configuration, and it proves the
# RS256 path does not silently depend on a secret being present.
os.environ["SUPABASE_JWT_SECRET"] = ""
os.environ["SUPABASE_PROJECT_URL"] = PROJECT_URL
os.environ.setdefault("AUTH_ENABLED", "true")

import jwt  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from integration_example import app  # noqa: E402
from jwt_auth import jwks_url  # noqa: E402

AUD = "authenticated"
ISS = f"{PROJECT_URL}/auth/v1"
NOW = int(time.time())

RESULTS: list[tuple[bool, str]] = []


def check(name: str, condition: bool, extra: str = "") -> None:
    RESULTS.append((bool(condition), name))
    print(f"[{'PASS' if condition else 'FAIL'}] {name}" + (f" -> {extra}" if extra else ""))


def claims_for(role: str = "student") -> dict:
    return {
        "iss": ISS,
        "sub": "user-uuid-123",
        "aud": AUD,
        "exp": NOW + 3600,
        "iat": NOW,
        "role": "authenticated",
        "email": f"{role}@college.edu",
        "app_metadata": {"provider": "email", "providers": ["email"], "role": role},
        "user_metadata": {"role": role},
    }


def rs256_token(role: str = "student", *, key=_private_pem, kid: str = KEY_ID, **over) -> str:
    payload = {**claims_for(role), **over}
    return jwt.encode(payload, key, algorithm="RS256", headers={"kid": kid})


client = TestClient(app)


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


print("=" * 78)
print("RS256 / JWKS VERIFICATION  (the new-Supabase-project configuration)")
print("=" * 78)
print(f"JWKS endpoint : {jwks_url()}")
print(f"SUPABASE_JWT_SECRET is empty: {os.environ['SUPABASE_JWT_SECRET']!r}\n")

# ------------------------------------------------------ 0. the JWKS is reachable
import httpx  # noqa: E402

r = httpx.get(jwks_url(), timeout=5)
check("JWKS endpoint is reachable and well-formed",
      r.status_code == 200 and "keys" in r.json(), f"HTTP {r.status_code}")

# ------------------------------------------- 1. the happy path on an RS256 token
r = client.post("/api/v1/fact-check", json={"claim": "The sky is blue today"}, headers=auth(rs256_token()))
check("Valid RS256 token -> 200 on /api/v1/fact-check", r.status_code == 200, f"got {r.status_code}")
check("Contract intact on the RS256 path",
      r.status_code == 200 and {"verdict", "explanation", "sources"} <= set(r.json()),
      f"keys={sorted(r.json().keys())[:4]}" if r.status_code == 200 else "")

r = client.get("/api/v1/analytics/summary", headers=auth(rs256_token("educator")))
check("RS256 educator token -> 200 on educator-only route", r.status_code == 200, f"got {r.status_code}")

# ----------------------------------------------------- 2. role extraction still works
r = client.get("/api/v1/analytics/summary", headers=auth(rs256_token("student")))
check("RS256 student token -> 403 on educator-only route (NOT 401)",
      r.status_code == 403, f"got {r.status_code}")

# ------------------------------------------------- 3. a DIFFERENT RSA key is rejected
attacker_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
attacker_pem = attacker_key.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.NoEncryption(),
)
r = client.post("/api/v1/fact-check", json={"claim": "forged by a stranger"},
                headers=auth(rs256_token(key=attacker_pem)))
check("RS256 token signed by the WRONG RSA key -> 401",
      r.status_code == 401, f"got {r.status_code}")
check("  ...and reports invalid_signature",
      r.status_code == 401 and r.json().get("error_code") == "invalid_signature",
      str(r.json().get("error_code")) if r.status_code == 401 else "")

# ===========================================================================
# 4. THE ALGORITHM-CONFUSION ATTACK
#
# The classic exploit: take the server's RSA PUBLIC key — which is public by
# design, it is served over HTTP — and use it as an HMAC secret to sign a
# token whose header says `alg: HS256`. A verifier that lets the token choose
# both the algorithm AND the key then verifies that signature successfully,
# because HMAC(public_key_pem, attacker_payload) is something the attacker can
# compute. It must fail here, because HS256 is only ever verified against
# SUPABASE_JWT_SECRET (which is empty in this configuration).
# ===========================================================================
public_pem = _private_key.public_key().public_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PublicFormat.SubjectPublicKeyInfo,
)
# The signature is hand-rolled rather than produced with PyJWT, because PyJWT
# refuses to use a PEM public key as an HMAC secret. That refusal is a useful
# guard-rail in OUR OWN code, but it is NOT a defence: a real attacker does not
# use a polite library. Hand-rolling is the only way to genuinely test whether
# the SERVER accepts the forged token.
import hashlib
import hmac


def hmac_sign(payload: dict, secret_material: bytes) -> str:
    head = _b64u(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    body = _b64u(json.dumps(payload).encode())
    sig = hmac.new(secret_material, f"{head}.{body}".encode(), hashlib.sha256).digest()
    return f"{head}.{body}.{_b64u(sig)}"


def hmac_verify(token: str, secret_material: bytes) -> bool:
    """A deliberately NAIVE verifier, to prove the forged token is well-formed."""
    head, body, sig = token.split(".")
    expected = _b64u(hmac.new(secret_material, f"{head}.{body}".encode(), hashlib.sha256).digest())
    return hmac.compare_digest(sig, expected)


ATTACK_PAYLOAD = {
    "sub": "attacker", "exp": NOW + 3600, "aud": AUD, "iss": ISS,
    "app_metadata": {"role": "educator"},   # also try to steal the teacher role
}

forged = hmac_sign(ATTACK_PAYLOAD, public_pem)

# CONTROL — without this the 401s below prove nothing, because a 401 is also
# what a malformed token gets. This shows the forged token is a perfectly
# well-formed JWT whose signature a naive verifier computes as valid.
check("CONTROL: forged token IS valid under a naive verifier",
      hmac_verify(forged, public_pem)
      and json.loads(_unb64u(forged.split(".")[1]))["app_metadata"]["role"] == "educator",
      "signature matches, educator claim present")

# --- Configuration A: THIS process. No SUPABASE_JWT_SECRET configured. ------
# The HS256 path cannot run at all, so the server must refuse. Either 401 (it
# is judged on the merits) or 503 (the scheme is not configured) is acceptable;
# what must NEVER happen is 200.
r = client.post("/api/v1/fact-check", json={"claim": "algorithm confusion"}, headers=auth(forged))
check("CONFUSION [secret unset]: forged HS256 token is refused (never 200)",
      r.status_code in (401, 503), f"got {r.status_code}")

r = client.get("/api/v1/analytics/summary", headers=auth(forged))
check("CONFUSION [secret unset]: cannot reach the educator dashboard",
      r.status_code in (401, 503), f"got {r.status_code}")

# --- Configuration B: a deploy where BOTH schemes are configured. -----------
# THIS is the dangerous one: a project that migrated to RS256 but still has its
# legacy secret in the environment. Now the HS256 path is live and will happily
# verify an HMAC — so the only thing standing between the attacker and a forged
# educator token is the fact that the attacker must sign with the SECRET, not
# with the public key they can read off the internet. This subprocess proves
# that the public key is not accepted as that secret.
import subprocess
import sys
import textwrap

probe = textwrap.dedent(f"""
    import os, json, time, sys
    os.environ["SUPABASE_JWT_SECRET"] = "a-real-legacy-secret-value"
    os.environ["SUPABASE_PROJECT_URL"] = {PROJECT_URL!r}
    os.environ["AUTH_ENABLED"] = "true"
    sys.path.insert(0, {os.getcwd()!r})
    from fastapi.testclient import TestClient
    from integration_example import app
    c = TestClient(app)
    forged = {forged!r}
    r = c.post("/api/v1/fact-check", json={{"claim": "x"}},
               headers={{"Authorization": "Bearer " + forged}})
    body = r.json()
    print(json.dumps({{"status": r.status_code,
                      "error_code": body.get("error_code"),
                      "detail": body.get("detail")}}))
""")
proc = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True, timeout=120)
try:
    out = json.loads(proc.stdout.strip().splitlines()[-1])
except Exception:
    out = {"status": None, "error_code": None, "detail": proc.stderr[-300:]}

check("CONFUSION [both schemes configured]: forged HS256 -> 401 invalid_signature",
      out["status"] == 401 and out["error_code"] == "invalid_signature",
      f"got {out['status']} {out['error_code']}")

# And a token legitimately signed with the configured secret must still work —
# otherwise "rejects the attack" could just mean "rejects all HS256".
def _legit_subprocess() -> dict:
    probe2 = textwrap.dedent(f"""
        import os, json, time, sys
        os.environ["SUPABASE_JWT_SECRET"] = "a-real-legacy-secret-value"
        os.environ["SUPABASE_PROJECT_URL"] = {PROJECT_URL!r}
        os.environ["AUTH_ENABLED"] = "true"
        sys.path.insert(0, {os.getcwd()!r})
        import jwt
        from fastapi.testclient import TestClient
        from integration_example import app
        tok = jwt.encode({{"sub": "real-user", "exp": int(time.time()) + 3600,
                           "aud": "authenticated", "iss": {ISS!r},
                           "app_metadata": {{"role": "student"}}}},
                         "a-real-legacy-secret-value", algorithm="HS256")
        r = TestClient(app).post("/api/v1/fact-check",
                                 json={{"claim": "a claim long enough to pass validation"}},
                                 headers={{"Authorization": "Bearer " + tok}})
        print(json.dumps({{"status": r.status_code,
                           "detail": r.json().get("detail") if r.status_code != 200 else None}}))
    """)
    pr = subprocess.run([sys.executable, "-c", probe2], capture_output=True, text=True, timeout=120)
    try:
        return json.loads(pr.stdout.strip().splitlines()[-1])
    except Exception:
        return {"status": None}


check("CONTROL: a token correctly signed with the configured secret still works",
      _legit_subprocess()["status"] == 200, "HS256 not blanket-rejected")

# --------------------------------------------------------------- 5. `alg: none`
def _alg_none() -> str:
    """Hand-build an unsigned token; PyJWT refuses to encode one."""
    head = _b64u(json.dumps({"alg": "none", "typ": "JWT"}).encode())
    body = _b64u(json.dumps({"sub": "attacker", "exp": NOW + 3600, "aud": AUD}).encode())
    return f"{head}.{body}."


r = client.post("/api/v1/fact-check", json={"claim": "no signature"}, headers=auth(_alg_none()))
check("`alg: none` token -> 401", r.status_code == 401, f"got {r.status_code}")

# ------------------------------------------------- 6. a superseded algorithm header
for bad_alg in ("HS512", "RS512", "PS256"):
    head = _b64u(json.dumps({"alg": bad_alg, "typ": "JWT", "kid": KEY_ID}).encode())
    body = _b64u(json.dumps(claims_for()).encode())
    r = client.post("/api/v1/fact-check", json={"claim": "x"}, headers=auth(f"{head}.{body}.AAAA"))
    check(f"Unlisted algorithm {bad_alg} -> 401", r.status_code == 401, f"got {r.status_code}")

# ------------------------------------------------------ 7. standard claim checks
r = client.post("/api/v1/fact-check", json={"claim": "expired"},
                headers=auth(rs256_token(exp=NOW - 7200)))
check("Expired RS256 token -> 401 token_expired",
      r.status_code == 401 and r.json().get("error_code") == "token_expired",
      str(r.json().get("error_code")))

r = client.post("/api/v1/fact-check", json={"claim": "wrong aud"},
                headers=auth(rs256_token(aud="someone-elses-app")))
check("RS256 token with a foreign audience -> 401",
      r.status_code == 401, f"got {r.status_code}")

r = client.post("/api/v1/fact-check", json={"claim": "wrong iss"},
                headers=auth(rs256_token(iss="https://evil.example.com/auth/v1")))
check("RS256 token with a foreign issuer -> 401",
      r.status_code == 401, f"got {r.status_code}")

r = client.post("/api/v1/fact-check", json={"claim": "no sub"},
                headers=auth(jwt.encode({"exp": NOW + 3600, "aud": AUD, "iss": ISS},
                                        _private_pem, algorithm="RS256")))
check("RS256 token missing `sub` -> 401", r.status_code == 401, f"got {r.status_code}")

r = client.post("/api/v1/fact-check", json={"claim": "garbage"}, headers=auth("not.a.jwt"))
check("Garbage token -> 401", r.status_code == 401, f"got {r.status_code}")

# ------------------------------------------------------- 8. unknown `kid` handling
r = client.post("/api/v1/fact-check", json={"claim": "rotated kid"},
                headers=auth(rs256_token(kid="key-that-does-not-exist")))
check("Unknown `kid` -> 401/503, never 200", r.status_code in (401, 503), f"got {r.status_code}")

# ------------------------------------------------------------ 9. public routes stay public
r = client.get("/health")
check("/health is public even in asymmetric mode", r.status_code == 200, f"got {r.status_code}")
r = client.post("/api/v1/fact-check", json={"claim": "no token at all"})
check("No Authorization header -> 401", r.status_code == 401, f"got {r.status_code}")

# ------------------------------------------------- 10. the JWKS fetch is cached
FETCH_COUNT["n"] = 0
for _ in range(5):
    client.post("/api/v1/fact-check", json={"claim": "cache probe"}, headers=auth(rs256_token()))
check("JWKS is cached across requests (no per-request network call)",
      FETCH_COUNT["n"] <= 2, f"{FETCH_COUNT['n']} fetch(es) for 5 requests")

# ------------------------------------------------------------------- summary
print("\n" + "=" * 78)
passed = sum(1 for ok, _ in RESULTS if ok)
print(f"{passed}/{len(RESULTS)} checks passed.")
if passed != len(RESULTS):
    print("\nFAILED:")
    for ok, name in RESULTS:
        if not ok:
            print(f"  - {name}")
    sys_exit = 1
else:
    print("\nRS256/JWKS verification works, and algorithm confusion is refused.")
    print("Evidence for the report: a project on Supabase's CURRENT default")
    print("signing scheme is verified without any shared secret, while the")
    print("classic confusion attack (RSA public key used as an HMAC secret)")
    print("still returns 401.")
    sys_exit = 0

_server.shutdown()
raise SystemExit(sys_exit)
