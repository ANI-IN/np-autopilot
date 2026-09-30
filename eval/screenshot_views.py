#!/usr/bin/env python3
"""Screenshot every B2 view against the LOCAL projection.

TEST HARNESS, NOT SHIPPED CODE. It serves the real `api/index.py` WSGI app over
the local PostgreSQL that migrate.py + project_graph.py filled, with two seams
stubbed so a screenshot does not need a Google sign-in:

  guard.identify          returns a fixed local identity instead of verifying a
                          Supabase token. NOTHING ELSE about the request path
                          changes — the same route table, the same handlers, the
                          same queries.
  data.request_connection yields a plain connection. The local database has no
                          Supabase auth rows, so np_role() would return 'none'
                          and RLS would correctly return nothing.

Both stubs exist HERE and only here. The deployed page keeps its real front
door; this file cannot weaken it because it is never imported by the app.

Usage:  SUPABASE_DB_URL_SESSION=... python3 eval/screenshot_views.py [outdir]
"""
from __future__ import annotations

import contextlib
import mimetypes
import os
import sys
import threading
from pathlib import Path
from wsgiref.simple_server import WSGIServer, make_server

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "web"))
sys.path.insert(0, str(REPO / "api"))

PUBLIC = REPO / "public"
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else REPO / "docs" / "screenshots" / "b4"


class _Identity:
    subject = "00000000-0000-0000-0000-0000000000b2"
    # Synthetic, and in the IK domain because `profiles` carries
    # `check domain_is_ik` — the local database enforces the same
    # signup rule production does. Belongs to nobody.
    email = "b2-screenshot-harness@interviewkickstart.com"
    role = "member"

    def __getattr__(self, _):          # tolerate fields the app may read
        return None


def _patch():
    from lib import guard, data  # noqa: F401
    guard.identify = lambda headers: _Identity()
    # request_connection is NOT stubbed. It sets request.jwt.claims and
    # switches to the `authenticated` role, which is what makes RLS apply — so
    # stubbing it would have meant screenshotting a page whose access control
    # never ran. The local database gets the same DSN for both pool variables
    # instead, and the profile row below is what grants the reads.
    os.environ.setdefault("SUPABASE_DB_URL_TRANSACTION",
                          os.environ["SUPABASE_DB_URL_SESSION"])
    return None


def _ensure_profile():
    """A profile row for the stub subject, in the LOCAL database only.

    /api/me is not stubbed — it runs its real query — so without a profile the
    page correctly paints "you are signed in and can read nothing". Granting
    the row here keeps that logic under test instead of bypassing it.
    """
    from pipeline.lib import db
    with db.connect(db.SESSION) as c, c.cursor() as cur:
        cur.execute("""insert into profiles(user_id,email,email_domain,role)
                       values (%s,%s,%s,'member')
                       on conflict (user_id) do update set role='member'""",
                    (_Identity.subject, _Identity.email, "interviewkickstart.com"))


def _serve():
    import index as api_app                                    # api/index.py

    def application(environ, start_response):
        path = environ.get("PATH_INFO", "/")
        if path.startswith("/api/"):
            return api_app.app(environ, start_response)
        rel = "index.html" if path in ("/", "") else path.lstrip("/")
        f = PUBLIC / rel
        if not f.is_file():
            start_response("404 NOT FOUND", [("content-type", "text/plain")])
            return [b"not found"]
        body = f.read_bytes()
        ctype = mimetypes.guess_type(str(f))[0] or "application/octet-stream"
        start_response("200 OK", [("content-type", ctype),
                                  ("content-length", str(len(body)))])
        return [body]

    class Quiet(WSGIServer):
        pass

    srv = make_server("127.0.0.1", 0, application, server_class=Quiet)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, srv.server_address[1]


#: The owner's list, 2026-09-30: taken at a 1440px-wide window at DPR 2.
SHOTS = [
    ("01-default-map", None,
     "the default map: every current type on one network, legacy as groups"),
    ("02-sessions-only", "types:class_session:",
     "only Sessions on: modules stay as ghost anchors named on their clusters"),
    ("02b-decks-and-modules", "types:slide_deck,module:",
     "only Decks + Modules on: decks hang off ghost sessions, which join their modules"),
    ("03-focus-api-design", "mapfocus:module:backend:3",
     "focus on API Design: its sessions, decks, week, assignments and instructors"),
    ("04-focus-robert-kreznarich", "mapfocus:instructor:Robert Kreznarich",
     "focus on Robert Kreznarich: his modules in SD1 and SD3"),
    ("05-api-design-opened", "module:backend:3",
     "API Design opened in its domain (double-click): sessions, links, Historical collapsed"),
    ("06-instructors-list", "list:instructor",
     "the List toggle: instructors, the 25 current first, the older sheets collapsed"),
    ("07-matrix-backend", "view:matrix:backend", "who teaches what — SD3 Backend Engineering"),
    ("08-matrix-testing", "view:matrix:testing", "who teaches what — SD4 Test Engineering"),
    ("09-timeline", "view:timeline", "the programme timeline"),
]
#: the same default map at DPR 1, to compare sharpness
DPR1_SHOT = ("10-default-map-dpr1", None, "the default map at DPR 1")


