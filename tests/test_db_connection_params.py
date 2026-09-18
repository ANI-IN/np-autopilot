"""The connection URL must not be parsed twice, by two different parsers.

FOUND IN PRODUCTION, from a Vercel runtime traceback:

    psycopg.OperationalError: failed to resolve host
      '2026@aws-0-ap-northeast-2.pooler.supabase.com'

The password contains a literal `@`, correctly written `%40` in the URL. Local
psycopg decodes it once and connects. The psycopg vendored into the Vercel
bundle decodes the netloc and then re-splits it, so

    postgres://user:pw%402026@aws-0-....pooler.supabase.com:6543/postgres

became `user:pw@2026@aws-0-...`, it took the FIRST `@`, and the host came out as
`2026@aws-0-...`. Every authenticated request 500'd, and only on Vercel.

This is the works-on-my-laptop-fails-in-production shape that DECISIONS §C
raises about the IPv6-only direct connection, arriving by a completely
different route — which is the useful part. The lesson generalises past the one
host that was already named.

`db.params()` splits the URL ONCE, here, and hands psycopg discrete keywords.
There is no string left for a second parser to disagree about.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from pipeline.lib import db                                            # noqa: E402


def _with_url(monkeypatch, url: str, var: str = db.TRANSACTION):
    monkeypatch.setenv(var, url)
    return db.params(var)


def test_a_percent_encoded_at_in_the_password_survives(monkeypatch):
    """THE PRODUCTION BUG, as a test."""
    p = _with_url(monkeypatch,
                  "postgres://postgres.abc:se%40cret%402026@"
                  "aws-0-ap-northeast-2.pooler.supabase.com:6543/postgres")
    assert p["host"] == "aws-0-ap-northeast-2.pooler.supabase.com", \
        f"the host absorbed part of the password: {p['host']!r}"
    assert p["port"] == 6543
    assert p["user"] == "postgres.abc"
    assert p["password"] == "se@cret@2026", \
        "the password must arrive DECODED — psycopg is given a parameter, not a URL"
    assert p["dbname"] == "postgres"


def test_other_url_specials_in_the_password(monkeypatch):
    """`@` is the one that breaks hosts, but it is not the only escape."""
    p = _with_url(monkeypatch,
                  "postgres://u:a%2Fb%3Ac%23d%3Fe%25f@host.example:5432/postgres")
    assert p["password"] == "a/b:c#d?e%f"
    assert p["host"] == "host.example"


def test_a_raw_at_in_the_password_takes_the_LAST_one(monkeypatch):
    """The property that makes discrete parameters safe.

    `urlparse` splits the netloc at the LAST '@', which is what RFC 3986 says
    and what produces the right answer even for a password containing a raw,
    unencoded '@'. The Vercel-side failure came from a parser that decoded
    first and then split at the FIRST '@'.

    So this is the contract being relied on, asserted rather than assumed:
    whatever the password contains, the host is the part after the final '@'.
    """
    p = _with_url(monkeypatch, "postgres://u:p@bad@host.example:6543/db")
    assert p["host"] == "host.example"
    assert p["password"] == "p@bad"
    assert p["dbname"] == "db"


def test_the_direct_connection_is_still_refused(monkeypatch):
    """Splitting into parameters must not bypass assert_not_direct.

    The IPv6-only direct host is the original works-locally-fails-on-Vercel
    case; a refactor that quietly dropped the check would restore it.
    """
    monkeypatch.setenv(db.TRANSACTION,
                       "postgres://u:p@db.yqmzjgzhxhihnpbgqmeh.supabase.co:5432/postgres")
    with pytest.raises(RuntimeError) as exc:
        db.params(db.TRANSACTION)
    assert "refusing the direct connection" in str(exc.value)


def test_a_missing_variable_still_names_itself(monkeypatch):
    monkeypatch.delenv(db.TRANSACTION, raising=False)
    with pytest.raises(RuntimeError) as exc:
        db.params(db.TRANSACTION)
    assert db.TRANSACTION in str(exc.value)


@pytest.mark.skipif(not db.available(), reason="needs the Supabase connection")
def test_the_real_configured_url_parses_and_connects():
    """The positive control, against the URL actually in use.

    Without this the tests above pass on a function that is never given the
    shape production has.
    """
    p = db.params(db.TRANSACTION)
    assert "@" not in (p["host"] or "")
    assert p["port"] == 6543, "web requests must use the transaction pooler"
    with db.connect(db.TRANSACTION) as conn, conn.cursor() as cur:
        cur.execute("select 1")
        assert cur.fetchone()[0] == 1
