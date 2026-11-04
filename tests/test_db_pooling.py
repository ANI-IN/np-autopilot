"""Request-scoped connections must use Supabase's TRANSACTION pooler (6543),
never the session pooler (5432) or the direct host: many Vercel instances each
holding a warm connection would exhaust the session pool (docs/operations/deployment.md,
"Connection pooling"). No database needed."""
from __future__ import annotations

import pytest

from pipeline.lib import db


@pytest.mark.parametrize("url", [
    "postgresql://u.ref:pw@aws-0-region.pooler.supabase.com:5432/postgres",
    "postgresql://postgres:pw@db.abcdefghijklmnopqrst.supabase.co:5432/postgres",
])
def test_request_connections_refuse_anything_but_the_transaction_pooler(url):
    with pytest.raises(RuntimeError):
        db.assert_transaction_pooler(url)


@pytest.mark.parametrize("url", [
    "postgresql://u.ref:pw@aws-0-region.pooler.supabase.com:6543/postgres",
    "postgresql://postgres:postgres@127.0.0.1:54322/postgres",          # local stack: not checked
    "postgresql://postgres.pooler-dev:postgres@127.0.0.1:6543/postgres",
])
def test_the_transaction_pooler_and_local_stacks_are_accepted(url):
    db.assert_transaction_pooler(url)


def test_the_request_path_opens_the_transaction_variable():
    from pathlib import Path
    src = (Path(__file__).resolve().parent.parent / "web" / "lib" / "data.py").read_text(encoding="utf-8")
    assert "_db.connect(_db.TRANSACTION)" in src
