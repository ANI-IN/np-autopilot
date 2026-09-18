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

def _api_modules():
    """Every route module actually shipped, found where they actually live."""
    mods = sorted(p for p in (REPO / "api").glob("*.py")
                  if p.name != "__init__.py")
    assert mods, "no route modules found — this scan is looking in the wrong place"
    return mods


def test_only_the_one_entrypoint_opens_a_database_connection():
    """THERE IS NO SECOND FRONT DOOR.

    Rewritten 2026-09-18. The previous version of this test scanned
    `web/api/` — a directory that has not existed since the WSGI consolidation
    moved every route to `api/` — so it ran over ZERO files and passed. Not a
    narrow scope: an empty one, reading as present. DECISIONS §A.7b instance 8.

    It also grepped for `serve(`, the per-file shell `api/index.py` deleted. So
    simply re-pointing it at `api/` would have made it pass on `index.py`'s
    docstring, which mentions `serve(...)` while describing its removal — the
    USES-not-MENTIONS trap that
    test_no_api_route_connects_as_owner_or_service_role was written to avoid.

    Hence AST, not substrings: this sees calls, not prose. The property it
    asserts is the one `api/index.py` actually provides — `_serve_read` is the
    only code path to a connection, and it calls identify() unconditionally, so
    a route cannot bring its own front door.
    """
    import ast

    openers = set()
    for path in _api_modules():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr == "request_connection":
                openers.add(path.name)
            if isinstance(node, ast.Name) and node.id == "request_connection":
                openers.add(path.name)

    assert openers, (
        "no module opens a connection at all. Either the data layer was renamed "
        "or this scan is again looking somewhere the routes are not — which is "
        "the exact way this test spent months passing over an empty directory.")
    # session.py is the ONE permitted exception and it is not a waiver: it is
    # the unauthenticated entry point, so it cannot be served by _serve_read
    # (there is no bearer token yet), and it must look up the profile of the
    # identity it has just verified. Its compensating control is asserted
    # below rather than assumed here.
    assert openers == {"index.py", "session.py"}, (
        f"{sorted(openers - {'index.py', 'session.py'})} open a database "
        "connection outside the single entrypoint. Every read route must be "
        "served by _serve_read, which calls identify() unconditionally.")


def test_the_session_route_verifies_google_before_it_connects():
    """The compensating control for the one module allowed its own connection.

    session.py is exempt from _serve_read because it runs before a session
    exists. That exemption is only safe while it verifies the Google token
    FIRST — connecting on an unverified subject would hand `auth.uid()` a value
    nobody checked.
    """
    import ast

    src = (REPO / "api" / "session.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    handle = next(n for n in ast.walk(tree)
                  if isinstance(n, ast.FunctionDef) and n.name == "handle")
    # Order WITHIN handle(), by line number. Comparing raw source offsets would
    # match `def _profile(...)` — the definition, which necessarily precedes the
    # call — and pass regardless of what handle() actually does.
    seen = []
    for node in ast.walk(handle):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in {"verify_google_token", "_profile", "_session_payload"}:
                seen.append((node.lineno, node.func.id))
    order = [name for _ln, name in sorted(seen)]
    assert "verify_google_token" in order, \
        "handle() no longer verifies the Google token at all"
    first_db = next((i for i, n in enumerate(order)
                     if n in {"_profile", "_session_payload"}), None)
    assert first_db is None or order.index("verify_google_token") < first_db, \
        ("the session route reaches the database before it verifies the Google "
         "token — it would be connecting on a subject nobody checked")


def test_the_entrypoint_identifies_before_it_connects():
    """The guard is not merely present in the file; it runs first.

    A test that only checked identify() appears somewhere in index.py would
    pass if it were called after the connection was opened, or in dead code.
    """
    import ast

    src = (REPO / "api" / "index.py").read_text(encoding="utf-8")
    fn = next(n for n in ast.walk(ast.parse(src))
              if isinstance(n, ast.FunctionDef) and n.name == "_serve_read")
    calls = [c.func.id for c in ast.walk(fn)
             if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)]
    attrs = [f"{c.func.value.id}.{c.func.attr}" for c in ast.walk(fn)
             if isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute)
             and isinstance(c.func.value, ast.Name)]
    assert "identify" in calls, "_serve_read no longer identifies the caller"
    assert "data.request_connection" in attrs, \
        "_serve_read no longer opens the connection — the shape changed"
    # Source order is the readable check, and it is the one that matters.
    assert src.index("identify(_Headers(environ))") < \
        src.index("data.request_connection("), \
        "identify() no longer runs before the connection is opened"


