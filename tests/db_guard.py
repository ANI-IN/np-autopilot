"""Read-only enforcement for `production_only` tests.

A `production_only` test asserts on production's own rows, so it runs against
production — and it must be unable to write there. Not "is written not to":
UNABLE. The enforcement is server-side, `default_transaction_read_only=on`
passed through libpq's PGOPTIONS, so it covers every connection the test opens,
autocommit ones, and any subprocess it spawns. A write raises
`ReadOnlySqlTransaction` and the test fails.

It is VERIFIED before the test runs, never assumed: a pooler that dropped the
startup option would otherwise leave the test running unguarded while looking
guarded. If the target does not report read-only, the test fails instead.
"""
from __future__ import annotations

import os
from contextlib import contextmanager, nullcontext

from pipeline.lib import db

READ_ONLY_OPTION = "-c default_transaction_read_only=on"


def guard_for(node):
    """The guard a test item runs under: read-only if marked production_only.
    The conftest fixture is only `with guard_for(request.node): yield`, so this
    is the wiring, and it is what the canaries test."""
    if node.get_closest_marker("production_only"):
        return read_only_database()
    return nullcontext()


@contextmanager
def read_only_database():
    saved = {k: os.environ.get(k) for k in ("PGOPTIONS", db.TRANSACTION)}
    os.environ["PGOPTIONS"] = f"{saved['PGOPTIONS'] or ''} {READ_ONLY_OPTION}".strip()
    # Route transaction-pooler connections through the session URL, the one
    # the check below verifies — a transaction pooler may not forward options.
    if os.environ.get(db.SESSION):
        os.environ[db.TRANSACTION] = os.environ[db.SESSION]
    try:
        with db.connect(db.SESSION) as conn, conn.cursor() as cur:
            cur.execute("show default_transaction_read_only")
            state = cur.fetchone()[0]
        if state != "on":
            raise RuntimeError(
                "production_only test NOT RUN: the target did not accept "
                f"read-only mode (default_transaction_read_only={state}); "
                "refusing to run it unguarded")
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
