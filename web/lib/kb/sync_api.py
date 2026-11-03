"""The sync's HTTP side: the protected cron route, "Sync now", the run log.

Where it runs (docs/DEPLOYMENT.md, "Scheduled sync"): the SCHEDULE lives in the
database (pg_cron + pg_net in each Supabase project, dev and production alike,
calling this deployment's /api/cron/kb-sync with a secret from Vault); the WORK
runs here, in the Vercel function, under a time budget below the function's
limit. Vercel's own cron only fires on Production deployments, so it could not
drive a preview; the database schedule can, and one design serves both.

The sync writes as the kb tables' OWNER (the pooler login), on a connection of
its own: only after the caller is proven to be the scheduler (the secret) or a
KB admin ("Sync now"). Every change is attributed to actor_type 'sync'.
"""
from __future__ import annotations

import hmac
import os

from . import sync


def budget() -> float:
    try:
        return max(3.0, float(os.environ.get("KB_SYNC_BUDGET_SECONDS", "10")))
    except ValueError:
        return 10.0


def cron_authorised(header: str | None) -> bool:
    secret = os.environ.get("KB_SYNC_SECRET", "")
    if len(secret) < 24 or not header:
        return False
    want = "Bearer " + secret
    return hmac.compare_digest(header.encode(), want.encode())


def run_now(trigger: str, actor_id: str | None) -> dict:
    """One time-boxed run on an owner connection. Never raises for a sync
    failure: the run log records it (and admins see the banner)."""
    from pipeline.lib import db
    if not sync.enabled():
        return {"status": "disabled", "message": "KB_SYNC_ENABLED is false: the sync is switched off"}
    conn = db.connect(db.TRANSACTION)
    try:
        out = sync.run(conn, trigger=trigger, actor_id=actor_id, apply=True, budget_seconds=budget())
    except Exception as exc:                                    # noqa: BLE001 - logged in kb.sync_runs by sync.run
        return {"status": "error", "message": f"{type(exc).__name__}: {str(exc)[:200]}"}
    finally:
        conn.close()
    out.pop("report", None)
    return out


def status(conn, limit: int = 20) -> dict:
    rows = conn.execute("""select id, started_at, finished_at, status, trigger, actor_id, counts, conflicts, errors, message
                           from kb.sync_runs order by id desc limit %s""", (limit,)).fetchall()
    cols = ("id", "started_at", "finished_at", "status", "trigger", "actor_id", "counts", "conflicts", "errors", "message")
    runs = [dict(zip(cols, r)) for r in rows]
    last = next((r for r in runs if r["status"] != "skipped"), None)
    return {"enabled": sync.enabled(), "budget_seconds": budget(), "runs": runs,
            "failing": bool(last and last["status"] == "error"), "last": last}
