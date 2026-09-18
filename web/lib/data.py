"""Request-scoped database access for the web app.

THE ONE RULE: every request runs as `authenticated` with the caller's JWT
claims set. Never as `postgres`, never as `service_role`.

That is what makes layer 4 safe to be last. DECISIONS §D says middleware is
defence in depth only, and doc 03's silent-failure lesson applies here too: the
documented failure mode of route protection is a matcher that quietly stops
matching. If an unguarded route reaches this module, it arrives with no
identity, `auth.uid()` is null, `np_role()` returns 'none', and RLS returns zero
rows. The route leaks nothing — it just answers "nothing found".

If instead this module connected as the owner, an unguarded route would return
the entire graph and the middleware would be the only thing that had ever been
protecting it.

Transaction pooler (6543) with `prepare_threshold=None`, per DECISIONS §C.1:
transaction-mode pooling cannot hold prepared statements across statements, and
psycopg3 prepares after five executions — the single most common
works-locally-fails-on-Vercel cause.
"""
from __future__ import annotations

import json
import os
import sys
from contextlib import contextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pipeline.lib import db as _db                                    # noqa: E402
from pipeline.lib import taxonomy as _tax                              # noqa: E402

#: Depth cap for neighbourhood expansion. Fails LOUDLY rather than truncating:
#: a silently truncated neighbourhood looks like a sparse graph, and this
#: project's recurring failure is concluding "not in the corpus" from a gap in
#: the tooling.
MAX_DEPTH = 3


class NotAuthenticated(Exception):
    """No verified identity reached the data layer."""


class DepthExceeded(Exception):
    """Asked for a traversal deeper than the cap."""


@contextmanager
def request_connection(identity_subject: str | None):
    """A connection scoped to one caller, for one request.

    `identity_subject` is the `sub` of a token that web/lib/auth.py already
    verified. Passing None is allowed and yields a connection that can see
    nothing — that is the unguarded-route case, and it must be harmless rather
    than impossible, because "impossible" would be an exception a route could
    catch and work around.
    """
    conn = _db.connect(_db.TRANSACTION)
    try:
        with conn.cursor() as cur:
            claims = {"role": "authenticated"}
            if identity_subject:
                claims["sub"] = str(identity_subject)
            cur.execute("select set_config('request.jwt.claims', %s, true)",
                        (json.dumps(claims),))
            cur.execute('set local role "authenticated"')
        yield conn
    finally:
        conn.rollback()
        conn.close()


def _rows(cur) -> list[dict]:
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


# --------------------------------------------------------------------------
# read paths
# --------------------------------------------------------------------------

def search(conn, query: str, types: list[str] | None = None,
           limit: int = 50) -> list[dict]:
    """Label search. Paginated by construction — never ships the whole graph."""
    limit = max(1, min(int(limit), 200))
    sql = ["select id, type, label from nodes where label ilike %s"]
    args: list = [f"%{query}%"]
    if types:
        sql.append("and type = any(%s)")
        args.append(list(types))
    sql.append("order by length(label), label limit %s")
    args.append(limit)
    with conn.cursor() as cur:
        cur.execute(" ".join(sql), args)
        return _rows(cur)


def node(conn, node_id: str) -> dict | None:
    with conn.cursor() as cur:
        cur.execute("select id, type, label, label_raw, sensitive, props "
                    "from nodes where id = %s", (node_id,))
        rows = _rows(cur)
    return rows[0] if rows else None


def neighbourhood(conn, node_id: str, depth: int = 1,
                  rels: list[str] | None = None, limit: int = 300) -> dict:
    """Expand around one node, EXCLUDING provenance structurally.

    Provenance is not in `edges` at all — it lives in `node_sources` — so the
    degree-18,134 file hubs cannot be walked through by accident. That is the
    §A.3 argument paying off: the dangerous join is not merely discouraged, it
    is unwriteable here.
    """
    depth = int(depth)
    if depth < 1 or depth > MAX_DEPTH:
        raise DepthExceeded(
            f"depth {depth} is outside 1..{MAX_DEPTH}. The cap is deliberate: "
            "silently truncating a neighbourhood makes a tooling limit look "
            "like a sparse graph.")
    limit = max(1, min(int(limit), 1000))
    sql = """
        with recursive walk(id, depth) as (
            select %s::text, 0
            union
            select case when e.source_id = w.id then e.target_id
                        else e.source_id end, w.depth + 1
            from walk w
            join edges e on (e.source_id = w.id or e.target_id = w.id)
            where w.depth < %s
              and (%s::text[] is null or e.rel = any(%s::text[]))
        )
        select n.id, n.type, n.label, min(w.depth) as depth
        from walk w join nodes n on n.id = w.id
        group by n.id, n.type, n.label
        order by depth, n.label
        limit %s
    """
    with conn.cursor() as cur:
        cur.execute(sql, (node_id, depth, rels, rels, limit))
        nodes = _rows(cur)
        ids = [n["id"] for n in nodes]
        cur.execute(
            "select rel, source_id, target_id, props from edges "
            "where source_id = any(%s) and target_id = any(%s)", (ids, ids))
        edges = _rows(cur)
    return {"nodes": nodes, "edges": edges,
            "truncated": len(nodes) >= limit, "depth": depth}


