"""E2 layer 2 — every way a token can be wrong, and that it is rejected.

Tokens are signed here with a locally generated RSA key and verified against a
locally served JWKS. No network, no real Google, no fixture token that expires.
That matters: an auth test that needs the internet is an auth test that gets
skipped in CI, and a skipped auth test is worse than none.

The case this file exists for is `test_ik_email_with_no_hd_is_rejected`: a token
carrying an @interviewkickstart.com address that `email.endswith()` would accept
and that must be refused, because an address in the domain is not membership of
the Workspace.
"""
from __future__ import annotations

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

from lib.auth import (AuthError, Identity, reset_jwks_cache,       # noqa: E402
                      verify_google_token)

AUD = "np-autopilot-test.apps.googleusercontent.com"
ISS = "https://accounts.google.com"
KID = "test-key-1"


@pytest.fixture(scope="module")
def signing():
    """One RSA key, its JWKS, and a token factory."""
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
        claims = {"iss": ISS, "aud": AUD, "sub": str(uuid.uuid4()),
                  "iat": now, "exp": now + 3600,
                  "email": "someone@interviewkickstart.com",
                  "email_verified": True,
                  "hd": "interviewkickstart.com",
                  "name": "Someone"}
        claims.update(overrides)
        claims = {k: v for k, v in claims.items() if v is not ...}
        return jwt.encode(claims, key, algorithm="RS256",
                          headers={"kid": overrides.pop("kid", KID)})

    return make, jwks, key


@pytest.fixture(autouse=True)
def _clear_cache():
    reset_jwks_cache()
    yield
    reset_jwks_cache()


def _verify(token, jwks, **kw):
    return verify_google_token(token, audience=AUD, jwks_fetcher=lambda: jwks, **kw)


# --------------------------------------------------------------------------
# the happy path, so every rejection below means something
# --------------------------------------------------------------------------

def test_a_valid_workspace_token_is_accepted(signing):
    make, jwks, _ = signing
    ident = _verify(make(), jwks)
    assert isinstance(ident, Identity)
    assert ident.email == "someone@interviewkickstart.com"
    assert ident.hosted_domain == "interviewkickstart.com"
    assert ident.email_verified is True


# --------------------------------------------------------------------------
# THE case: an IK email that endswith() would accept
# --------------------------------------------------------------------------

def test_ik_email_with_no_hd_is_rejected(signing):
    """A consumer Google account can carry an address in the domain.

    This is the exact token `email.endswith("@interviewkickstart.com")` would
    have accepted, and it is the reason DECISIONS §D says string matching is not
    sufficient.
    """
    make, jwks, _ = signing
    with pytest.raises(AuthError) as exc:
        _verify(make(hd=...), jwks)          # `...` drops the claim entirely
    assert "no hd claim" in str(exc.value)
    assert "consumer Google account" in str(exc.value)


def test_ik_email_with_wrong_hd_is_rejected(signing):
    make, jwks, _ = signing
    with pytest.raises(AuthError) as exc:
        _verify(make(hd="someoneelse.com"), jwks)
    assert "not 'interviewkickstart.com'" in str(exc.value)


def test_our_hd_with_a_foreign_email_is_rejected(signing):
    """Incoherent, and checked AFTER hd rather than instead of it."""
    make, jwks, _ = signing
    with pytest.raises(AuthError) as exc:
        _verify(make(email="someone@gmail.com"), jwks)
    assert "is not in that domain" in str(exc.value)


# --------------------------------------------------------------------------
# signature, issuer, audience, expiry — the reasons a claim is trustworthy
# --------------------------------------------------------------------------

def test_a_token_signed_by_someone_else_is_rejected(signing):
    """The whole basis of every claim above."""
    from cryptography.hazmat.primitives.asymmetric import rsa
    make, jwks, _ = signing
    attacker = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = int(time.time())
    forged = jwt.encode(
        {"iss": ISS, "aud": AUD, "sub": "forged", "iat": now, "exp": now + 3600,
         "email": "someone@interviewkickstart.com", "email_verified": True,
         "hd": "interviewkickstart.com"},
        attacker, algorithm="RS256", headers={"kid": KID})
    with pytest.raises(AuthError) as exc:
        _verify(forged, jwks)
    assert "token rejected" in str(exc.value)


def test_a_token_for_another_audience_is_rejected(signing):
    """A token minted for a different app, replayed at ours."""
    make, jwks, _ = signing
    with pytest.raises(AuthError) as exc:
        _verify(make(aud="some-other-app.apps.googleusercontent.com"), jwks)
    assert "token rejected" in str(exc.value)


def test_a_token_from_another_issuer_is_rejected(signing):
    make, jwks, _ = signing
    with pytest.raises(AuthError):
        _verify(make(iss="https://evil.example.com"), jwks)


def test_an_expired_token_is_rejected(signing):
    make, jwks, _ = signing
    now = int(time.time())
    with pytest.raises(AuthError) as exc:
        _verify(make(iat=now - 7200, exp=now - 3600), jwks)
    assert "token rejected" in str(exc.value)


def test_an_unverified_email_is_rejected(signing):
    make, jwks, _ = signing
    with pytest.raises(AuthError) as exc:
        _verify(make(email_verified=False), jwks)
    assert "email_verified" in str(exc.value)


def test_an_unknown_kid_is_rejected(signing):
    """Google rotates keys; a token whose key we cannot find is not trusted."""
    make, jwks, _ = signing
    token = make(kid="some-other-kid")
    with pytest.raises(AuthError) as exc:
        _verify(token, jwks)
    assert "no Google signing key matches" in str(exc.value)


def test_an_unsigned_token_is_rejected(signing):
    """alg=none. The oldest JWT attack, and it must not work."""
    _, jwks, _ = signing
    now = int(time.time())
    unsigned = jwt.encode(
        {"iss": ISS, "aud": AUD, "sub": "x", "iat": now, "exp": now + 3600,
         "email": "someone@interviewkickstart.com", "email_verified": True,
         "hd": "interviewkickstart.com"},
        key="", algorithm="none", headers={"kid": KID})
    with pytest.raises(AuthError):
        _verify(unsigned, jwks)


def test_a_missing_required_claim_is_rejected(signing):
    make, jwks, _ = signing
    with pytest.raises(AuthError):
        _verify(make(sub=...), jwks)


def test_garbage_is_rejected_without_crashing(signing):
    _, jwks, _ = signing
    for junk in ("", "not.a.token", "a.b", "..", "x" * 500):
        with pytest.raises(AuthError):
            _verify(junk, jwks)


# --------------------------------------------------------------------------
# the shared-account problem, named rather than hidden
# --------------------------------------------------------------------------

def test_a_known_shared_account_is_flagged(signing, monkeypatch):
    """The Drive folder is owned by b2c-courses-new-programs@, a team account.

    If people sign in as it, several humans resolve to one identity and the §E.4
    audit trail cannot answer its own question. It cannot be detected from a
    token, so known addresses are configured and flagged. docs/AUTH.md says the
    log identifies an account, not a person.
    """
    make, jwks, _ = signing
    monkeypatch.setenv("NP_SHARED_ACCOUNTS", "b2c-courses-new-programs")
    ident = _verify(make(email="b2c-courses-new-programs@interviewkickstart.com"),
                    jwks)
    assert ident.is_shared_account is True
    normal = _verify(make(), jwks)
    assert normal.is_shared_account is False
