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


# ---------------------------------------------------------------------------
# The seam: a Google `sub` is NOT a uuid, and `auth.uid()` casts to one.
# ---------------------------------------------------------------------------
#
# Found by joining the layers rather than testing them apart. `profiles.user_id`
# is uuid, `np_role()` resolves through `auth.uid()`, and `auth.uid()` is
#
#     (current_setting('request.jwt.claims')::jsonb ->> 'sub')::uuid
#
# A Google subject is a decimal string like 117609876543210987654. Setting it as
# `sub` makes every policy evaluation raise
#
#     invalid input syntax for type uuid: "117609876543210987654"
#
# so every authenticated request would have returned 500. Each layer was green;
# the join between layer 2 and layer 1 had never been exercised. It fails loudly
# rather than silently, which is the one mercy — but it means the Google token
# cannot be the thing the database sees.
#
# So there are two tokens, with different jobs:
#
#   GOOGLE ID TOKEN    proves Workspace membership. Verified here, by
#                      verify_google_token, with the `hd` check. Presented once,
#                      at /api/session.
#   SUPABASE ACCESS    proves an established session and carries a uuid `sub`
#     TOKEN            that auth.uid() can resolve. Presented on every request.
#                      Exists only because GoTrue minted it, and GoTrue only
#                      mints it after the migration-0007 hook accepted the `hd`.
#
# Both are verified in THIS module. That is the point: there is exactly one
# place that turns a string into an identity.

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")

_SB_JWKS_CACHE: dict = {"keys": None, "fetched_at": 0.0}


def _supabase_jwks(fetcher=None) -> dict:
    """Supabase's own signing keys, for projects using asymmetric JWTs."""
    now = time.time()
    if _SB_JWKS_CACHE["keys"] and now - _SB_JWKS_CACHE["fetched_at"] < _JWKS_TTL:
        return _SB_JWKS_CACHE["keys"]
    if fetcher is None:
        import json
        import urllib.request
        url = f"{SUPABASE_URL}/auth/v1/.well-known/jwks.json"
        with urllib.request.urlopen(url, timeout=10) as resp:
            keys = json.loads(resp.read())
    else:
        keys = fetcher()
    _SB_JWKS_CACHE.update(keys=keys, fetched_at=now)
    return keys


def reset_supabase_jwks_cache() -> None:
    _SB_JWKS_CACHE.update(keys=None, fetched_at=0.0)


def verify_supabase_token(token: str, *, jwks_fetcher=None,
                          hs256_secret: str | None = None,
                          leeway: int = 0) -> Identity:
    """Verify a Supabase (GoTrue) access token and return the identity.

    Supports both project shapes: asymmetric keys published at the project's
    JWKS endpoint, and the legacy shared HS256 secret. The algorithm is chosen
    from the VERIFIED key material, never from the token's own header — reading
    `alg` off an unverified token to decide how to verify it is how `alg: none`
    and HS/RS confusion get in.

    What this does NOT do, deliberately: trust `user_metadata`. GoTrue copies
    the provider's claims there at signup, and `user_metadata` is writable by
    the user through the auth API. So `hd` read from a Supabase token is an
    attacker-controlled string. The domain guarantee comes from two places that
    are not: the migration-0007 hook, which refuses to create the user at all,
    and `profiles.email_domain`, which carries a CHECK constraint and is written
    only from a Google token this module verified.
    """
    import jwt

    try:
        header = jwt.get_unverified_header(token)
    except Exception as exc:                                   # noqa: BLE001
        raise AuthError(f"malformed token: {exc}") from exc

    secret = hs256_secret if hs256_secret is not None else \
        os.environ.get("SUPABASE_JWT_SECRET")
    kid = header.get("kid")

    key = None
    algorithms: list[str] = []
    if kid:
        # Any failure fetching or parsing the keys must surface as AuthError.
        # It escaped as ValueError once — a Google token carries a `kid`, so it
        # took this branch, and with SUPABASE_URL unset urllib raised "unknown
        # url type". guard.py catches AuthError and answers 401; everything else
        # becomes a 500, so the wrong credential presented itself as a server
        # fault. Caught by test_a_google_subject_is_refused_on_a_data_route.
        try:
            jwks = _supabase_jwks(jwks_fetcher)
        except AuthError:
            raise
        except Exception as exc:                               # noqa: BLE001
            raise AuthError(
                f"cannot fetch Supabase signing keys: {type(exc).__name__}: "
                f"{exc}. If this token came from Google, it belongs at "
                "/api/session, not on a data request.") from exc
        match = next((k for k in jwks.get("keys", []) if k.get("kid") == kid), None)
        if match is None:
            # The production shape of "a Google token arrived on a data route":
            # the fetch succeeds, and Google's kid is simply not one of ours.
            # Without the second sentence this reads as a key-rotation problem.
            raise AuthError(
                f"no Supabase signing key matches kid {kid!r}. If this token "
                "was issued by Google, it belongs at /api/session, which trades "
                "it for a session; a data request carries the Supabase access "
                "token that returns.")
        try:
            key = jwt.PyJWK(match).key
        except Exception as exc:                               # noqa: BLE001
            raise AuthError(f"unusable Supabase signing key: {exc}") from exc
        algorithms = [match.get("alg", "RS256")]
    elif secret:
        key, algorithms = secret, ["HS256"]
    else:
        raise AuthError(
            "cannot verify a Supabase token: the token has no kid and "
            "SUPABASE_JWT_SECRET is not set")

    issuer = f"{SUPABASE_URL}/auth/v1" if SUPABASE_URL else None
    try:
        claims = jwt.decode(
            token, key=key, algorithms=algorithms,
            audience="authenticated",
            **({"issuer": issuer} if issuer else {}),
            leeway=leeway,
            options={"require": ["exp", "aud", "sub"],
                     "verify_signature": True, "verify_exp": True,
                     "verify_aud": True, "verify_iss": bool(issuer)},
        )
    except Exception as exc:                                   # noqa: BLE001
        raise AuthError(f"token rejected: {type(exc).__name__}: {exc}") from exc

    subject = str(claims.get("sub") or "")
    # The whole reason this function exists. A `sub` that is not a uuid makes
    # every RLS policy raise rather than deny, so it is refused HERE, where the
    # message can say what is wrong, instead of 500ing inside a policy.
    try:
        import uuid as _uuid
        _uuid.UUID(subject)
    except Exception as exc:                                   # noqa: BLE001
        raise AuthError(
            f"subject {subject!r} is not a uuid. auth.uid() casts sub to uuid, "
            "so this token would make every policy evaluation raise. A Google "
            "ID token belongs at /api/session, not on a data request."
        ) from exc

    email = (claims.get("email") or "").strip().lower()
    return Identity(subject=subject, email=email,
                    hosted_domain="",          # NOT from this token. See above.
                    email_verified=bool(claims.get("email_verified", False)),
                    name=None)
