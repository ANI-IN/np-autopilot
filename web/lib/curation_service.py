"""F1 — the only path a curation write may take.

Three things happen here and nowhere else: the caller's role is checked, the
write carries an optimistic-locking predicate, and the before/after pair is
audited with a stated reason.

WHY OPTIMISTIC LOCKING IS NOT CEREMONY HERE. `lib/resolve.py` returns
`Ambiguous` by default because three shipped bugs had the same shape — several
plausible targets, one chosen, no signal to the caller. A lost curation update
is that failure with a database underneath it: two people resolve the `ML` alias
differently within the same minute, last-write-wins, and the losing decision
vanishes with nobody told. The second writer must fail LOUDLY.

A trigger refuses any write that does not arrive through here, so "just this
once, directly" is not available.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import data                                                   # noqa: E402
from pipeline.lib import taxonomy as _tax                              # noqa: E402

#: table -> (primary key column, columns a caller may set)
WRITABLE = {
    "people": ("canonical", {"team", "title", "seniority", "props"}),
    "domain_aliases": ("alias", {"domain", "claims", "sibling_test", "confirmed",
                                 "confirmed_by", "confirmed_at", "note", "props"}),
    "workflow_owners": ("workflow_id", {"name", "theme_id", "owner", "confirmed",
                                        "suggestion", "evidence", "props"}),
}


class NotPermitted(Exception):
    """The caller is not an admin."""


class StaleVersion(Exception):
    """Someone else changed this row first. The write did NOT happen."""


class NoReason(Exception):
    """A curation write with no stated reason."""


@dataclass(frozen=True)
class Actor:
    user_id: str
    email: str
    role: str
    shared_account: bool = False


def _require_admin(actor: Actor) -> None:
    if actor.role != "admin":
        raise NotPermitted(
            f"{actor.email} holds {actor.role!r}; curation writes are admin only")
    if actor.shared_account:
        # Belt and braces: the database constraint already prevents a listed
        # shared account holding admin, so reaching this means the list changed
        # after the profile was created.
        raise NotPermitted(
            f"{actor.email} is a shared account; a curation change must be "
            "attributable to a person")


def _row(cur, table: str, key_col: str, key: str) -> dict | None:
    cur.execute(f"select * from {table} where {key_col} = %s", (key,))
    if cur.description is None:
        return None
    cols = [d[0] for d in cur.description]
    rec = cur.fetchone()
    return dict(zip(cols, rec)) if rec else None


def _jsonable(value):
    import datetime as _dt
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    if isinstance(value, (_dt.date, _dt.datetime)):
        return value.isoformat()
    return value


def update_row(conn, actor: Actor, table: str, key: str, changes: dict,
               expected_version: int, reason: str) -> dict:
    """Update one curation row. Raises StaleVersion if someone got there first.

    `expected_version` is not optional and has no default. A default would let a
    caller omit it and silently get last-write-wins, which is the exact failure
    this function exists to prevent.
    """
    if table not in WRITABLE:
        raise NotPermitted(f"{table} is not a curation table")
    if not (reason or "").strip():
        raise NoReason("a curation write must state why")
    _require_admin(actor)

    key_col, allowed = WRITABLE[table]
    unknown = set(changes) - allowed
    if unknown:
        raise NotPermitted(f"cannot set {sorted(unknown)} on {table}")

    with conn.cursor() as cur:
        # The trigger refuses writes that do not come through here.
        cur.execute("select set_config('np.writing_through_service','on',true)")

        before = _row(cur, table, key_col, key)
        if before is None:
            raise StaleVersion(f"{table}.{key} does not exist")

        sets = ", ".join(f"{c} = %s" for c in changes)
        params = list(changes.values()) + [key, expected_version]
        cur.execute(
            f"update {table} set {sets} where {key_col} = %s and version = %s",
            params)
        if cur.rowcount == 0:
            # Distinguish "gone" from "changed under us" — they need different
            # responses from a human, and "0 rows" alone says neither.
            current = _row(cur, table, key_col, key)
            raise StaleVersion(
                f"{table}.{key} is at version "
                f"{current['version'] if current else 'DELETED'}, not "
                f"{expected_version}. Someone changed it first and YOUR WRITE "
                "DID NOT HAPPEN. Re-read the row, decide again, retry.")

        after = _row(cur, table, key_col, key)
        cur.execute(
            "insert into curation_audit(actor_user_id, actor_email, "
            "shared_account, table_name, row_key, action, before_value, "
            "after_value, reason) values (%s,%s,%s,%s,%s,'update',%s,%s,%s)",
            (actor.user_id, actor.email, actor.shared_account, table, key,
             json.dumps(_jsonable(before)), json.dumps(_jsonable(after)),
             reason.strip()))
    return after


def history(conn, table: str, key: str, limit: int = 50) -> list[dict]:
    """What happened to one row, and why. Admin only, by RLS on curation_audit."""
    with conn.cursor() as cur:
        cur.execute(
            "select at, actor_email, action, before_value, after_value, reason "
            "from curation_audit where table_name = %s and row_key = %s "
            "order by at desc limit %s", (table, key, limit))
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]


# --------------------------------------------------------------------------
# the alias surface — F3
# --------------------------------------------------------------------------

def ambiguous_aliases(conn) -> list[dict]:
    """Aliases awaiting a human decision, with the evidence for each candidate.

    Returns everything a person needs to decide and NOTHING that decides for
    them. In particular there is no "recommended" or "best" field, and the
    candidates are returned in the order the corpus owner recorded them rather
    than ranked: `lib/resolve.py` returns Ambiguous rather than picking, and a UI
    that ranks candidates reintroduces the picking one layer up.
    """
    with conn.cursor() as cur:
        cur.execute("""
            select alias, domain, claims, sibling_test, confirmed, note, props,
                   version
            from domain_aliases
            where confirmed = false and domain is null
            order by claims desc nulls last, alias
        """)
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        for row in rows:
            cands = (row.get("props") or {}).get("candidates") or []
            row["candidates"] = [_candidate_evidence(cur, row["alias"], c)
                                 for c in cands]
            row["no_candidates_note"] = (
                "No domain carries this name. It may be a product that predates "
                "or postdates the owner sheet — a decision about the TAXONOMY, "
                "not about this alias." if not cands else None)
    return rows


def _candidate_evidence(cur, alias: str, candidate: str) -> dict:
    """What is true about one candidate target, measured rather than asserted.

    Every figure here answers a question a person asked in review:
      corroborating  — do the people who wrote this alias ALSO already point at
                       this candidate by another route? This is the only signal
                       in the data, and for two of the three aliases it is zero.
      taught_modules — is this domain one we actually deliver, or a name on a
                       sheet? A candidate with no teaching evidence is a
                       different kind of answer.
      existing_edges — how many expert_in edges the candidate already carries,
                       so the decision's blast radius is visible before it is
                       taken.
    """
    cur.execute("select id from nodes where type = 'domain' and label = %s",
                (candidate,))
    row = cur.fetchone()
    if not row:
        return {"domain": candidate, "exists": False}
    dom_id = row[0]

    # CORROBORATION IS NOT COMPUTABLE HERE, and saying so is the point.
    #
    # The useful question is "do the people who wrote this alias ALSO already
    # point at this candidate by another route?". Answering it needs the
    # UNJOINED expertise claims — 1,577 of them across 882 people — and those
    # are precisely what produced no edges, which is why the alias is unresolved
    # at all. They live in knowledge/candidates.json and are not projected.
    #
    # A field that always reads 0 because the data is absent is worse than no
    # field: it reads as "no corroboration exists" when it means "we did not
    # look". Measured offline, the real answer is uneven — roughly half the ML
    # claimants also wrote "Machine Learning", and for Agentic AI the figure is
    # zero out of 64. Projecting the claims is a small, separate change.
    cur.execute("select count(*) from edges where rel = %s and target_id = %s",
                (_tax.edge_for_role("instructor_domain"), dom_id))
    existing = cur.fetchone()[0]

    cur.execute("""
        select count(distinct m.id)
        from edges cv
        join edges ct on ct.source_id = cv.source_id and ct.rel = 'contains'
        join nodes m on m.id = ct.target_id
        where cv.rel = 'covers' and cv.target_id = %s
          and exists (select 1 from edges t where t.rel='teaches' and t.target_id=m.id)
    """, (dom_id,))
    taught = cur.fetchone()[0]

    return {
        "domain": candidate,
        "exists": True,
        "existing_expert_in_edges": existing,
        "taught_modules": taught,
        "corroboration": {
            "available": False,
            "why": ("needs the unjoined expertise claims, which are not "
                    "projected. Measured offline they are uneven: ~half the ML "
                    "claimants also declared 'Machine Learning', while 0 of 64 "
                    "Agentic AI claimants carry any signal at all."),
        },
    }
