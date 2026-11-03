"""D2 — live updates over Supabase Realtime, with presence, through the local
demo server (eval/kb_demo_server.py): real local-GoTrue sessions, the Realtime
origin taken from `supabase status`, and the security policy's connect-src
widened to exactly that origin. Polling stays the fallback (test_kb_e2e covers
it with Realtime off).

Needs the local stack running (Realtime + Auth) and the demo users from
eval/kb_demo_seed.py; skips otherwise. Uses the users only: the seeded demo
content is not touched (a record is created and removed by the test).
"""
from __future__ import annotations

import pytest

from kb_support import dev_server, owner, requires_kb

pytest.importorskip("playwright.sync_api", reason="kb realtime: needs the playwright package")
from playwright.sync_api import expect, sync_playwright                # noqa: E402

pytestmark = [requires_kb]
DEMO_PW = "ik-demo-local"


def _demo_users_exist() -> bool:
    try:
        with owner() as c:
            return c.execute("select count(*) from auth.users where email in "
                             "('demo-admin@interviewkickstart.com', 'demo-editor@interviewkickstart.com')").fetchone()[0] == 2
    except Exception:                                                  # noqa: BLE001
        return False


def _stack_up() -> bool:
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "eval"))
    try:
        import kb_local_stack
        kb_local_stack.status()
        return True
    except BaseException:                                              # noqa: BLE001
        return False


@pytest.mark.skipif(not (_demo_users_exist() and _stack_up()),
                    reason="kb realtime: needs the local Supabase stack running and the demo users (eval/kb_demo_seed.py)")
def test_presence_and_realtime_live_update_between_two_people():
    with owner() as c:
        tid = c.execute("select id from kb.node_types where key = 'topic'").fetchone()[0]
        nid = c.execute("insert into kb.nodes (type_id, name) values (%s, 'Realtime probe topic') returning id", (tid,)).fetchone()[0]
    try:
        with dev_server("kb_demo_server.py") as base, sync_playwright() as pw:
            b = pw.chromium.launch(channel="chrome", headless=True)

            frames: list[str] = []          # what the admin's socket received
            polls: list[int] = []           # frame count at each change-feed fetch of the admin's page

            def login(email, watch=False):
                ctx = b.new_context(viewport={"width": 1440, "height": 900})
                p = ctx.new_page()
                if watch:
                    p.on("websocket", lambda ws: ws.on(
                        "framereceived", lambda f: frames.append(f if isinstance(f, str) else f.decode(errors="replace"))))
                    p.on("request", lambda r: "/api/kb/changes?since=" in r.url and polls.append(len(frames)))
                p.goto(base + "/local-login")
                p.locator("#email").fill(email)
                p.locator("#password").fill(DEMO_PW)
                p.locator("#submit").click()
                expect(p.get_by_test_id("whoami")).to_be_visible(timeout=20000)
                p.goto(base + f"/kb/#/records?open={nid}")
                expect(p.get_by_test_id("panel-name")).to_have_text("Realtime probe topic")
                return p
            a = login("demo-admin@interviewkickstart.com", watch=True)
            e = login("demo-editor@interviewkickstart.com")
            assert a.evaluate("(async () => (await import('/kb/js/realtime.js')).realtimeActive())()") is True
            expect(a.get_by_test_id("presence")).to_contain_text("demo editor is viewing", timeout=15000)
            e.get_by_test_id("panel-summary").click()
            expect(a.get_by_test_id("presence")).to_contain_text("demo editor is editing", timeout=15000)
            e.get_by_test_id("edit-summary").fill("changed over realtime")
            before = len(frames)
            e.get_by_test_id("panel-name").click()
            expect(a.get_by_test_id("panel-summary")).to_have_text("changed over realtime", timeout=10000)
            # The socket delivered it: after the edit the admin's socket received a
            # postgres_changes event, and the page fetched the change feed BECAUSE of
            # it (a fetch made after that frame arrived). Run 6 (B5): this replaces a
            # wall-clock bound (arrival under 3 s), which failed on a loaded machine
            # although the socket had delivered.
            got = [i for i, f in enumerate(frames) if i >= before and '"postgres_changes"' in f]
            assert got, "the admin's socket received no change event after the edit"
            assert any(n > got[0] for n in polls), "no change-feed fetch followed the socket's event"
            b.close()
    finally:
        with owner() as c:
            # Remove the probe record. Its audit rows stay: the activity log is
            # append-only (0029), even for this fixture. They are attributed (System,
            # demo admin, demo editor), never "Someone", and the demo seed, which is
            # re-run after every test run, truncates the log (A2).
            c.execute("delete from kb.nodes where id = %s", (nid,))
