"""E2 layer 4 and E3 read paths — including the unguarded-route case.

The required test from DECISIONS §D, both halves: a non-IK identity is rejected
AT THE API and, as that identity, returns zero rows AT THE DATABASE.

And the one doc 03 makes necessary: a route added without a matcher entry must
still be refused. The documented failure mode of route protection is a matcher
that quietly stops matching, so "we added the path to the config" is not a
safety property — what the unguarded route can reach is.
"""
from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "web"))

from pipeline.lib import db                                           # noqa: E402

pytestmark = pytest.mark.skipif(
    not db.available(),
    reason="no SUPABASE_DB_URL_SESSION / psycopg — database tests skipped")

from lib import data                                                  # noqa: E402

MEMBER = uuid.UUID("00000000-0000-4000-8000-00000000fb01")
OUTSIDER = uuid.UUID("00000000-0000-4000-8000-00000000fb02")


@pytest.fixture
def member_profile():
    with db.connect(db.SESSION) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "insert into profiles(user_id,email,email_domain,role) values "
                "(%s,'member@interviewkickstart.com','interviewkickstart.com',"
                "'member') on conflict (user_id) do update set role='member'",
                (MEMBER,))
            conn.commit()
    yield MEMBER
    with db.connect(db.SESSION) as conn:
        with conn.cursor() as cur:
            cur.execute("delete from profiles where user_id = any(%s)",
                        ([MEMBER, OUTSIDER],))
            conn.commit()


# --------------------------------------------------------------------------
# the unguarded route
# --------------------------------------------------------------------------

def test_a_route_that_forgets_the_guard_returns_nothing(member_profile):
    """No identity reaches the data layer -> auth.uid() is null -> RLS denies.

    This is what makes middleware safe to be LAST. If this layer connected as
    the owner instead, an unguarded route would return the entire graph and
    middleware would be the only thing that had ever protected it.
    """
    with data.request_connection(None) as conn:
        assert data.search(conn, "a") == []
        assert data.node(conn, "dom_e2c96c28c6208a0e") is None
        nb = data.neighbourhood(conn, "dom_e2c96c28c6208a0e", depth=1)
        assert nb["nodes"] == [] and nb["edges"] == []
        assert data.provenance(conn, "dom_e2c96c28c6208a0e")["corpus"] == []
        cov = data.coverage(conn)
        assert all(v == 0 for k, v in cov.items() if isinstance(v, int))


def test_an_identity_with_no_profile_returns_nothing(member_profile):
    """The non-IK case at the DATABASE: signed in, but not provisioned."""
    with data.request_connection(str(OUTSIDER)) as conn:
        assert data.search(conn, "a") == []
        assert data.coverage(conn)["programs_without_domain"] == 0


def test_the_request_connection_never_runs_as_owner(member_profile):
    with data.request_connection(str(MEMBER)) as conn, conn.cursor() as cur:
        cur.execute("select current_user")
        assert cur.fetchone()[0] == "authenticated"


def test_the_transaction_pooler_is_used_with_prepares_disabled():
    """Works-locally-fails-on-Vercel, prevented in the connection itself."""
    import inspect
    src = inspect.getsource(data.request_connection)
    assert "_db.TRANSACTION" in src
    assert "prepare_threshold" in inspect.getsource(db.connect)


# --------------------------------------------------------------------------
# a provisioned member gets real answers
# --------------------------------------------------------------------------

def test_a_member_can_search_and_read(member_profile):
    with data.request_connection(str(MEMBER)) as conn:
        hits = data.search(conn, "Backend", limit=10)
        assert hits, "member sees nothing"
        assert all("id" in h and "label" in h for h in hits)
        n = data.node(conn, hits[0]["id"])
        assert n and n["sensitive"] is False


def test_search_is_bounded(member_profile):
    """Never ship 5,048 nodes to a browser."""
    with data.request_connection(str(MEMBER)) as conn:
        assert len(data.search(conn, "a", limit=10)) <= 10
        assert len(data.search(conn, "a", limit=99999)) <= 200


