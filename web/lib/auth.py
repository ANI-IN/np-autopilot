"""Layer 2 — Google Workspace identity, verified server-side.

DECISIONS §D, stated there and implemented here:

  **Email-claim string matching is not sufficient.** `email.endswith("@ik.com")`
  trusts a claim that may be unverified, and a consumer Google account can carry
  an address in your domain without belonging to your Workspace. The `hd`
  (hosted domain) claim is what distinguishes the two — and only when it arrives
  on a token whose SIGNATURE and AUDIENCE were checked against Google's JWKS.

So every one of these is a rejection, and each has its own test:

  - signature that does not verify against Google's published keys
  - `iss` that is not accounts.google.com
  - `aud` that is not our client id          (a token minted for another app)
  - `exp` in the past
  - `email_verified` false
  - `hd` absent                              (a consumer account)
  - `hd` present but not interviewkickstart.com
  - an @interviewkickstart.com EMAIL with a wrong or absent `hd`  <- the one
    that `email.endswith()` would have let through

No network call is made to verify a token beyond fetching Google's keys, which
are cached. The keys are the only thing fetched; the claims are never trusted
from the client.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass

GOOGLE_ISSUERS = ("https://accounts.google.com", "accounts.google.com")
GOOGLE_JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"

#: The one domain. Not configurable by request, only by deployment.
ALLOWED_HD = os.environ.get("NP_ALLOWED_HD", "interviewkickstart.com")

_JWKS_CACHE: dict = {"keys": None, "fetched_at": 0.0}
_JWKS_TTL = 3600


class AuthError(Exception):
    """Rejection. The message says which check failed, for the audit log."""


@dataclass(frozen=True)
class Identity:
    subject: str
    email: str
    hosted_domain: str
    email_verified: bool
    name: str | None = None

    @property
    def is_shared_account(self) -> bool:
        """Best-effort. A shared team mailbox resolves several humans to one id.

        Cannot be detected reliably from a token — Google does not say. Named
        here so docs/AUTH.md can be honest that the audit log identifies an
        ACCOUNT, not a person, and so a known shared address is at least flagged.
        """
        local = self.email.split("@", 1)[0].lower()
        return local in {s.strip().lower()
                         for s in os.environ.get("NP_SHARED_ACCOUNTS", "").split(",")
                         if s.strip()}


def _fetch_jwks(fetcher=None) -> dict:
    """Google's public keys, cached. `fetcher` is injected by tests."""
    now = time.time()
    if _JWKS_CACHE["keys"] and now - _JWKS_CACHE["fetched_at"] < _JWKS_TTL:
        return _JWKS_CACHE["keys"]
    if fetcher is None:
        import json
        import urllib.request
        with urllib.request.urlopen(GOOGLE_JWKS_URL, timeout=10) as resp:
            keys = json.loads(resp.read())
    else:
        keys = fetcher()
    _JWKS_CACHE.update(keys=keys, fetched_at=now)
    return keys


def reset_jwks_cache() -> None:
    _JWKS_CACHE.update(keys=None, fetched_at=0.0)


def verify_google_token(token: str, *, audience: str | None = None,
                        jwks_fetcher=None, leeway: int = 0) -> Identity:
    """Verify a Google ID token and return the identity, or raise AuthError.

    Order matters: the signature is checked FIRST. Every claim below is only
    meaningful because the token was signed by Google, and reading a claim off
    an unverified token to decide whether to verify it is the classic inversion.
    """
    import jwt
    from jwt import PyJWKClient  # noqa: F401  (imported for parity with prod use)

    audience = audience or os.environ.get("GOOGLE_OAUTH_CLIENT_ID")
    if not audience:
        raise AuthError("no audience configured: set GOOGLE_OAUTH_CLIENT_ID")

    try:
        header = jwt.get_unverified_header(token)
    except Exception as exc:                                   # noqa: BLE001
        raise AuthError(f"malformed token: {exc}") from exc
    kid = header.get("kid")
    if not kid:
        raise AuthError("token header has no kid")

    jwks = _fetch_jwks(jwks_fetcher)
    match = next((k for k in jwks.get("keys", []) if k.get("kid") == kid), None)
    if match is None:
        raise AuthError(f"no Google signing key matches kid {kid!r}")

    try:
        key = jwt.PyJWK(match).key
    except Exception as exc:                                   # noqa: BLE001
        raise AuthError(f"unusable signing key: {exc}") from exc

    try:
        claims = jwt.decode(
            token, key=key,
            algorithms=[match.get("alg", "RS256")],
            audience=audience,
            issuer=list(GOOGLE_ISSUERS),
            leeway=leeway,
            options={"require": ["exp", "iat", "aud", "iss", "sub"],
                     "verify_signature": True, "verify_exp": True,
                     "verify_aud": True, "verify_iss": True},
        )
    except Exception as exc:                                   # noqa: BLE001
        raise AuthError(f"token rejected: {type(exc).__name__}: {exc}") from exc

    email = (claims.get("email") or "").strip().lower()
    if not email:
        raise AuthError("token carries no email")
    if claims.get("email_verified") is not True:
        raise AuthError("email_verified is not true")

    # THE CHECK THAT MATTERS.
    hd = (claims.get("hd") or "").strip().lower()
    if not hd:
        raise AuthError(
            f"token has no hd claim — {email} is a consumer Google account, not a "
            "Workspace identity. An address in the domain is not membership of it."
        )
    if hd != ALLOWED_HD:
        raise AuthError(f"hd is {hd!r}, not {ALLOWED_HD!r}")

    # Belt and braces, and deliberately AFTER hd rather than instead of it: a
    # token whose hd is ours but whose email is elsewhere is incoherent.
    if not email.endswith("@" + ALLOWED_HD):
        raise AuthError(f"hd is {hd!r} but email {email!r} is not in that domain")

    return Identity(subject=claims["sub"], email=email, hosted_domain=hd,
                    email_verified=True, name=claims.get("name"))
