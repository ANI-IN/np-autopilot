"""M7 — concurrency, through the service layer on separate real connections
(the same code path the HTTP routes and the MCP server use).

  * two sessions edit the same record from the same version → exactly one
    wins, the other gets Conflict (409) with the winner's record;
  * 20 parallel creates, including 5 racing on one name → no duplicates, no
    orphans, and exactly one audit insert per created row;
  * 20 parallel edge creates while the shared endpoint is archived → every
    edge either refused or archived with it, never live and orphaned.

Timings are printed for docs/TEST_RESULTS.md.
"""
from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from kb_support import USERS, as_user, ensure_users, owner, requires_kb, reset

pytestmark = requires_kb

from lib.kb import service as svc                                     # noqa: E402
from lib.kb.errors import Conflict, Duplicate, KbError                 # noqa: E402


@pytest.fixture(autouse=True)
def _setup():
    ensure_users()
    reset()
    yield
    reset()


def _run(role, fn):
    """One transaction as `role`; commit on success, roll back on KbError."""
    with as_user(USERS[role]) as conn:
        actor = svc.Actor(USERS[role])
        svc.begin(conn, actor)
        try:
            out = fn(conn, actor)
        except KbError as exc:
            conn.rollback()
            return exc
        conn.commit()
        return out


def test_two_editors_same_record_exactly_one_wins():
    node = _run("editor", lambda c, a: svc.create_node(c, a, {"type": "topic", "name": "Race"}))
    barrier = threading.Barrier(2)

    def edit(role, text):
        def fn(c, a):
            barrier.wait()
            return svc.update_node(c, a, str(node["id"]), {"version": 1, "summary": text})
        return _run(role, fn)

    with ThreadPoolExecutor(2) as ex:
        results = list(ex.map(lambda args: edit(*args), [("editor", "A"), ("contributor", "B")]))
    wins = [r for r in results if isinstance(r, dict)]
    losses = [r for r in results if isinstance(r, Conflict)]
    assert len(wins) == 1 and len(losses) == 1, results
    assert losses[0].details["current"]["summary"] == wins[0]["summary"]
    assert losses[0].details["current"]["version"] == 2
    with owner() as c:
        assert c.execute("select version, summary from kb.nodes where id=%s", (node["id"],)).fetchone() \
            == (2, wins[0]["summary"])


def test_twenty_parallel_creates_no_duplicates_no_orphans_audit_matches():
    course = _run("editor", lambda c, a: svc.create_node(c, a, {"type": "course", "name": "Parallel Course"}))
    names = [f"Module {i}" for i in range(15)] + ["Same Name"] * 5
    barrier = threading.Barrier(len(names))

    def create(name):
        def fn(c, a):
            barrier.wait()
            n = svc.create_node(c, a, {"type": "module", "name": name, "scope": str(course["id"])})
            svc.create_edge(c, a, {"type": "contains", "source_id": str(course["id"]), "target_id": str(n["id"])})
            return n
        return _run("contributor", fn)

    t0 = time.perf_counter()
    with ThreadPoolExecutor(len(names)) as ex:
        results = list(ex.map(create, names))
    elapsed = time.perf_counter() - t0
    created = [r for r in results if isinstance(r, dict)]
    dupes = [r for r in results if isinstance(r, Duplicate)]
    others = [r for r in results if not isinstance(r, (dict, Duplicate))]
    print(f"\n[concurrency] 20 parallel create+connect: {len(created)} created, {len(dupes)} duplicate-refused, "
          f"{len(others)} other, {elapsed * 1000:.0f} ms total")
    assert not others, others
    assert len(created) == 16 and len(dupes) == 4
    with owner() as c:
        assert c.execute("select count(*) from kb.nodes where type_id = (select id from kb.node_types where key='module') "
                         "and name_norm = 'same name'").fetchone()[0] == 1
        live_modules = c.execute("select count(*) from kb.nodes where scope_id = %s", (course["id"],)).fetchone()[0]
        edges = c.execute("select count(*) from kb.edges where source_id = %s", (course["id"],)).fetchone()[0]
        assert live_modules == 16 and edges == 16, "every created module has exactly its edge: no orphans, no partials"
        audits = c.execute("select count(*) from kb.audit_log where table_name='nodes' and action='insert'").fetchone()[0]
        assert audits == 17                                        # 16 modules + the course
        audit_edges = c.execute("select count(*) from kb.audit_log where table_name='edges' and action='insert'").fetchone()[0]
        assert audit_edges == 16


def test_parallel_edge_creates_racing_an_archive_leave_no_orphans():
    hub = _run("editor", lambda c, a: svc.create_node(c, a, {"type": "topic", "name": "Hub"}))
    leaves = [_run("editor", lambda c, a, i=i: svc.create_node(c, a, {"type": "topic", "name": f"Leaf {i}"}))
              for i in range(20)]
    barrier = threading.Barrier(21)

    def connect(leaf):
        def fn(c, a):
            barrier.wait()
            return svc.create_edge(c, a, {"type": "related", "source_id": str(leaf["id"]), "target_id": str(hub["id"])})
        return _run("contributor", fn)

    def archive():
        def fn(c, a):
            barrier.wait()
            return svc.archive_node(c, a, str(hub["id"]))
        return _run("editor", fn)

    with ThreadPoolExecutor(21) as ex:
        futs = [ex.submit(connect, leaf) for leaf in leaves] + [ex.submit(archive)]
        results = [f.result() for f in futs]
    assert isinstance(results[-1], dict) and results[-1]["node"]["archived_at"]
    with owner() as c:
        orphans = c.execute("""select count(*) from kb.edges e join kb.nodes n on n.id in (e.source_id, e.target_id)
                               where e.archived_at is null and n.archived_at is not null""").fetchone()[0]
    assert orphans == 0