#: The default view, resolved from the taxonomy BY ROLE rather than by name.
#: `taxonomy.yaml` is the single source of truth and a type string written as a
#: literal here would quietly become a second one — CLAUDE.md, and the grep test
#: in tests/test_taxonomy_single_source.py, which caught exactly that in the
#: first draft of this code.
#:
#: The node type is DERIVED from the edges' own endpoints rather than asserted,
#: so renaming the type in taxonomy.yaml moves this view with it instead of
#: silently emptying it.
OVERVIEW_ROLES = ("domain_primary", "domain_delivery")


def _overview_spec() -> tuple[str, tuple[str, ...]]:
    rels = tuple(_tax.edge_for_role(r) for r in OVERVIEW_ROLES)
    sources = {_tax.edge_endpoints(r)[0] for r in rels}
    if len(sources) != 1:
        raise RuntimeError(
            f"the default view's roles {OVERVIEW_ROLES} now hang off "
            f"{sorted(sources)} rather than one node type. The landing view "
            "cannot be 'every X' when there is no single X — decide what it "
            "should be rather than letting it pick one.")
    return sources.pop(), rels


#: Deliberately module constants and NOT parameters — see overview().
OVERVIEW_TYPE, OVERVIEW_RELS = _overview_spec()

#: Which of those roles means "owns". Named, not indexed, so the unowned
#: calculation cannot silently follow a reordering of OVERVIEW_ROLES.
OWNER_ROLE = "domain_primary"

#: Cap on the default view. It returns 65 nodes today; this exists so that a
#: projection which unexpectedly grows cannot quietly turn the landing page
#: into a bulk download. Hitting it is REPORTED, never silently trimmed.
OVERVIEW_CAP = 400


def overview(conn) -> dict:
    """The landing view: every domain, and the people who own or deliver it.

    BOUNDED BY CONSTRUCTION, AND THAT IS THE ENTIRE POINT. It takes no
    parameters. The node type and the two relations are literals in this
    module, not values a caller supplies, so there is no query string that
    turns this into "give me an arbitrary subgraph".

    WHY THAT MATTERS, since the usual reason no longer applies. §A.3 moved
    provenance into `node_sources`, so the catastrophic join -- walking a
    degree-18,134 file hub -- is now unwriteable in this module rather than
    merely discouraged. That protects every query here. It does NOT protect a
    client that assembles its own graph from bulk downloads, because such a
    client walks whatever it happens to hold instead of asking SQL for it. The
    guarantee lives in the query layer; a bulk client routes around the query
    layer. So "never ship the whole graph" stands on that, not on payload size
    -- the whole public graph is 526 KiB, which would be fine -- and this
    endpoint is deliberately the shape that cannot grow into one.

    ISOLATED DOMAINS ARE RETURNED, not filtered. A domain with nobody against
    it is a finding -- 3 of 42 today -- and the landing view is exactly where it
    should be visible. The client ships with "show unconnected" ON for the same
    reason; see public/index.html.
    """
    with conn.cursor() as cur:
        cur.execute(
            "select rel, source_id, target_id, props from edges "
            "where rel = any(%s) and (source_id in "
            "  (select id from nodes where type = %s) or target_id in "
            "  (select id from nodes where type = %s))",
            (list(OVERVIEW_RELS), OVERVIEW_TYPE, OVERVIEW_TYPE))
        edges = _rows(cur)
        touched = ({e["source_id"] for e in edges}
                   | {e["target_id"] for e in edges})
        cur.execute(
            "select id, type, label, label_raw, props from nodes "
            "where type = %s or id = any(%s) "
            "order by type, label limit %s",
            (OVERVIEW_TYPE, list(touched), OVERVIEW_CAP + 1))
        nodes = _rows(cur)

    truncated = len(nodes) > OVERVIEW_CAP
    if truncated:
        nodes = nodes[:OVERVIEW_CAP]
    # An edge whose endpoint fell outside the cap would render as a line to
    # nowhere. Drop it here rather than letting the client hold a dangling ref.
    keep = {n["id"] for n in nodes}
    edges = [e for e in edges
             if e["source_id"] in keep and e["target_id"] in keep]

    # A DOMAIN WITH NO OWNER IS REPORTED EXPLICITLY, not left to be noticed.
    #
    # The original plan was to let these show up as isolated nodes. Measuring
    # the view killed that: 39 of 42 domains have an owner, but all 42 have a
    # deliverer, so once `delivered_by` is included NOTHING is isolated and the
    # gap becomes invisible -- three domains that look exactly like the other
    # 39 unless you count edges by relation. A finding that depends on a node
    # happening to have degree 0 is a finding waiting to disappear, which is
    # the §A.7b shape: the absence and the healthy case render identically.
    owner_rel = _tax.edge_for_role(OWNER_ROLE)
    owned = {e["source_id"] for e in edges if e["rel"] == owner_rel} | \
            {e["target_id"] for e in edges if e["rel"] == owner_rel}
    unowned = sorted(n["label"] for n in nodes
                     if n["type"] == OVERVIEW_TYPE and n["id"] not in owned)
    return {"nodes": nodes, "edges": edges, "truncated": truncated,
            "unowned": unowned,
            "unowned_note": (
                "domains with no owner recorded. Not an error and not an empty "
                "result: ownership is domain-level and blank is a real state. "
                "Surfaced because the default view is where it is cheapest to "
                "notice." ) if unowned else None}


