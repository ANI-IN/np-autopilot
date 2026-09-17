"""G1 — the login flow end to end, and the seam that had never been joined.

`tests/test_auth_google.py` proves layer 2 refuses twelve kinds of bad Google
token. This file proves the parts BETWEEN the layers, which is where the actual
defect was:

    profiles.user_id is uuid
    np_role() resolves through auth.uid()
    auth.uid() casts request.jwt.claims->>'sub' to uuid
    a Google subject is a decimal string, e.g. 117609876543210987654

So a Google token presented on a data route made every policy evaluation raise
`invalid input syntax for type uuid` — a 500 on every authenticated request.
Each layer was green in isolation. Nothing exercised the join.

Everything here is offline: locally generated keys, a locally served JWKS, and
an injected opener in place of GoTrue. An auth test that needs the internet is
an auth test that gets skipped, and a skipped auth test is worse than none.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
import sys
import time
import uuid
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "web"))

jwt = pytest.importorskip("jwt", reason="PyJWT not installed")
pytest.importorskip("cryptography")

from lib import gotrue                                              # noqa: E402
from lib.auth import (AuthError, reset_jwks_cache,                  # noqa: E402
                      reset_supabase_jwks_cache, verify_google_token,
                      verify_supabase_token)

AUD = "np-autopilot-test.apps.googleusercontent.com"
ISS = "https://accounts.google.com"
KID = "test-key-1"
SB_SECRET = "a-test-only-hs256-secret-that-is-long-enough-to-be-plausible"


@pytest.fixture(scope="module")
def signing():
    from cryptography.hazmat.primitives.asymmetric import rsa
    from jwt.utils import base64url_encode
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pub = key.public_key().public_numbers()

    def b64u_int(v: int) -> str:
        raw = v.to_bytes((v.bit_length() + 7) // 8, "big")
        return base64url_encode(raw).decode()

    jwks = {"keys": [{"kty": "RSA", "kid": KID, "alg": "RS256", "use": "sig",
                      "n": b64u_int(pub.n), "e": b64u_int(pub.e)}]}

    def make(**overrides) -> str:
        now = int(time.time())
        claims = {"iss": ISS, "aud": AUD, "sub": "117609876543210987654",
                  "iat": now, "exp": now + 3600,
                  "email": "someone@interviewkickstart.com",
                  "email_verified": True,
                  "hd": "interviewkickstart.com", "name": "Someone"}
        claims.update(overrides)
        claims = {k: v for k, v in claims.items() if v is not ...}
        return jwt.encode(claims, key, algorithm="RS256",
                          headers={"kid": overrides.pop("kid", KID)})

    return make, jwks


def supabase_token(**overrides) -> str:
    now = int(time.time())
    claims = {"aud": "authenticated", "sub": str(uuid.uuid4()),
              "exp": now + 3600, "iat": now, "role": "authenticated",
              "email": "someone@interviewkickstart.com"}
    claims.update(overrides)
    claims = {k: v for k, v in claims.items() if v is not ...}
    return jwt.encode(claims, SB_SECRET, algorithm="HS256")


@pytest.fixture(autouse=True)
def _clear():
    reset_jwks_cache()
    reset_supabase_jwks_cache()
    yield
    reset_jwks_cache()
    reset_supabase_jwks_cache()


# ---------------------------------------------------------------------------
# THE SEAM
# ---------------------------------------------------------------------------

def test_a_google_subject_is_refused_on_a_data_route(signing):
    """THE DEFECT, as a test.

    A Google `sub` is a decimal string. auth.uid() casts to uuid. Presented on
    a data route it does not deny — it RAISES, inside the policy, and the route
    answers 500 'internal'. A credential problem arriving as a database fault
    is the wrong signal to give whoever is debugging it.
    """
    make, _ = signing
    google = make()
    with pytest.raises(AuthError) as exc:
        verify_supabase_token(google, hs256_secret=SB_SECRET)
    # AuthError specifically, not just "some exception": guard.py answers 401
    # for AuthError and 500 for everything else, so the exception TYPE is the
    # difference between "wrong credential" and "the server is broken".
    assert "/api/session" in str(exc.value), (
        "the refusal must point at where a Google token is accepted; got: "
        + str(exc.value))


def test_the_uuid_check_names_where_the_google_token_belongs():
    """A refusal that does not say what to do instead is half a refusal."""
    tok = supabase_token(sub="117609876543210987654")
    with pytest.raises(AuthError) as exc:
        verify_supabase_token(tok, hs256_secret=SB_SECRET)
    msg = str(exc.value)
    assert "not a uuid" in msg
    assert "/api/session" in msg, \
        "the message must name where a Google token IS accepted"


def test_a_uuid_subject_is_accepted():
    """The positive control. Without it the test above passes on a function
    that rejects everything."""
    sub = str(uuid.uuid4())
    ident = verify_supabase_token(supabase_token(sub=sub), hs256_secret=SB_SECRET)
    assert ident.subject == sub
    assert ident.email == "someone@interviewkickstart.com"


# ---------------------------------------------------------------------------
# Supabase token rejections
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("overrides,expect", [
    ({"aud": "anon"}, "aud"),
    ({"exp": int(time.time()) - 10}, "expired"),
    ({"sub": ...}, "sub"),
])
def test_supabase_token_rejections(overrides, expect):
    tok = supabase_token(**overrides)
    with pytest.raises(AuthError):
        verify_supabase_token(tok, hs256_secret=SB_SECRET)


def test_a_token_signed_with_the_wrong_secret_is_rejected():
    tok = jwt.encode({"aud": "authenticated", "sub": str(uuid.uuid4()),
                      "exp": int(time.time()) + 3600}, "not-our-secret",
                     algorithm="HS256")
    with pytest.raises(AuthError):
        verify_supabase_token(tok, hs256_secret=SB_SECRET)


def test_alg_none_is_rejected():
    """The classic. An unsigned token that claims it needs no signature."""
    tok = jwt.encode({"aud": "authenticated", "sub": str(uuid.uuid4()),
                      "exp": int(time.time()) + 3600}, key="", algorithm="none")
    with pytest.raises(AuthError):
        verify_supabase_token(tok, hs256_secret=SB_SECRET)


def test_user_metadata_hd_is_never_trusted():
    """GoTrue copies provider claims into user_metadata, which the USER can
    write through the auth API. An `hd` read from there is attacker-controlled.

    The identity returned by verify_supabase_token must therefore carry no
    hosted domain at all, rather than a value someone could have set.
    """
    tok = supabase_token(user_metadata={"hd": "evil.example"},
                         hd="evil.example")
    ident = verify_supabase_token(tok, hs256_secret=SB_SECRET)
    assert ident.hosted_domain == "", \
        "a Supabase token must not be a source of the domain claim"


# ---------------------------------------------------------------------------
# THE CASE THE BRIEF NAMES: IK email, no Workspace membership
# ---------------------------------------------------------------------------

class _Refused(Exception):
    pass


def _signin(make, jwks, monkeypatch, **token_overrides):
    """Run /api/session's signin decision path without an HTTP server.

    Mirrors api/session.py::handle('signin') exactly: verify OURSELVES first, and
    only then contact GoTrue. `contacted` records whether GoTrue was reached,
    which is the ordering assertion below.
    """
    contacted = {"gotrue": False}
    monkeypatch.setattr(gotrue, "SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setattr(gotrue, "ANON_KEY", "anon-test")

    def opener(req):
        contacted["gotrue"] = True
        return {"access_token": supabase_token(), "refresh_token": "rt",
                "expires_in": 3600, "user": {"id": str(uuid.uuid4()),
                                             "email": "someone@interviewkickstart.com"}}

    token = make(**token_overrides)
    try:
        verify_google_token(token, audience=AUD, jwks_fetcher=lambda: jwks)
    except AuthError as exc:
        raise _Refused(str(exc)) from exc
    session = gotrue.exchange_google_id_token(token, opener=opener)
    return session, contacted


def test_ik_email_with_no_hd_completes_oauth_and_is_still_refused(
        signing, monkeypatch):
    """The exact case `email.endsWith()` accepts.

    A correctly signed Google token, a real @interviewkickstart.com address,
    email_verified true — everything a consumer Google account with a custom
    address produces after a completely successful OAuth dance. It is refused
    because the `hd` claim is absent, and absence of `hd` means the account is
    not a member of the Workspace.
    """
    make, jwks = signing
    with pytest.raises(_Refused) as exc:
        _signin(make, jwks, monkeypatch, hd=...)
    msg = str(exc.value)
    assert "hd" in msg
    assert "consumer Google account" in msg, \
        "the refusal must explain WHY an address in the domain is not membership"


def test_our_verification_runs_before_gotrue_is_contacted(signing, monkeypatch):
    """Order, asserted rather than assumed.

    The migration-0007 hook enforces the same `hd` rule, so a reversed order
    would also refuse — but only if the hook is actually configured in the
    Supabase dashboard, which no test in this repo can assert. Verifying first
    means the refusal holds with the hook unwired, and the hook goes back to
    being what it is described as: defence in depth.
    """
    make, jwks = signing
    contacted = {}
    with pytest.raises(_Refused):
        try:
            _signin(make, jwks, monkeypatch, hd="gmail.com")
        except _Refused:
            raise
    # A refused sign-in must not have created anything upstream.
    _, contacted = _signin(make, jwks, monkeypatch)       # the accepted case
    assert contacted["gotrue"] is True, \
        "the happy path must reach GoTrue, or the check above proves nothing"


def test_a_refused_signin_never_reaches_gotrue(signing, monkeypatch):
    """The negative half of the ordering claim, measured directly."""
    make, jwks = signing
    seen = {"gotrue": False}
    monkeypatch.setattr(gotrue, "SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setattr(gotrue, "ANON_KEY", "anon-test")

    def opener(req):
        seen["gotrue"] = True
        return {}

    token = make(hd=...)
    try:
        verify_google_token(token, audience=AUD, jwks_fetcher=lambda: jwks)
        gotrue.exchange_google_id_token(token, opener=opener)
    except AuthError:
        pass
    assert seen["gotrue"] is False, \
        "a token we refused was still handed to GoTrue — a user row could exist"


# ---------------------------------------------------------------------------
# the shape of the deployed application
# ---------------------------------------------------------------------------

def test_every_api_route_goes_through_the_guard_or_is_the_session_route():
    """No path reaches data without web/lib/auth.py.

    Two shapes are permitted: a read route built with `serve(...)`, which calls
    identify() and therefore auth.py; and the session route, which verifies
    explicitly because it is the unauthenticated entry point. Anything else is
    a route that could answer without an identity.
    """
    offenders = []
    for path in sorted((REPO / "web" / "api").glob("*.py")):
        src = path.read_text(encoding="utf-8")
        if "serve(" in src:
            continue
        if path.name == "session.py":
            assert "verify_google_token" in src
            continue
        if path.name == "config.py":
            # Serves three public values and touches no database.
            assert "request_connection" not in src and "psycopg" not in src
            continue
        offenders.append(path.name)
    assert not offenders, (
        f"{offenders} reach the application without going through the guard")


def test_no_api_route_connects_as_owner_or_service_role():
    """USES, not MENTIONS.

    The first version banned the string `SERVICE_ROLE` and failed on
    api/config.py, whose docstring says the key is never read there. A check
    that cannot tell a prohibition from its own description is a check that gets
    silenced by deleting the comment.
    """
    read_key = re.compile(r"environ(\.get\(|\[)\s*[\"']\w*SERVICE_ROLE")
    for path in sorted((REPO / "web").rglob("*.py")):
        src = path.read_text(encoding="utf-8")
        assert not read_key.search(src), (
            f"{path.name} READS a service-role key from the environment")
        assert "db.SESSION" not in src, (
            f"{path.name} uses the SESSION pooler — web requests run on the "
            "TRANSACTION pooler as `authenticated`, never as the owner")


def test_nothing_the_browser_can_fetch_mentions_a_secret():
    for path in sorted((REPO / "public").rglob("*")):
        if not path.is_file() or path.name.startswith("."):
            continue
        src = path.read_text(encoding="utf-8", errors="replace")
        for banned in ("SERVICE_ROLE", "service_role", "SUPABASE_JWT_SECRET",
                       "eyJhbGciOi"):
            assert banned not in src, f"{path.name} contains {banned!r}"


def test_csp_pins_the_inline_scripts_by_hash():
    """The page is built from two inline blocks and the CSP has no
    'unsafe-inline'. Editing the HTML without recomputing the hashes would make
    the deployed page silently refuse to run its own scripts — a blank explorer
    with a console error nobody sees until someone opens devtools.

    So the hashes are recomputed here and compared.
    """
    html = (REPO / "public" / "index.html").read_text(encoding="utf-8")
    blocks = re.findall(r"<script>([\s\S]*?)</script>", html)
    assert len(blocks) == 2, f"expected 2 inline blocks, found {len(blocks)}"
    want = {"'sha256-" + base64.b64encode(
        hashlib.sha256(b.encode()).digest()).decode() + "'" for b in blocks}

    csp = ""
    vj = json.loads((REPO / "vercel.json").read_text())
    for hdr in vj["headers"][0]["headers"]:
        if hdr["key"] == "content-security-policy":
            csp = hdr["value"]
    assert csp, "no content-security-policy header configured"
    assert "unsafe-inline" not in csp.split("style-src")[0], \
        "script-src must not allow unsafe-inline: the page holds a session token"
    missing = [h for h in want if h not in csp]
    assert not missing, (
        "vercel.json's CSP does not match public/index.html. Recompute:\n"
        + "\n".join(sorted(want)))


def test_the_explorer_never_asks_for_the_whole_graph():
    """1.2 MB is small enough to ship, which is exactly why it must not be."""
    html = (REPO / "public" / "index.html").read_text(encoding="utf-8")
    for banned in ("/api/graph", "/api/all", "__NP.data =", "nodes.json"):
        assert banned not in html, f"the client references {banned!r}"
    assert "nodeBudget" in html, "no ceiling on what the client will hold"


def test_vercel_config_is_actually_tracked_by_git():
    """`/*.json` in .gitignore caught vercel.json, and nothing would have said so.

    The rule exists because a live service-account key once sat at the repo
    root. But Vercel reads its configuration from the repository: an ignored
    vercel.json deploys WITHOUT the CSP, HSTS and frame-options headers. The
    site comes up and looks right. The headers this repo carefully configures
    simply are not there.

    Checked against git itself rather than the filesystem, because the file is
    present locally either way — which is exactly why it went unnoticed.
    """
    import subprocess
    out = subprocess.run(["git", "ls-files", "--error-unmatch", "vercel.json"],
                         cwd=REPO, capture_output=True, text=True)
    assert out.returncode == 0, (
        "vercel.json is not tracked by git. Vercel reads config from the repo, "
        "so the deployment would have no security headers at all. Check "
        ".gitignore for a rule matching it.")
