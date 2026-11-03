"""Run 6 (B1): the CHANGE-PROPAGATION MATRIX in a real browser — the acceptance
test for "every admin change appears everywhere".

ONE browser (headless Chromium), two pages, both signed in as a viewer:
  - the knowledge base Graph page, opened on a course (two steps deep);
  - the NP Autopilot map at "/".
An admin then performs every write path in the brief through the API (the
import and the sync as themselves). For each one this measures, from the moment
the write returns, how long each page takes to show it WITHOUT a reload, and
fails above 5 seconds. Neither page has Supabase Realtime here (the local
server has none): this is the polling fallback, the slower path.

The table is printed and written to docs/run6/MATRIX.md.

Browser runs are ONE AT A TIME across the run-6 agents: take the lock first
(`mkdir .run6/browser.lock` in the main checkout), remove it after.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from kb_support import USERS, Client, as_user, dev_server, ensure_users, owner, requires_kb, reset, token_for

pytest.importorskip("playwright.sync_api", reason="kb e2e: needs the playwright package")
from playwright.sync_api import sync_playwright                         # noqa: E402

pytestmark = [requires_kb]
REPO = Path(__file__).resolve().parent.parent
LIMIT = 5.0
ROWS: list[dict] = []


@pytest.fixture(scope="module")
def server():
    with dev_server() as base:
        yield base


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        yield b
        b.close()


def _drop_custom():
    with owner() as c:
        c.execute("truncate kb.flags, kb.templates, kb.saved_views, kb.graph_positions, kb.person_accounts, kb.sync_map, kb.sync_runs, kb.legacy_archive")
        c.execute("delete from kb.proposals where action = 'type_change'")
        c.execute("delete from kb.node_types where not is_core")
        c.execute("delete from kb.edge_types where not is_core")


def _page(browser, url, role="viewer"):
    ctx = browser.new_context(viewport={"width": 1400, "height": 900})
    sess = json.dumps({"access_token": token_for(USERS[role], ttl=3600), "expires_at": int(time.time()) + 3600,
                       "user": {"email": f"kbtest-{role}@interviewkickstart.com"}})
    ctx.add_init_script(f"localStorage.setItem('np_session', {json.dumps(sess)});")
    page = ctx.new_page()
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    page.on("console", lambda m: m.type == "error" and page.errors.append(m.text))
    page.goto(url)
    return ctx, page


def _until(pages_conds: dict, t0: float, limit: float = LIMIT + 1.0) -> dict:
    """Poll each page's condition (JS returning true) until all hold; the
    seconds from t0 to the first time each held (None if never)."""
    got = {k: None for k in pages_conds}
    while time.monotonic() - t0 < limit and any(v is None for v in got.values()):
        for k, (page, js) in pages_conds.items():
            if got[k] is None:
                try:
                    if page.evaluate(js):
                        got[k] = round(time.monotonic() - t0, 2)
                except Exception:                                      # noqa: BLE001 - mid-update DOM
                    pass
        time.sleep(0.1)
    return got


def _graph_has(nid):
    return f"(() => {{ const g = window.__kbGraph; const n = g && g.cy.getElementById('{nid}'); return !!(n && n.length && !n.hasClass('hidden')); }})()"


def _graph_lacks(nid):
    return f"(() => {{ const g = window.__kbGraph; return !!g && !g.cy.getElementById('{nid}').length; }})()"


def _map_node(nid, label=None):
    lab = f" && n.l === {json.dumps(label)}" if label else ""
    return f"(() => window.__NP.data.nodes.some((n) => n.id === '{nid}'{lab}))()"


def _map_lacks(nid):
    return f"(() => window.__NP_LIVE && window.__NP_LIVE.applied > 0 && !window.__NP.data.nodes.some((n) => n.id === '{nid}'))()"


def _map_edge(a, b, rel=None):
    r = f" && e.r === '{rel}'" if rel else ""
    return f"(() => window.__NP.data.edges.some((e) => ((e.s === '{a}' && e.t === '{b}') || (e.s === '{b}' && e.t === '{a}')){r}))()"


def _map_refetched(n):
    return f"(() => (window.__NP_LIVE && window.__NP_LIVE.applied) > {n})()"


def _graph_fed(n):
    return f"(() => (window.__kbGraph && window.__kbGraph.feed || 0) > {n})()"


def test_change_propagation_matrix(server, browser):
    ensure_users()
    reset()
    _drop_custom()
    admin = Client(USERS["admin"])
    ok = lambda r, code=(200, 201): (r[0] in code and r[1]) or pytest.fail(f"{r}")     # noqa: E731
    course = ok(admin.post("/api/kb/nodes", {"type": "course", "name": "Matrix Course"}))
    m1 = ok(admin.post("/api/kb/nodes", {"type": "module", "name": "Matrix Module", "parents": [course["id"]], "owner_id": None}))
    ins = ok(admin.post("/api/kb/nodes", {"type": "instructor", "name": "Matrix Teacher"}))
    ins2 = ok(admin.post("/api/kb/nodes", {"type": "instructor", "name": "Matrix Mentee"}))
    ins3 = ok(admin.post("/api/kb/nodes", {"type": "instructor", "name": "Matrix Guided"}))
    ok(admin.post("/api/kb/types/node", {"label": "Workshop", "allowed_parents": ["course"]}))
    ws = ok(admin.post("/api/kb/nodes", {"type": "workshop", "name": "Matrix Workshop", "parents": [course["id"]]}))
    contexts = []
    try:
        gctx, graph = _page(browser, server + f"/kb/#/graph/{course['id']}?depth=2")
        mctx, npmap = _page(browser, server + "/")
        contexts += [gctx, mctx]
        graph.wait_for_function(_graph_has(m1["id"]), timeout=20000)
        npmap.wait_for_function("window.__NP_LIVE && window.__NP_LIVE.cursor !== null && "
                                f"window.__NP.data.nodes.some((n) => n.id === '{m1['id']}')", timeout=30000)
        time.sleep(0.5)

        def step(op, kind, action, gjs, mjs, gnote="", mnote=""):
            gbase = graph.evaluate("window.__kbGraph.feed || 0")
            mbase = npmap.evaluate("window.__NP_LIVE.applied")
            t0 = time.monotonic()
            out = action()
            conds = {}
            if gjs:
                conds["graph"] = (graph, gjs(gbase) if callable(gjs) else gjs)
            if mjs:
                conds["map"] = (npmap, mjs(mbase) if callable(mjs) else mjs)
            got = _until(conds, t0)
            ROWS.append({"op": op, "kind": kind, "graph": got.get("graph"), "map": got.get("map"), "gnote": gnote, "mnote": mnote})
            return out

        # records
        new = step("record create (inside the course)", "record.create",
                   lambda: ok(admin.post("/api/kb/nodes", {"type": "module", "name": "Matrix New", "parents": [course["id"]]})),
                   None, None)
        ROWS.pop()
        t0 = time.monotonic()
        got = _until({"graph": (graph, _graph_has(new["id"])), "map": (npmap, _map_node(new["id"], "Matrix New"))}, t0)
        ROWS.append({"op": "record create (inside the course)", "kind": "record.create", "graph": got["graph"], "map": got["map"], "gnote": "", "mnote": ""})
        cur = ok(admin.get(f"/api/kb/nodes/{m1['id']}"))
        step("record update (rename)", "record.update",
             lambda: ok(admin.patch(f"/api/kb/nodes/{m1['id']}", {"version": cur["version"], "name": "Matrix Renamed"})),
             f"window.__kbGraph.cy.getElementById('{m1['id']}').data('label') === 'Matrix Renamed'", _map_node(m1["id"], "Matrix Renamed"))
        step("record archive", "record.archive", lambda: ok(admin.post(f"/api/kb/nodes/{new['id']}/archive")),
             _graph_lacks(new["id"]), _map_lacks(new["id"]))
        step("record restore", "record.restore", lambda: ok(admin.post(f"/api/kb/nodes/{new['id']}/restore")),
             _graph_has(new["id"]), _map_node(new["id"]))
        ok(admin.post(f"/api/kb/nodes/{new['id']}/archive"))
        time.sleep(3)
        step("record permanent delete (after archive)", "record.delete", lambda: ok(admin.delete(f"/api/kb/nodes/{new['id']}")),
             _graph_fed, _map_refetched, "stays gone; feed applied", "stays gone; refetched")

        # relationships
        e = step("relationship create", "relationship.create", lambda: ok(admin.post("/api/kb/edges", {"type": "teaches", "source_id": ins["id"], "target_id": m1["id"]})),
                 f"!!window.__kbGraph.cy.getElementById('{ins['id']}').length", _map_edge(ins["id"], m1["id"]))
        step("relationship update (role, note)", "relationship.update",
             lambda: ok(admin.patch(f"/api/kb/edges/{e['id']}", {"version": e["version"], "note": "matrix note", "props": {"role": "backup_1"}})),
             f"window.__kbGraph.cy.getElementById('{e['id']}').data('note') === 'matrix note'",
             f"window.__NP.data.edges.some((x) => x.p && x.p.instructor_role === 'backup_1')")
        step("relationship archive", "relationship.archive", lambda: ok(admin.post(f"/api/kb/edges/{e['id']}/archive")),
             f"!window.__kbGraph.cy.getElementById('{e['id']}').length", f"!({_map_edge(ins['id'], m1['id'])})")
        step("relationship permanent delete (after archive)", "relationship.delete", lambda: ok(admin.delete(f"/api/kb/edges/{e['id']}")),
             _graph_fed, _map_refetched, "stays gone; feed applied", "stays gone; refetched")
        e = ok(admin.post("/api/kb/edges", {"type": "teaches", "source_id": ins["id"], "target_id": m1["id"]}))
        graph.wait_for_function(f"!!window.__kbGraph.cy.getElementById('{e['id']}').length", timeout=8000)

        # custom relationship types: a new type appears in the legend and filters with its own style
        def new_type():
            t = ok(admin.post("/api/kb/types/edge", {"label": "mentors", "inverse_label": "mentored by",
                                                       "rules": [{"source": "instructor", "target": "instructor"}]}))
            ok(admin.post("/api/kb/edges", {"type": "mentors", "source_id": ins["id"], "target_id": ins2["id"]}))
            return t
        t = step("custom relationship type create (+ a relationship of it)", "reltype.create", new_type,
                 "(() => { const f = document.querySelector('[data-testid=graph-edge-filter-mentors]'); const sw = f && f.parentElement.querySelector('.legend-line');"
                 " const e = window.__kbGraph.cy.edges().filter((x) => x.data('type') === 'mentors'); "
                 " return !!(f && sw && sw.dataset.color && e.length && e[0].data('color') === sw.dataset.color); })()",
                 "(() => { const l = document.querySelector('#legend [data-rel=mentors]'); return !!(l && l.dataset.color) && "
                 f"{_map_edge(ins['id'], ins2['id'], 'mentors')}; }})()",
                 "legend + filter + own colour/line", "legend (own colour/line) + edge")
        tt = ok(admin.get("/api/kb/types"))
        style = {x["key"]: (x["color"], x["line_style"]) for x in tt["edge_types"]}["mentors"]
        assert style != {x["key"]: (x["color"], x["line_style"]) for x in tt["edge_types"]}["teaches"]
        ver = {x["key"]: x["version"] for x in tt["edge_types"]}["mentors"]
        step("custom relationship type rename", "reltype.update",
             lambda: ok(admin.patch("/api/kb/types/edge/mentors", {"version": ver, "label": "coaches"})),
             "(() => { const f = document.querySelector('[data-testid=graph-edge-filter-mentors]'); return !!f && f.closest('label').textContent.includes('coaches'); })()",
             "(() => { const l = document.querySelector('#legend [data-rel=mentors]'); return !!l && l.textContent.includes('coaches'); })()")
        ok(admin.post("/api/kb/types/edge", {"label": "guides", "inverse_label": "guided by", "rules": [{"source": "instructor", "target": "instructor"}]}))
        g2 = ok(admin.post("/api/kb/edges", {"type": "guides", "source_id": ins["id"], "target_id": ins3["id"]}))
        graph.wait_for_function(f"!!window.__kbGraph.cy.getElementById('{g2['id']}').length", timeout=8000)
        npmap.wait_for_function(_map_edge(ins["id"], ins3["id"], "guides"), timeout=8000)
        step("custom relationship type merge", "reltype.update",
             lambda: ok(admin.post("/api/kb/types/edge/guides/merge", {"into": "mentors"})),
             f"window.__kbGraph.cy.edges().filter((x) => x.data('type') === 'guides').length === 0 && window.__kbGraph.cy.edges().filter((x) => x.data('type') === 'mentors').length === 2",
             _map_edge(ins["id"], ins3["id"], "mentors"))
        for x in ok(admin.get("/api/kb/graph", "rels=mentors"))["edges"]:
            ok(admin.post(f"/api/kb/edges/{x['id']}/archive"))
        time.sleep(3)
        step("custom relationship type archive", "reltype.archive", lambda: ok(admin.post("/api/kb/types/edge/mentors/archive")),
             "!document.querySelector('[data-testid=graph-edge-filter-mentors]')",
             "!document.querySelector('#legend [data-rel=mentors]')")

        # record types and fields
        tt = ok(admin.get("/api/kb/types"))
        wt = {x["key"]: x for x in tt["node_types"]}["workshop"]
        new_color = next(c for c in tt["palette"] if c != wt["color"])
        step("record type change (colour, a new field)", "type.update",
             lambda: ok(admin.patch("/api/kb/types/node/workshop", {"version": wt["version"], "color": new_color,
                                                                     "fields": wt["fields"] + [{"key": "venue", "label": "Venue", "kind": "short_text"}]})),
             f"window.__kbGraph.cy.getElementById('{ws['id']}').data('color') === '{new_color}'", _map_refetched,
             "node restyled", "refetched (the map's colours are its own)")

        # tags, owners, bulk, graph edits
        step("tag attach", "tag.attach", lambda: ok(admin.post(f"/api/kb/nodes/{m1['id']}/tags", {"name": "matrix"})),
             _graph_fed, _map_refetched, "refreshed", "refetched")
        tag = ok(admin.get("/api/kb/tags"))["items"][0]
        step("tag rename", "tag.update", lambda: ok(admin.patch(f"/api/kb/tags/{tag['id']}", {"version": tag["version"], "name": "matrixed"})),
             _graph_fed, _map_refetched, "refreshed", "refetched")
        step("tag detach", "tag.detach", lambda: ok(admin.delete(f"/api/kb/nodes/{m1['id']}/tags/{tag['id']}")),
             _graph_fed, _map_refetched, "refreshed", "refetched")
        cur = ok(admin.get(f"/api/kb/nodes/{m1['id']}"))
        step("owner (account and by role)", "record.owner",
             lambda: ok(admin.patch(f"/api/kb/nodes/{m1['id']}", {"version": cur["version"], "owner_id": USERS["editor"], "owner_record_id": ins["id"]})),
             f"window.__kbGraph.cy.getElementById('{m1['id']}').data('owner') === '{USERS['editor']}'", _map_refetched, "owner filter data", "refetched")
        v0 = graph.evaluate(f"window.__kbGraph.cy.getElementById('{m1['id']}').data('version')")
        step("bulk edit", "record.update",
             lambda: ok(admin.post("/api/kb/nodes/bulk", {"ids": [m1["id"]], "set": {"status": "draft"}})),
             f"window.__kbGraph.cy.getElementById('{m1['id']}').data('version') > {v0}", _map_refetched, "patched", "refetched")
        step("graph edit (a position moved)", "layout.update",
             lambda: ok(admin.post("/api/kb/graph/positions", {"positions": [{"node_id": m1["id"], "x": 812.0, "y": -412.0}]})),
             f"Math.round(window.__kbGraph.cy.getElementById('{m1['id']}').position('x')) === 812",
             f"window.__NP.data.nodes.some((n) => n.id === '{m1['id']}' && Math.round(n.x) === 203)", "moved", "moved (x/4)")

        # links, templates
        r = ok(admin.post("/api/kb/resources", {"url": "https://docs.google.com/presentation/d/b1-matrix", "title": "Matrix Deck", "kind": "slides"}))
        att = step("link attach (a deck on the module)", "link.attach", lambda: ok(admin.post(f"/api/kb/nodes/{m1['id']}/resources", {"resource_id": r["id"]})),
                   _graph_fed, _map_node("link:" + r["id"], "Matrix Deck"), "panel data (links are not graph nodes)", "deck node")
        step("link detach", "link.detach", lambda: ok(admin.post(f"/api/kb/attachments/{att['attachment_id']}/detach")),
             _graph_fed, f"!({_map_node('link:' + r['id'])})", "panel data", "deck gone")
        tpl_src = ok(admin.post("/api/kb/nodes", {"type": "module", "name": "Template Module"}))
        tpl = ok(admin.post("/api/kb/templates", {"source_id": tpl_src["id"], "name": "Module shape"}))
        made = step("template create (into the course)", "record.create",
                    lambda: ok(admin.post(f"/api/kb/templates/{tpl['id']}/instantiate", {"name": "From Template", "parents": [course["id"]]})),
                    None, None)
        ROWS.pop()
        t0 = time.monotonic()
        got = _until({"graph": (graph, _graph_has(made["root"]["id"])), "map": (npmap, _map_node(made["root"]["id"], "From Template"))}, t0)
        ROWS.append({"op": "template create (into the course)", "kind": "record.create", "graph": got["graph"], "map": got["map"], "gnote": "", "mnote": ""})

        # import and sync
        from lib.kb import service as svc

        def imported():
            with as_user(USERS["admin"], actor_type="import") as c:
                n = svc.create_node(c, svc.Actor(USERS["admin"], "import"), {"type": "module", "name": "Imported Module", "parents": [course["id"]]})
                c.commit()
            return {"id": str(n["id"])}
        imp = step("import (Sheets importer)", "record.create", imported, None, None)
        ROWS.pop()
        t0 = time.monotonic()
        got = _until({"graph": (graph, _graph_has(imp["id"])), "map": (npmap, _map_node(imp["id"], "Imported Module"))}, t0)
        ROWS.append({"op": "import (Sheets importer, actor import)", "kind": "record.create", "graph": got["graph"], "map": got["map"], "gnote": "", "mnote": ""})
        step("sync run (Sync now / scheduled)", "sync.run + record.create", lambda: _sync_one(), _graph_fed, _map_node("ins_matrix_sync", "Synced Teacher"),
             "refreshed", "new record")

        # people
        step("person account (e-mail link)", "owner.account",
             lambda: ok(admin.post(f"/api/kb/nodes/{ins['id']}/account", {"email": "kbmatrix-person@interviewkickstart.com"})),
             _graph_fed, _map_refetched, "feed applied", "refetched")

        assert graph.errors == [] and npmap.errors == [], (graph.errors, npmap.errors)
    finally:
        for c in contexts:
            c.close()
        _write_matrix()
        reset()
        _drop_custom()
    slow = [r for r in ROWS if r["graph"] is None or r["map"] is None or r["graph"] > LIMIT or r["map"] > LIMIT]
    assert not slow, slow


def _sync_one():
    import psycopg
    from kb_support import session_dsn
    from lib.kb import sync as engine
    M = engine.load_mapping()
    src = "kbmatrix_src"
    with owner() as c:
        c.execute(f"drop schema if exists {src} cascade")
        c.execute(f"create schema {src}")
        c.execute(f"""create table {src}.nodes (id text primary key, type text, label text, props jsonb, sensitive boolean default false);
            create table {src}.edges (id serial primary key, rel text, source_id text, target_id text, props jsonb);
            create table {src}.node_sources (node_id text, file text);
            create table {src}.node_layout (node_id text, x float8, y float8);
            create table {src}.people (canonical text, team text, title text, seniority text);
            create table {src}.people_aliases (alias text, canonical text);
            create table {src}.domain_aliases (alias text, domain text);
            create table {src}.workflow_owners (workflow_id text, suggestion text);
            create table {src}.curation_notes (id serial, scope text, row_key text, note text, position int)""")
        c.execute(f"insert into {src}.nodes (id, type, label, props) values ('ins_matrix_sync', %s, 'Synced Teacher', '{{}}')",
                  (M["roles"]["instructor"],))
    try:
        mapping = dict(M, type_fields={}, placement={}, new_record_types=[], new_relationship_types=[], relationships=[])
        with psycopg.connect(session_dsn()) as conn:
            out = engine.run(conn, trigger="cli", actor_id=USERS["admin"], apply=True, source=src, mapping=mapping)
        assert out["status"] == "ok", out
        return out
    finally:
        with owner() as c:
            c.execute(f"drop schema if exists {src} cascade")


def _write_matrix():
    if not ROWS:
        return
    def cell(v, note):
        if v is None:
            return "FAIL (not within 6 s)"
        return f"{v:.2f} s" + (f" ({note})" if note else "")
    lines = ["# Change-propagation matrix (run 6, B1)", "",
             "Every write path, performed as an admin (the import and the sync as themselves), on a local",
             "server with NO Supabase Realtime (the polling fallback, the slower path). Seconds from the",
             "moment the write returned until each open page showed it, without a reload. Limit: 5 s.",
             "API column: tests/test_kb_propagation.py asserts the change feed's kind and node_ids,",
             "GET /api/kb/graph and the \"/\" routes for the same operations.",
             "Generated by tests/test_kb_propagation_e2e.py on " + time.strftime("%Y-%m-%d %H:%M") + ".", "",
             "| Operation | Change kind | API | Graph page | \"/\" map |", "|---|---|---|---|---|"]
    for r in ROWS:
        lines.append(f"| {r['op']} | `{r['kind']}` | pass | {cell(r['graph'], r['gnote'])} | {cell(r['map'], r['mnote'])} |")
    worst = max((max(r["graph"] or 99, r["map"] or 99) for r in ROWS), default=0)
    lines += ["", f"Slowest: {worst:.2f} s. Both pages poll /api/kb/changes every 2.5 s while visible.",
              "\"feed applied\" / \"refreshed\": the page received the change and re-read what it shows; the change",
              "has no mark of its own on that page (a tag, a link, an owner on the map, a permanently",
              "deleted record that the archive had already removed)."]
    out = REPO / "docs" / "run6" / "MATRIX.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n" + "\n".join(lines))