def provenance(conn, node_id: str) -> dict:
    """Both source shapes, kept DISTINCT.

    The whole point of the §A.5 fix: a hand-entered fact must be visibly
    hand-entered. They are returned in separate lists rather than one list with
    a flag, because a flag is something a UI can forget to render.
    """
    with conn.cursor() as cur:
        cur.execute("""
            select origin, file, sheet, row_num, col_num, col_name, page,
                   within_cell, ordinal, prop, evidence, entered_at
            from node_sources where node_id = %s
            order by origin, file nulls last, row_num nulls last, ordinal
        """, (node_id,))
        rows = _rows(cur)
    corpus = [r for r in rows if r["origin"] == "corpus"]
    hand = [r for r in rows if r["origin"] == "hand"]
    return {
        "corpus": corpus,
        "hand": hand,
        "hand_note": (
            "Out-of-corpus evidence, entered by a person. NOT produced by a scan. "
            "`prop` names the property this entry justifies."
        ) if hand else None,
    }


def coverage(conn) -> dict:
    """SQL, per DECISIONS §C.2 — the one path that is strictly better as SQL.

    Whole-graph aggregate counting. In Python it needs the entire graph in
    memory; here it is a handful of LEFT JOIN ... IS NULL.
    """
    with conn.cursor() as cur:
        cur.execute("""
            with isolated as (
                -- Two NOT EXISTS rather than one with an OR. The OR form cannot
                -- use either directional index and measured 17ms against 4ms;
                -- combined with the other four it was 18.8ms against 5.6ms.
                -- (A first run measured 1.6s, which was cold buffers, not the
                -- plan — worth saying, because "optimising" on a cold number
                -- would have chased the wrong thing.)
                select id from nodes
                where type <> 'file'
                  and not exists (select 1 from edges e where e.source_id = nodes.id)
                  and not exists (select 1 from edges e where e.target_id = nodes.id)
            )
            select
              (select count(*) from nodes p where p.type='program' and not exists
                 (select 1 from edges e where e.rel='covers' and e.source_id=p.id))
                as programs_without_domain,
              (select count(*) from nodes m where m.type='module' and not exists
                 (select 1 from edges e where e.rel='contains' and e.target_id=m.id))
                as modules_without_program,
              (select count(*) from nodes m where m.type='module' and not exists
                 (select 1 from edges e where e.rel='teaches' and e.target_id=m.id))
                as modules_without_instructor,
              (select count(*) from nodes d where d.type='domain' and not exists
                 (select 1 from edges e where e.source_id=d.id
                    and e.rel in ('owned_by','supported_by','delivered_by')))
                as domains_without_owner,
              (select count(*) from isolated) as isolated_records
        """)
        row = _rows(cur)[0]
    row["workflow_ownership"] = (
        "OUT OF SCOPE — ownership in New Programs attaches to domains, not "
        "workflows. Never report 92 workflows as missing an owner.")
    row["counts_are_floors"] = (
        "person, instructor and module counts are floors over 127 of 374 "
        "worksheets, not totals.")
    return row


def domain_subgraph(conn, domain_label: str) -> dict:
    """Fetch what /staffing needs, and NOTHING more.

    The tiering itself stays in Python (§C.2): an ORDER BY expresses ranking but
    cannot express "these are different kinds of evidence and merging them is
    the worst failure this system can produce". So this returns raw rows and
    the caller partitions them.
    """
    with conn.cursor() as cur:
        cur.execute("select id, label, props from nodes "
                    "where type='domain' and lower(label)=lower(%s)",
                    (domain_label,))
        doms = _rows(cur)
        if not doms:
            return {"domain": None}
        dom = doms[0]
        cur.execute("""
            select i.id, i.label, e.props as edge_props, m.label as module
            from edges cv
            join edges ct on ct.source_id = cv.source_id and ct.rel = 'contains'
            join nodes m  on m.id = ct.target_id
            join edges e  on e.target_id = m.id and e.rel = 'teaches'
            join nodes i  on i.id = e.source_id
            where cv.rel = 'covers' and cv.target_id = %s
        """, (dom["id"],))
        taught = _rows(cur)
        cur.execute("""
            select i.id, i.label, e.props as edge_props
            from edges e join nodes i on i.id = e.source_id
            where e.rel = 'expert_in' and e.target_id = %s
        """, (dom["id"],))
        declared = _rows(cur)
    return {"domain": dom, "taught": taught, "declared": declared}