def test_neighbourhood_depth_cap_fails_loudly(member_profile):
    """Truncating silently makes a tooling limit look like a sparse graph."""
    with data.request_connection(str(MEMBER)) as conn:
        with pytest.raises(data.DepthExceeded):
            data.neighbourhood(conn, "dom_e2c96c28c6208a0e", depth=data.MAX_DEPTH + 1)
        with pytest.raises(data.DepthExceeded):
            data.neighbourhood(conn, "dom_e2c96c28c6208a0e", depth=0)
        ok = data.neighbourhood(conn, "dom_e2c96c28c6208a0e", depth=1)
        assert ok["depth"] == 1


def test_traversal_cannot_walk_through_provenance(member_profile):
    """Structural, not a WHERE clause someone can forget.

    sourced_from is not in `edges` at all — it lives in node_sources — so the
    degree-18,134 file hubs are unreachable from a traversal.
    """
    from pipeline.lib import taxonomy
    prov = taxonomy.edge_for_role("provenance")
    with data.request_connection(str(MEMBER)) as conn, conn.cursor() as cur:
        cur.execute("select count(*) from edges where rel = %s", (prov,))
        assert cur.fetchone()[0] == 0, (
            "provenance edges are in `edges`; a traversal can now walk a file hub"
        )
        cur.execute("select count(*) from node_sources")
        assert cur.fetchone()[0] > 30000, "provenance is missing entirely"


def test_provenance_keeps_the_two_shapes_distinct(member_profile):
    """A hand-entered fact must be VISIBLY hand-entered — the §A.5 fix's point."""
    with data.request_connection(str(MEMBER)) as conn, conn.cursor() as cur:
        cur.execute("select node_id from node_sources where origin='hand' limit 1")
        row = cur.fetchone()
        assert row, "no hand provenance in the database"
        node_id = row[0]
    with data.request_connection(str(MEMBER)) as conn:
        p = data.provenance(conn, node_id)
    assert p["hand"], "hand provenance did not come back"
    assert p["hand_note"] and "NOT produced by a scan" in p["hand_note"]
    assert all(h["prop"] for h in p["hand"]), "a hand entry names no property"
    assert all(c["file"] for c in p["corpus"]), "a corpus entry names no file"


def test_coverage_never_reports_workflow_ownership_as_a_gap(member_profile):
    with data.request_connection(str(MEMBER)) as conn:
        cov = data.coverage(conn)
    assert "OUT OF SCOPE" in cov["workflow_ownership"]
    assert "floors" in cov["counts_are_floors"]


def test_staffing_subgraph_returns_tiers_unmerged(member_profile):
    """The fetch returns RAW rows; the tiering stays in Python (§C.2).

    If this ever returned a single ranked list, an ORDER BY would have collapsed
    evidence classes that must never merge.
    """
    with data.request_connection(str(MEMBER)) as conn:
        sub = data.domain_subgraph(conn, "Backend")
    assert sub["domain"], "Backend not found"
    assert "taught" in sub and "declared" in sub
    taught_names = {r["label"] for r in sub["taught"]}
    declared_names = {r["label"] for r in sub["declared"]}
    assert taught_names, "no teaching evidence for Backend"
    # The caller must be able to tell them apart; overlap is fine in the raw
    # fetch, and query.py is what removes a taught name from the declared tier.
    assert isinstance(taught_names, set) and isinstance(declared_names, set)


# ---------------------------------------------------------------------------
# The default view (STATE §8.2). These guard a DESIGN decision, not a number.
# ---------------------------------------------------------------------------

def test_the_default_view_cannot_be_widened_by_a_caller():
    """The whole reason /api/overview is safe, asserted rather than trusted.

    §A.3 moved provenance out of `edges`, so the catastrophic join is now
    unwriteable server-side. That protects every query in data.py. It does NOT
    protect a client that downloads a graph in bulk, because such a client walks
    what it holds instead of asking SQL — it routes around the query layer
    entirely. So the rule "never ship the whole graph" survives on THAT, and the
    property that keeps this endpoint on the right side of it is that **it takes
    no parameters**: the node type and the relations are module constants.

    A future edit that reads a type or a rel off the query string turns the
    landing page into a general subgraph endpoint, which is the exact shape the
    rule forbids — and it would do so while every other test still passed.
    """
    import inspect

    params = list(inspect.signature(data.overview).parameters)
    assert params == ["conn"], (
        f"data.overview now takes {params}. If a caller can choose what it "
        "returns, it is a general subgraph endpoint wearing a landing page's "
        "name. Keep the type and relations as module constants."
    )
    assert isinstance(data.OVERVIEW_RELS, tuple), \
        "OVERVIEW_RELS must be an immutable module constant"
    assert data.OVERVIEW_TYPE == "domain"