def test_no_route_module_builds_its_own_http_shell():
    """A module that answers HTTP itself would bypass _serve_read entirely."""
    import ast

    offenders = []
    for path in _api_modules():
        if path.name == "index.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name in {"do_GET", "do_POST", "app"}:
                offenders.append(f"{path.name}::{node.name}")
            if isinstance(node, ast.Attribute) and node.attr == "BaseHTTPRequestHandler":
                offenders.append(f"{path.name}::BaseHTTPRequestHandler")
    assert not offenders, (
        f"{offenders} answer HTTP directly. There is one entrypoint so that no "
        "route can forget the guard; a second one reintroduces exactly that.")


def test_every_endpoint_module_is_registered():
    """A route module nobody registered is dead code that looks live.

    The inverse of the guard question: not "can a registered route skip the
    guard" but "is there a module that believes it is a route and is not one".
    """
    import sys as _sys
    _sys.path.insert(0, str(REPO / "api"))
    _sys.path.insert(0, str(REPO / "web"))
    import index                                                  # noqa: E402

    # BOTH registries. WRITES was added for /api/curate, and a guard that knew
    # only about READS would report a registered write route as dead code —
    # or, worse, stay quiet about a genuinely unregistered one because the
    # author "fixed" the test by widening the exception list.
    registered = {fn.__module__ for _name, fn in index.READS.values()}
    registered |= {fn.__module__ for fn in index.WRITES.values()}
    declared = set()
    for path in _api_modules():
        src = path.read_text(encoding="utf-8")
        if "ENDPOINT = (" in src and path.name != "index.py":
            declared.add(path.stem)
    assert declared, "no module declares an ENDPOINT — the scan found nothing"
    assert declared <= registered | {"config", "session"}, (
        f"{sorted(declared - registered)} declare an ENDPOINT but are not in "
        "api/index.py's READS table — dead code shaped like a live route.")


def test_no_api_route_connects_as_owner_or_service_role():
    """USES, not MENTIONS.

    The first version banned the string `SERVICE_ROLE` and failed on
    api/config.py, whose docstring says the key is never read there. A check
    that cannot tell a prohibition from its own description is a check that gets
    silenced by deleting the comment.
    """
    read_key = re.compile(r"environ(\.get\(|\[)\s*[\"']\w*SERVICE_ROLE")
    # BOTH TREES. This scanned only `web/` while every HTTP route lives in
    # `api/` — eleven files, none of them ever opened by the check that STATE.md
    # cites as proof no API route holds the key. It passed because it was
    # looking in the wrong place, not because the key was absent.
    # DECISIONS §A.7b instance 8.
    scanned = sorted(list((REPO / "web").rglob("*.py"))
                     + list((REPO / "api").rglob("*.py")))
    assert any(p.parent.name == "api" for p in scanned), \
        "the service-role scan no longer reaches api/"
    for path in scanned:
        if "__pycache__" in path.parts:
            continue
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


#: What Google Identity Services needs, by directive. SPECIFIC PATHS, not the
#: bare origin — accounts.google.com also serves the whole Google account UI and
#: there is no reason to permit that.
#:
#: Every one of these was found by the page failing in a browser console, not by
#: reading the policy: the stylesheet at /gsi/style was blocked while the page
#: rendered perfectly, because a blocked stylesheet is invisible unless you are
#: looking for it.
GSI_REQUIREMENTS = {
    "script-src": "https://accounts.google.com/gsi/client",
    "style-src": "https://accounts.google.com/gsi/style",
    "connect-src": "https://accounts.google.com/gsi/",
    "frame-src": "https://accounts.google.com/gsi/",
}


def _headers() -> dict:
    vj = json.loads((REPO / "vercel.json").read_text())
    return {h["key"]: h["value"] for h in vj["headers"][0]["headers"]}


def _csp() -> dict:
    csp = _headers().get("content-security-policy", "")
    assert csp, "no content-security-policy header configured"
    out = {}
    for part in csp.split(";"):
        bits = part.split()
        if bits:
            out[bits[0]] = bits[1:]
    return out


