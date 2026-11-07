"""Performance budgets (Phase 1, 2026-11-07). A regression fails the build:

- the number of SQL statements each main workspace route runs (every statement
  is a round trip to the database; the dashboard once ran 34 and the Data quality
  page fetched the whole dashboard beside its own data);
- large /api/kb responses are compressed and written as compact JSON;
- the workspace's first page loads within a time budget, and only the modules it
  needs: a view's module is fetched when its page opens, never at startup.

Budgets carry headroom over today's counts; raise one only with a reason.
"""
from __future__ import annotations

import json
import time

import pytest

from kb_support import USERS, Client, as_user, ensure_users, requires_kb, reset, token_for

pytestmark = [requires_kb]

#: route -> statements allowed (today's count in the comment, measured 2026-11-07)
BUDGET = {
    ("dashboard",): 30,     # 25
    ("counts",): 8,         # 6
    ("quality",): 26,       # 20 (it now carries the dashboard's attention lists too)
    ("changes",): 3,        # 2: polled every 2.5 s by every open tab
    ("me",): 4,             # 3
    ("types",): 9,          # 7
    ("nodes",): 6,          # 3
}


@pytest.fixture(scope="module", autouse=True)
def _data():
    ensure_users(); reset()
    ed = Client(USERS["editor"])
    _, c = ed.post("/api/kb/courses", {"name": "Budget Course"})
    for i in range(5):
        ed.post("/api/kb/nodes", {"type": "module", "name": f"Budget Module {i}", "parents": [c["id"]]})
    yield
    reset()


def _count(route: tuple[str, ...], role: str = "admin") -> int:
    import kb_routes
    import psycopg
    n = [0]
    orig = psycopg.Cursor.execute

    def counting(self, *a, **k):
        n[0] += 1
        return orig(self, *a, **k)
    with as_user(USERS[role]) as conn:
        try:
            psycopg.Cursor.execute = counting
            kb_routes.handle(conn, kb_routes.svc.Actor(USERS[role]), "GET", list(route), {}, None)
        finally:
            psycopg.Cursor.execute = orig
            conn.rollback()
    return n[0]


@pytest.mark.parametrize("route", list(BUDGET), ids=lambda r: "/".join(r))
def test_statements_per_route_stay_within_budget(route):
    import kb_routes
    kb_routes._CACHE.clear()                      # count the real work, not a cache hit
    got = _count(route)
    assert got <= BUDGET[route], f"GET /api/kb/{'/'.join(route)} ran {got} SQL statements, budget {BUDGET[route]}"


def test_the_quality_page_needs_one_request():
    src = open(__import__("pathlib").Path(__file__).resolve().parent.parent / "public" / "kb" / "js" / "views" / "quality.js",
               encoding="utf-8").read()
    assert "api('GET', '/dashboard')" not in src, "the Data quality page fetches the whole dashboard again"
    _, q = Client(USERS["viewer"]).get("/api/kb/quality")
    assert "attention" in q and "completeness" in q


def test_large_kb_responses_are_compressed_and_compact():
    import index
    raw_big = {"items": [{"name": f"record {i}", "summary": "x" * 40} for i in range(200)]}
    out = []
    body = b"".join(index._respond(lambda s, h: out.append(dict(h)), 200, raw_big, no_store=True, accept_encoding="gzip, br"))
    assert out[0].get("content-encoding") in ("br", "gzip"), out[0]
    assert len(body) < len(json.dumps(raw_big)) / 5
    small = []
    body = b"".join(index._respond(lambda s, h: small.append(dict(h)), 200, {"ok": True}, no_store=True, accept_encoding="br"))
    assert "content-encoding" not in small[0] and body == b'{"ok":true}', "a tiny body is sent as it is, compact"
    src = open(__import__("inspect").getsourcefile(index._serve_kb), encoding="utf-8").read()
    fn = src[src.index("def _serve_kb"):]
    fn = fn[:fn.index("\nclass ")]
    assert "accept_encoding=" in fn, "/api/kb responses must be offered compression"


def test_the_first_page_loads_within_budget_and_views_load_lazily():
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright
    from kb_support import dev_server
    with dev_server() as base, sync_playwright() as p:
        try:
            b = p.chromium.launch(channel="chrome", headless=True)
        except Exception:                                              # noqa: BLE001
            b = p.chromium.launch(headless=True)
        ctx = b.new_context(viewport={"width": 1440, "height": 900})
        sess = json.dumps({"access_token": token_for(USERS["admin"], ttl=3600), "expires_at": int(time.time()) + 3600,
                           "user": {"email": "kbtest-admin@interviewkickstart.com"}})
        ctx.add_init_script(f"localStorage.setItem('np_session', {json.dumps(sess)});")
        page = ctx.new_page()
        modules = []
        page.on("request", lambda r: "/kb/js/" in r.url and modules.append(r.url.split("/kb/js/")[1]))
        page.goto(base + "/kb/")                                   # warm the server and the browser cache
        page.wait_for_selector("[data-testid=dash-grid]", timeout=30000)
        modules.clear()
        t0 = time.monotonic()
        page.reload()
        page.wait_for_selector("[data-testid=dash-grid]", timeout=30000)
        ms = (time.monotonic() - t0) * 1000
        assert ms < 3000, f"the dashboard took {ms:.0f} ms to load locally (budget 3000)"
        # the dashboard (Home), activity.js (the record panel's History uses its sentences) and search.js (Home's search box)
        lazy = [m for m in modules if m.startswith("views/") and m not in ("views/dashboard.js", "views/activity.js", "views/search.js")]
        assert not lazy, f"views loaded at startup instead of on first use: {lazy}"
        assert "views/graph.js" not in modules
        page.click("[data-nav=graph]")
        page.wait_for_function("() => window.__kbGraph && window.__kbGraph.loadedAt", timeout=30000)
        assert "views/graph.js" in modules, "the Graph page's module loads when the page opens"
        b.close()
