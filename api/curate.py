"""POST /api/curate — record a curation decision.

F1: the ONLY HTTP path to a curation write, and it adds nothing to
`web/lib/curation_service.py`'s contract. The role check, the optimistic-locking
predicate and the audit row all live there; this file translates HTTP to that
call and its failures back to status codes.

WHY EACH FAILURE GETS ITS OWN STATUS. "Nothing happened" is the shape this
project keeps being bitten by (DECISIONS §A.7b), and a curation write has three
completely different ways to not happen:

    403  you are not an admin, or you are a shared account
    409  someone changed the row first — YOUR WRITE DID NOT HAPPEN
    400  you gave no reason

Collapsing those into one error would leave a person re-clicking a button that
will never work, or worse, believing a decision was recorded that was not.

409 IS THE ONE THAT MATTERS. Two people resolving `ML` differently within a
minute is exactly the scenario the locking exists for, and the loser must be
told loudly enough to re-read and decide again rather than quietly overwritten.
"""
import sys
from pathlib import Path
# Vercel discovers Python functions at /api in the project root, so this
# file sits one level above web/. The shared modules stay in web/lib.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "web"))
from lib import curation_service as cs                                 # noqa: E402


def _actor(conn, identity) -> cs.Actor:
    """Built from the DATABASE, not from the token.

    `Identity.is_shared_account` is best-effort — Google does not tell us — and
    migration 0014 exists precisely because a shared-account flag the caller
    supplies is the caller's opinion with a constraint's reputation. The role
    and the flag both come from the row here.
    """
    with conn.cursor() as cur:
        cur.execute("select np_role()")
        role = cur.fetchone()[0]
        cur.execute("select email, is_shared_account from profiles "
                    "where user_id = auth.uid()")
        row = cur.fetchone()
    email = row[0] if row else (identity.email or "")
    shared = bool(row[1]) if row else False
    return cs.Actor(user_id=str(identity.subject), email=email, role=role,
                    shared_account=shared)


def handle(conn, identity, body: dict) -> tuple[int, dict]:
    table = (body.get("table") or "").strip()
    key = (body.get("key") or "").strip()
    changes = body.get("changes")
    reason = body.get("reason") or ""
    version = body.get("expected_version")

    if not table or not key or not isinstance(changes, dict) or not changes:
        return 400, {"error": "bad_request",
                     "reason": "table, key and a non-empty changes object are required"}
    if not isinstance(version, int):
        # No default, deliberately: see curation_service.update_row. A missing
        # version must not silently become last-write-wins.
        return 400, {"error": "bad_request",
                     "reason": "expected_version is required and must be the "
                               "integer you read with the row"}

    actor = _actor(conn, identity)

    # CONFIRMATION IS STAMPED SERVER-SIDE, never taken from the body. Otherwise
    # a caller could record someone else as the confirmer, which is the one
    # field the audit trail exists to make trustworthy.
    if changes.get("confirmed") is True:
        from datetime import datetime, timezone
        changes["confirmed_by"] = actor.email
        changes["confirmed_at"] = datetime.now(timezone.utc)

        # AND THE REASONING GOES INTO THE ROW, not only into curation_audit.
        #
        # curation_audit records who changed what and why, and it is the right
        # place for that. But `pipeline/curation.py export` writes the TABLE
        # back to YAML, and the audit table is not part of that round trip — so
        # a decision whose reasoning lives only in the audit would come back as
        # a bare mapping with no trace of why. A future fuzzy pass then sees two
        # plausible names and no record of the human who said they are different
        # people, which is exactly how `Karthika S` and `Karthika Pai` get
        # re-merged. Appended, never overwritten: the existing `why` records why
        # the alias was ambiguous, and that stays true after it is resolved.
        with conn.cursor() as cur:
            cur.execute("select note from domain_aliases where alias = %s", (key,))
            prior_row = cur.fetchone()
        prior = (prior_row[0] if prior_row else "") or ""
        stamp = datetime.now(timezone.utc).date().isoformat()
        decision = (f"RESOLVED {stamp} by {actor.email}: {reason.strip()}")
        changes["note"] = f"{prior}\n\n{decision}".strip() if prior else decision

    try:
        after = cs.update_row(conn, actor, table, key, changes, version, reason)
    except cs.NoReason as exc:
        return 400, {"error": "no_reason", "reason": str(exc)}
    except cs.NotPermitted as exc:
        return 403, {"error": "forbidden", "reason": str(exc)}
    except cs.StaleVersion as exc:
        return 409, {"error": "stale_version", "reason": str(exc)}
    return 200, {"row": after, "recorded_by": actor.email}


#: (endpoint name, write function). Registered in api/index.py's WRITES table.
ENDPOINT = ("curate", handle)