def main() -> int:
    if not os.environ.get("SUPABASE_DB_URL_SESSION"):
        sys.exit("set SUPABASE_DB_URL_SESSION to the LOCAL database")
    # The page gates on /api/config before it boots. These are LOCAL PLACEHOLDERS
    # for a harness that never talks to Supabase or Google — identify() is
    # stubbed, so nothing verifies them and nothing is sent anywhere. They exist
    # only so the client takes the signed-in path instead of painting the gate.
    os.environ.setdefault("SUPABASE_URL", "http://127.0.0.1/local-harness")
    os.environ.setdefault("SUPABASE_ANON_KEY", "local-harness-not-a-key")
    os.environ.setdefault("GOOGLE_OAUTH_CLIENT_ID", "local-harness.apps.local")
    _patch()
    _ensure_profile()
    srv, port = _serve()
    base = f"http://127.0.0.1:{port}"
    OUT.mkdir(parents=True, exist_ok=True)

    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(viewport={"width": 1440, "height": 900},
                            device_scale_factor=2)
        INIT = """
          try{
            const k=(window.__NP&&window.__NP.sessionKey)||'np_session';
            localStorage.setItem(k, JSON.stringify({
              access_token:'local', refresh_token:'local',
              expires_at: Math.floor(Date.now()/1000)+86400}));
          }catch(e){}
        """
        ctx.add_init_script(INIT)
        page = ctx.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: errors.append(m.text)
                if m.type == "error" else None)

        for name, action, caption in SHOTS:
            page.goto(base + "/", wait_until="networkidle")
            page.wait_for_timeout(2500)
            if action and action.startswith("module:"):
                # what a double-click on the map does: open it in its domain
                _, slug, seq = action.split(":")
                page.evaluate(
                    """([slug,seq])=>{const n=D.nodes.find(x=>x.t==='module'&&
                        x.dom===slug&&String((x.p||{}).sequence)===seq);
                       if(n){state.open.add(n.id);goPlace({kind:'domain',id:domainOf(n).id},'shot');
                             openNode(n.id);}}""", [slug, seq])
            elif action and action.startswith("instructor:"):
                page.evaluate(
                    """(name)=>{const n=D.nodes.find(x=>x.t==='instructor'&&x.l===name);
                       if(n){goPlace({kind:'node',id:n.id},'shot');openNode(n.id);}}""",
                    action.split(":", 1)[1])
            elif action and action.startswith("view:matrix"):
                dom = action.split(":")[2] if action.count(":") > 1 else None
                page.evaluate("""(d)=>{state.fDomain=d; renderFilters(); setView('matrix',true);}""", dom)
            elif action == "view:timeline":
                page.evaluate("""()=>setView('timeline',true)""")
            elif action and action.startswith("mapfocus:instructor:"):
                page.evaluate("""(name)=>{const n=D.nodes.find(x=>x.t==='instructor'&&x.l===name);
                                  if(n)activate(n);}""", action.split(":", 2)[2])
            elif action and action.startswith("mapfocus:module:"):
                _, _, slug, seq = action.split(":")
                page.evaluate(
                    """([slug,seq])=>{const n=D.nodes.find(x=>x.t==='module'&&
                        x.dom===slug&&String((x.p||{}).sequence)===seq);
                       if(n)activate(n);}""", [slug, seq])
            elif action and action.startswith("list:"):
                page.evaluate("""(t)=>{state.types=new Set([t]); state.listMode=true;
                    recompute(true,'shot'); renderChips(); renderCrumbs(); writeUrl();}""",
                              action.split(":", 1)[1])
            elif action and action.startswith("types:"):
                spec, dom = action.split(":", 1)[1].rsplit(":", 1)
                page.evaluate("""([ts,d])=>{state.fDomain=d||null; renderFilters();
                    state.types=new Set(ts.split(',')); recompute(true,'shot');
                    renderChips(); renderCrumbs(); writeUrl();}""", [spec, dom])
            elif action and action.startswith("only:"):
                page.evaluate("""(t)=>onlyType(t)""", action.split(":", 1)[1])
            elif action and action.startswith("focus:"):
                _, slug, who = action.split(":", 2)
                page.evaluate(
                    """([slug,name])=>{
                       const mods=D.nodes.filter(x=>x.t==='module'&&x.dom===slug&&!x.legacy);
                       for(const m of mods)state.open.add(m.id);
                       const d=domainOf(mods[0]);
                       goPlace({kind:'domain',id:d.id},'shot');
                       const n=D.nodes.find(x=>x.t==='instructor'&&x.l===name);
                       if(n)openNode(n.id);}""", [slug, who])
            page.wait_for_timeout(1200)
            path = OUT / f"{name}.png"
            page.screenshot(path=str(path))
            shown = path.relative_to(REPO) if path.is_relative_to(REPO) else path
            print(f"  {shown}  — {caption}")
        # the same map at DPR 1 (the renderer harness checks the backing store
        # at DPR 1 and 2; this is the picture to compare sharpness by eye)
        ctx1 = b.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        ctx1.add_init_script(INIT)
        p1 = ctx1.new_page()
        p1.goto(base + "/", wait_until="networkidle")
        p1.wait_for_timeout(3000)
        name, _, caption = DPR1_SHOT
        p1.screenshot(path=str(OUT / f"{name}.png"))
        print(f"  {OUT.name}/{name}.png  — {caption}")
        b.close()
    srv.shutdown()
    # The Google Sign-In script rejects the placeholder client id. That is the
    # harness, not the page, and filtering it is not the same as ignoring real
    # errors — everything else still fails the run.
    noise = ("favicon", "gsi_logger", "client id is not found",
             "status of 403")
    real_errors = [e for e in errors
                   if not any(n in e.lower() for n in noise)]
    if real_errors:
        print(f"\n  {len(real_errors)} console/page error(s):")
        for e in real_errors[:8]:
            print(f"    {e[:160]}")
        return 1
    print("\n  no console or page errors")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