def test_the_default_view_route_ignores_the_query_string(member_profile):
    """Same rule, at the route rather than the function.

    Passing a hostile query string must change nothing. A route that quietly
    honoured `?type=` or `?rels=` would widen the endpoint without touching
    data.py, so the constant-signature test above would still be green.
    """
    sys.path.insert(0, str(REPO / "api"))
    import overview as overview_route

    with data.request_connection(str(MEMBER)) as conn:
        plain, n_plain = overview_route._overview(conn, None, {})
        hostile, n_hostile = overview_route._overview(conn, None, {
            "type": "instructor", "rels": "teaches,expert_in,sourced_from",
            "limit": "99999", "depth": "3", "id": "dom_e2c96c28c6208a0e",
        })
    assert n_plain == n_hostile
    assert [n["id"] for n in plain["nodes"]] == [n["id"] for n in hostile["nodes"]]
    assert {e["rel"] for e in hostile["edges"]} <= set(data.OVERVIEW_RELS), \
        "the query string widened the relation set"


def test_the_default_view_returns_every_domain_and_stays_small(member_profile):
    """Positive control, and the size claim the choice rests on."""
    with data.request_connection(str(MEMBER)) as conn:
        out = data.overview(conn)
        with conn.cursor() as cur:
            cur.execute("select count(*) from nodes where type = 'domain'")
            total = cur.fetchone()[0]

    domains = [n for n in out["nodes"] if n["type"] == "domain"]
    assert len(domains) == total, "the landing view is missing domains"
    assert out["truncated"] is False
    # Well inside the client's nodeBudget of 1,200 — the constraint the largest
    # connected component (1,881 nodes) fails.
    assert len(out["nodes"]) <= 200, (
        f"the default view grew to {len(out['nodes'])} nodes. It is the landing "
        "page; if the projection changed shape, decide that deliberately."
    )


def test_the_default_view_reports_domains_with_no_owner(member_profile):
    """A domain with no owner is a FINDING and must be named, not inferred.

    It was going to be left to show up as an isolated node. Measuring killed
    that: every domain has a deliverer, so once `delivered_by` is included
    nothing is isolated and the gap renders identically to a healthy domain.
    That is the §A.7b shape — absence and success looking the same — so the
    count is derived from the edges here instead.
    """
    with data.request_connection(str(MEMBER)) as conn:
        out = data.overview(conn)

    from pipeline.lib import taxonomy
    owner_rel = taxonomy.edge_for_role("domain_primary")
    owned = {e["source_id"] for e in out["edges"] if e["rel"] == owner_rel} | \
            {e["target_id"] for e in out["edges"] if e["rel"] == owner_rel}
    expected = sorted(n["label"] for n in out["nodes"]
                      if n["type"] == "domain" and n["id"] not in owned)
    assert out["unowned"] == expected, \
        "`unowned` disagrees with the edges it is supposed to be derived from"
    # Negative control: derived, not hardcoded. If every domain had an owner the
    # note must be absent rather than a stale string.
    assert (out["unowned_note"] is None) == (not out["unowned"])


def test_the_default_view_carries_no_provenance(member_profile):
    """Claim 1, asserted at the endpoint a bulk client would grow out of."""
    from pipeline.lib import taxonomy
    prov = taxonomy.edge_for_role("provenance")
    with data.request_connection(str(MEMBER)) as conn:
        out = data.overview(conn)
    assert all(e["rel"] != prov for e in out["edges"])
    assert all(e["rel"] in data.OVERVIEW_RELS for e in out["edges"])
