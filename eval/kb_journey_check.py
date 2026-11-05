#!/usr/bin/env python3
"""The pre-deploy journey on the LOCAL demo (:8765): real local sign-in, three
roles in the real UI, the MCP server over stdio, and the Graph page and "/" map
open as live tabs. What it adds to tests/ and eval/kb_workflow_check.py: the
same run crosses every role, Claude's token and the live pages, against a real
GoTrue session rather than a test token.

Steps: sign-in and refusals -> a contributor proposes in the UI -> an editor
approves in the UI -> the record reaches the Graph tab -> edits, a stale version,
a bad name -> a module through create, rename, archive and restore on the "/" map
(topics are deferred there, so a module is the record to watch) -> role limits ->
Claude over MCP, including what its token must never do -> restore, permanent
delete, Activity -> a hostile name -> sign-out.

Needs eval/kb_demo_seed.py and eval/kb_demo_server.py 8765 first. It leaves
synthetic records behind, so re-run the seed afterwards. Screenshots (fictional
data) go to the gitignored .measure/journey.

    python eval/kb_journey_check.py          # prints PASS/FAIL per step; exit 1 on any FAIL
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import traceback
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from playwright.sync_api import sync_playwright, expect

BASE = "http://localhost:8765"
PW = "ik-demo-local"
REPO = Path(__file__).resolve().parent.parent
SHOTS = REPO / ".measure" / "journey"
SHOTS.mkdir(parents=True, exist_ok=True)
EM = {r: f"demo-{r}@interviewkickstart.com" for r in ("admin", "editor", "contributor")}
R = []


def check(step, ok, note=""):
    R.append((step, bool(ok)))
    print(f"{'PASS' if ok else 'FAIL'}  {step}" + (f"  ({note})" if note else ""), flush=True)


def http(method, path, tok=None, body=None):
    h = {"content-type": "application/json"}
    if tok:
        h["authorization"] = "Bearer " + tok
    rq = urllib.request.Request(BASE + path, method=method, headers=h,
                                data=None if body is None else json.dumps(body).encode())
    try:
        with urllib.request.urlopen(rq, timeout=60) as r:
            raw = r.read()
            return r.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except ValueError:
            return e.code, {"raw": raw[:200].decode("utf-8", "replace")}


def login(role):
    c, s = http("POST", "/local-login/session", body={"email": EM[role], "password": PW})
    assert c == 200, (c, list(s))
    return s.get("access_token") or s["session"]["access_token"]


def wait(page, js, t=10.0):
    t0 = time.monotonic()
    while time.monotonic() - t0 < t:
        try:
            if page.evaluate(js):
                return round(time.monotonic() - t0, 2)
        except Exception:
            pass
        page.wait_for_timeout(250)
    return None


def ui_login(ctx, role, errs):
    p = ctx.new_page()
    p.on("pageerror", lambda e: errs.append(f"{role}: {str(e)[:140]}"))
    p.goto(BASE + "/local-login")
    p.fill("#email", EM[role])
    p.fill("#password", PW)
    p.click("#submit")
    p.wait_for_url("**/kb/**", timeout=60000)
    p.wait_for_selector("[data-testid=dash-grid]", timeout=60000)
    return p


async def mcp_run(tok, fn):
    env = {**os.environ, "KB_API_URL": "http://127.0.0.1:8765", "KB_MCP_TOKEN": tok, "PYTHONIOENCODING": "utf-8"}
    p = StdioServerParameters(command=sys.executable, args=[str(REPO / "mcp_server" / "kb_server.py")], env=env)
    async with stdio_client(p) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            return await fn(s)


async def call(s, tool, **a):
    res = await s.call_tool(tool, a)
    t = res.content[0].text if res.content else ""
    return {"error": t} if res.isError else json.loads(t)


def section(name, fn):
    print(f"\n# {name}", flush=True)
    try:
        fn()
    except Exception as e:
        check(f"{name}: completed without an exception", False, f"{type(e).__name__}: {str(e)[:220]}")
        traceback.print_exc(limit=2)


NAME = "E2E Journey Topic"
S = {}
with sync_playwright() as pw:
    b = pw.chromium.launch(channel="chrome", headless=True)
    errs = []
    V = {"width": 1536, "height": 900}
    cc, ce, ca = (b.new_context(viewport=V) for _ in range(3))

    def s_auth():
        check("wrong password refused", http("POST", "/local-login/session", body={"email": EM["admin"], "password": "nope"})[0] == 401)
        check("unknown user refused", http("POST", "/local-login/session", body={"email": "nobody@interviewkickstart.com", "password": PW})[0] == 401)
        check("no token -> 401", http("GET", "/api/kb/nodes")[0] == 401)
        check("garbage token -> 401", http("GET", "/api/kb/nodes", "not-a-token")[0] == 401)
        for r in EM:
            S[r] = login(r)
        roles = {r: http("GET", "/api/kb/me", S[r])[1].get("role") for r in EM}
        check("each role signs in with the right role", roles == {r: r for r in EM}, str(roles))
    section("Sign-in and access", s_auth)

    def s_tabs():
        S["pc"], S["pe"], S["pa"] = ui_login(cc, "contributor", errs), ui_login(ce, "editor", errs), ui_login(ca, "admin", errs)
        check("three browsers signed in through /local-login", True)
        S["graph"] = ca.new_page()
        S["graph"].on("pageerror", lambda e: errs.append(f"graph: {str(e)[:140]}"))
        S["graph"].goto(BASE + "/kb/#/graph")
        check("admin Graph tab loaded", wait(S["graph"], "!!(window.__kbGraph && window.__kbGraph.cy && window.__kbGraph.cy.nodes().length)", 30) is not None)
        S["map"] = ca.new_page()
        S["map"].on("pageerror", lambda e: errs.append(f"map: {str(e)[:140]}"))
        S["map"].goto(BASE + "/")
        check("admin / map tab loaded and following the change feed", wait(S["map"], "!!(window.__NP_LIVE && window.__NP_LIVE.cursor !== null)", 30) is not None)
    section("Open the live pages", s_tabs)

    def s_propose():
        p = S["pc"]
        p.get_by_test_id("new-record").first.click()
        expect(p.get_by_test_id("proposal-note")).to_contain_text("sent to an editor for approval")
        p.get_by_test_id("create-type").fill("Topic")
        p.get_by_test_id("create-type-option").filter(has=p.get_by_text("Topic", exact=True)).first.click()
        p.get_by_test_id("create-name").fill(NAME)
        expect(p.get_by_test_id("create-submit")).to_contain_text("Send for approval")
        p.get_by_test_id("create-submit").click()
        p.wait_for_timeout(1500)
        p.screenshot(path=str(SHOTS / "1-contributor-proposed.png"))
        q = http("GET", "/api/kb/nodes?q=E2E+Journey", S["editor"])[1]["items"]
        check("nothing live until approved", q == [], f"{len(q)} found")
        pr = http("GET", "/api/kb/proposals", S["editor"])[1]["items"]
        check("contributor's new record is 1 pending proposal", len(pr) == 1, str(len(pr)))
    section("Contributor proposes (real UI)", s_propose)

    def s_approve():
        p = S["pe"]
        p.goto(BASE + "/kb/#/approvals")
        expect(p.get_by_test_id("proposal")).to_contain_text(NAME)
        p.screenshot(path=str(SHOTS / "2-editor-approvals.png"))
        t0 = time.monotonic()
        p.get_by_test_id("approve").click()
        expect(p.get_by_test_id("empty")).to_contain_text("Nothing waiting")
        q = http("GET", "/api/kb/nodes?q=E2E+Journey", S["editor"])[1]["items"]
        check("approved record is live", [n["name"] for n in q] == [NAME])
        S["n"] = q[0]
        rid = q[0]["id"]
        t = wait(S["graph"], f"!!window.__kbGraph.cy.getElementById('{rid}').length", 12)
        check("appears on the open Graph tab with no reload", t is not None, f"{round(time.monotonic()-t0,1)} s after click")
    section("Editor approves (real UI); live propagation", s_approve)

    def s_edit():
        rid = S["n"]["id"]
        d = http("GET", f"/api/kb/nodes/{rid}", S["editor"])[1]
        c, u = http("PATCH", f"/api/kb/nodes/{rid}", S["editor"], {"version": d["version"], "name": NAME + " v2", "summary": "Edited in the journey"})
        check("editor edit saved", c == 200, str(c))
        check("stale version -> 409", http("PATCH", f"/api/kb/nodes/{rid}", S["editor"], {"version": d["version"], "summary": "stale"})[0] == 409)
        c2, e = http("PATCH", f"/api/kb/nodes/{rid}", S["editor"], {"version": u["version"], "name": ""})
        check("empty name -> 422 naming the field", c2 == 422 and "name" in json.dumps(e), str(c2))
        check("rename reaches Graph tab", wait(S["graph"], f"window.__kbGraph.cy.getElementById('{rid}').data('label') === '{NAME} v2'", 12) is not None)
        S["ver"] = u["version"]
    section("Edits and errors", s_edit)

    def s_map():
        e = S["editor"]
        a = S["admin"]
        dom = http("GET", "/api/kb/nodes?type=domain", e)[1]["items"][0]["id"]
        has = lambda rid, extra="": f"window.__NP.data.nodes.some((n) => n.id === '{rid}'{extra})"
        c, m = http("POST", "/api/kb/nodes", e, {"type": "module", "name": "E2E Map Module", "parents": [dom]})
        check("editor creates a module in a domain", c == 201, str(c))
        rid = m["id"]
        t = wait(S["map"], has(rid), 12)
        check("module appears on the open / map, no reload", t is not None, f"{t} s")
        http("PATCH", f"/api/kb/nodes/{rid}", e, {"version": m["version"], "name": "E2E Map Module v2"})
        t = wait(S["map"], has(rid, " && n.l === 'E2E Map Module v2'"), 12)
        check("rename reaches the / map", t is not None, f"{t} s")
        http("POST", f"/api/kb/nodes/{rid}/archive", e, {"reason": "journey"})
        t = wait(S["map"], "!" + has(rid), 12)
        check("archive leaves the / map", t is not None, f"{t} s")
        http("POST", f"/api/kb/nodes/{rid}/restore", a)
        t = wait(S["map"], has(rid), 12)
        check("restore returns to the / map", t is not None, f"{t} s")
    section("The / map follows a module", s_map)

    def s_perm():
        rid = S["n"]["id"]
        c = S["contributor"]
        e = S["editor"]
        code, _ = http("PATCH", f"/api/kb/nodes/{rid}", c, {"version": S["ver"], "summary": "contributor change"})
        now = http("GET", f"/api/kb/nodes/{rid}", e)[1]
        check("contributor edit does not change the record directly", code in (200, 202) and now["summary"] == "Edited in the journey", f"HTTP {code}")
        pend = http("GET", "/api/kb/proposals", e)[1]["items"]
        for x in pend:
            http("POST", f"/api/kb/proposals/{x['id']}/reject", e, {"reason": "journey"})
        check("its proposal can be rejected, record unchanged",
              http("GET", "/api/kb/proposals", e)[1]["items"] == [] and http("GET", f"/api/kb/nodes/{rid}", e)[1]["summary"] == "Edited in the journey",
              f"{len(pend)} rejected")
        check("contributor cannot delete", http("DELETE", f"/api/kb/nodes/{rid}", c)[0] == 403)
        inv = {"email": "x@interviewkickstart.com", "role": "editor"}
        check("contributor cannot invite members", http("POST", "/api/kb/members/invite", c, inv)[0] == 403)
        check("editor cannot invite members", http("POST", "/api/kb/members/invite", e, inv)[0] == 403)
        check("editor cannot delete permanently", http("DELETE", f"/api/kb/nodes/{rid}", e)[0] == 403)
    section("Role limits", s_perm)

    def s_mcp():
        rid = S["n"]["id"]
        c, t = http("POST", "/api/kb/tokens", S["admin"], {"name": "e2e journey", "expires_in_days": 1})
        check("admin mints an API token", c in (200, 201) and t.get("token", "").startswith("ikkb_"))
        tok = t["token"]

        async def run(s):
            tools = await s.list_tools()
            return (len(tools.tools), await call(s, "search_knowledge", query="E2E Journey"), await call(s, "get_node", node_id=rid),
                    await call(s, "create_node", type="topic", name="E2E Claude Topic"), await call(s, "archive_node", node_id=rid, reason="journey"))
        with ThreadPoolExecutor(1) as ex:
            n, srch, got, made, arch = ex.submit(lambda: asyncio.run(mcp_run(tok, run))).result(timeout=120)
        check("MCP server lists its tools over stdio", n >= 15, f"{n} tools")
        check("Claude search finds the record", "E2E Journey" in json.dumps(srch))
        check("every result is marked as data", "data_notice" in got)
        check("Claude can create a record", "error" not in made, str(made)[:120] if "error" in made else "")
        check("Claude's archive needs a person's approval", arch.get("result", {}).get("status") == "approval_required", str(arch)[:120])
        check("record not archived yet", http("GET", f"/api/kb/nodes/{rid}", S["admin"])[1]["archived_at"] is None)
        check("AI token cannot mint tokens", http("POST", "/api/kb/tokens", tok, {"name": "x"})[0] == 403)
        check("AI token cannot invite or grant roles", http("POST", "/api/kb/members/invite", tok, {"email": "x@interviewkickstart.com", "role": "admin"})[0] == 403)
        check("person approves Claude's archive", http("POST", f"/api/kb/proposals/{arch['result']['proposal_id']}/approve", S["admin"])[0] == 200)
        check("record now archived", http("GET", f"/api/kb/nodes/{rid}", S["admin"])[1]["archived_at"] is not None)
        check("AI token cannot delete the archived record permanently", http("DELETE", f"/api/kb/nodes/{rid}", tok, {"confirm": NAME + " v2"})[0] == 403)
        check("archived record leaves the Graph tab", wait(S["graph"], f"!window.__kbGraph.cy.getElementById('{rid}').length", 12) is not None)
        check("token revoked", http("POST", f"/api/kb/tokens/{t['id']}/revoke", S["admin"])[0] == 200)
        check("revoked token -> 401", http("GET", "/api/kb/nodes", tok)[0] == 401)
    section("Claude through MCP", s_mcp)

    def s_restore_delete():
        rid = S["n"]["id"]
        a = S["admin"]
        check("restore works", http("POST", f"/api/kb/nodes/{rid}/restore", a)[0] == 200 and http("GET", f"/api/kb/nodes/{rid}", a)[1]["archived_at"] is None)
        code = http("DELETE", f"/api/kb/nodes/{rid}", a)[0]
        check("delete without archiving first is refused", code in (400, 403, 409, 422), str(code))
        http("POST", f"/api/kb/nodes/{rid}/archive", a, {"reason": "journey end"})
        c, body = http("DELETE", f"/api/kb/nodes/{rid}", a, {"confirm": NAME + " v2"})
        check("admin deletes the archived record", c in (200, 204), f"{c} {str(body)[:120] if c >= 400 else ''}")
        check("deleted record -> 404", http("GET", f"/api/kb/nodes/{rid}", a)[0] == 404)
        p = S["pa"]
        p.goto(BASE + "/kb/#/activity")
        p.wait_for_timeout(2500)
        txt = p.inner_text("body")
        p.screenshot(path=str(SHOTS / "3-activity.png"))
        check("Activity tells the story in sentences", "E2E Journey Topic" in txt and "Someone" not in txt)
    section("Restore, delete, Activity", s_restore_delete)

    def s_xss():
        c, n = http("POST", "/api/kb/nodes", S["editor"], {"type": "topic", "name": "<img src=x onerror=window.__x=1>"})
        check("hostile name handled (stored as text or refused)", c in (200, 201, 422), str(c))
        if c in (200, 201):
            p = S["pa"]
            p.goto(BASE + f"/kb/#/record/{n['id']}")
            p.wait_for_timeout(1500)
            S["map"].reload()
            wait(S["map"], "!!(window.__NP && window.__NP.data)", 20)
            S["map"].wait_for_timeout(1500)
            check("it does not run on the record page or the map", p.evaluate("window.__x") is None and S["map"].evaluate("window.__x") is None)
    section("Hostile input", s_xss)

    def s_out():
        m = S["map"]
        m.get_by_text("sign out", exact=True).click()
        m.wait_for_timeout(2500)
        q = ca.new_page()
        q.goto(BASE + "/kb/")
        q.wait_for_timeout(2500)
        check("after sign-out the workspace asks to sign in", q.get_by_text("Sign in").first.is_visible())
    section("Sign out", s_out)

    print()
    check("no uncaught page errors in any tab", errs == [], "; ".join(errs[:4]))
    b.close()

ok = sum(1 for _, x in R if x)
print(f"\nJOURNEY: {ok}/{len(R)} passed")
for s, x in R:
    if not x:
        print("  FAILED:", s)
sys.exit(0 if ok == len(R) else 1)