def test_csp_pins_the_inline_scripts_by_hash():
    """The page is built from two inline blocks and script-src has no
    'unsafe-inline'. Editing the HTML without recomputing the hashes would make
    the deployed page silently refuse to run its own scripts — a blank explorer
    with a console error nobody sees until someone opens devtools."""
    html = (REPO / "public" / "index.html").read_text(encoding="utf-8")
    blocks = re.findall(r"<script>([\s\S]*?)</script>", html)
    assert len(blocks) == 2, f"expected 2 inline blocks, found {len(blocks)}"
    want = {"'sha256-" + base64.b64encode(
        hashlib.sha256(b.encode()).digest()).decode() + "'" for b in blocks}

    directives = _csp()
    script_src = directives.get("script-src", [])
    assert "'unsafe-inline'" not in script_src, \
        "script-src must not allow unsafe-inline: the page holds a session token"
    missing = [h for h in want if h not in script_src]
    assert not missing, (
        "vercel.json's CSP does not match public/index.html. Recompute:\n"
        + "\n".join(sorted(want)))


def test_csp_permits_everything_google_sign_in_actually_loads():
    """A CSP THAT BLOCKS A DEPENDENCY FAILS BY PRODUCING A PAGE THAT LOOKS FINE.

    That is the whole reason this test exists. The explorer rendered, the layout
    was correct, the console said

        Loading the stylesheet 'https://accounts.google.com/gsi/style' violates
        the following Content Security Policy directive: style-src 'self'
        'unsafe-inline'

    and the only visible symptom was a sign-in button that did not appear.
    Nothing failed loudly; the page simply omitted the thing it was blocked from
    loading. Same shape as A.7b, in a header.
    """
    directives = _csp()
    missing = []
    for directive, source in GSI_REQUIREMENTS.items():
        allowed = directives.get(directive, [])
        # A source is covered by an exact match or by a permitted prefix, since
        # 'https://accounts.google.com/gsi/' covers '/gsi/client'.
        ok = any(source == a or source.startswith(a.rstrip("/") + "/")
                 or a.startswith(source) for a in allowed)
        if not ok:
            missing.append(f"{directive} does not permit {source} "
                           f"(has: {allowed or 'nothing'})")
    assert not missing, "Google sign-in will be blocked:\n  " + "\n  ".join(missing)


def test_every_external_url_in_the_page_is_permitted_by_the_csp():
    """Derived, so a NEW dependency cannot be added without a policy for it.

    GSI_REQUIREMENTS above is a hand-written list and therefore goes stale. This
    reads the page instead: any absolute URL it references must appear somewhere
    in the policy. It will not tell you WHICH directive is right — that is the
    test above — but it will refuse to let a new origin in silently.
    """
    html = (REPO / "public" / "index.html").read_text(encoding="utf-8")
    csp = _headers().get("content-security-policy", "")
    referenced = set(re.findall(r"https://[a-zA-Z0-9.\-]+(?:/[a-zA-Z0-9./_\-]*)?",
                                html))
    # Comments and prose mention URLs that nothing loads; only count those that
    # are actually assigned to src/href. Looking at the ~30 characters before
    # each occurrence is enough and avoids a quoting-sensitive regex.
    def is_loaded(u: str) -> bool:
        for m in re.finditer(re.escape(u), html):
            before = html[max(0, m.start() - 30):m.start()]
            if re.search(r"(?:\.src|\bsrc|\bhref)\s*=\s*[\"']?\s*$", before):
                return True
        return False

    loaded = {u for u in referenced if is_loaded(u)}
    unpermitted = [u for u in loaded
                   if u not in csp and not any(
                       u.startswith(tok) for tok in csp.split() if tok.startswith("http"))]
    assert not unpermitted, (
        f"the page loads {unpermitted} but the CSP does not permit it; a blocked "
        "resource does not raise, it is simply absent")


def test_coop_allows_the_google_popup_to_talk_back():
    """GSI's popup flow calls window.postMessage on its opener.

    The default `same-origin` COOP severs that reference, so the popup completes
    the sign-in and the result never reaches the page. The console shows a COOP
    warning; the page shows a button that does nothing.
    """
    coop = _headers().get("cross-origin-opener-policy")
    assert coop == "same-origin-allow-popups", (
        f"cross-origin-opener-policy is {coop!r}; GSI's popup needs "
        "'same-origin-allow-popups' to postMessage back to the opener")


def test_the_security_headers_that_must_not_be_relaxed():
    """The rest of the set, so fixing GSI cannot quietly loosen them."""
    h = _headers()
    assert h.get("x-frame-options") == "DENY"
    assert h.get("x-content-type-options") == "nosniff"
    assert h.get("referrer-policy") == "no-referrer"
    assert "max-age=" in h.get("strict-transport-security", "")
    d = _csp()
    assert d.get("default-src") == ["'self'"]
    assert d.get("object-src") == ["'none'"]
    assert d.get("base-uri") == ["'none'"]


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
