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
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else REPO / "docs" / "screenshots"


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


SHOTS = [
    ("01-structure-default", None,
     "the whole structure layer, legacy modules faded"),
    ("02-module-api-design", "module:backend:3",
     "API Design module panel — the full chain"),
    ("03-instructor-panel", "instructor:first",
     "instructor panel — roles by evidence tier"),
    ("04-matrix-testing", "view:matrix:testing",
     "who-teaches-what, filtered to Test Engineering"),
    ("05-timeline", "view:timeline", "programme timeline"),
]


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
        ctx = b.new_context(viewport={"width": 1500, "height": 950},
                            device_scale_factor=2)
        ctx.add_init_script("""
          try{
            const k=(window.__NP&&window.__NP.sessionKey)||'np_session';
            localStorage.setItem(k, JSON.stringify({
              access_token:'local', refresh_token:'local',
              expires_at: Math.floor(Date.now()/1000)+86400}));
          }catch(e){}
        """)
        page = ctx.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: errors.append(m.text)
                if m.type == "error" else None)

        for name, action, caption in SHOTS:
            page.goto(base + "/", wait_until="networkidle")
            page.wait_for_timeout(2500)
            if action and action.startswith("module:"):
                _, slug, seq = action.split(":")
                page.evaluate(
                    """([slug,seq])=>{const n=D.nodes.find(x=>x.t==='module'&&
                        x.dom===slug&&String(x.p.sequence)===seq);
                       if(n){openNode(n.id);centreOn(n,1.8);}}""", [slug, seq])
            elif action == "instructor:first":
                page.evaluate(
                    """()=>{const n=D.nodes.find(x=>x.t==='instructor'&&
                        E.some(e=>(e.s===x.id||e.t===x.id)&&e.p&&e.p.tier==='mastersheet'));
                       if(n){openNode(n.id);centreOn(n,1.8);}}""")
            elif action and action.startswith("view:matrix"):
                dom = action.split(":")[2] if action.count(":") > 1 else None
                page.evaluate("""(d)=>{state.fDomain=d; setView('matrix',true);}""", dom)
            elif action == "view:timeline":
                page.evaluate("""()=>setView('timeline',true)""")
            page.wait_for_timeout(1200)
            path = OUT / f"{name}.png"
            page.screenshot(path=str(path))
            shown = path.relative_to(REPO) if path.is_relative_to(REPO) else path
            print(f"  {shown}  — {caption}")
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
