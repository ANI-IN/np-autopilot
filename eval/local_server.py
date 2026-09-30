#!/usr/bin/env python3
"""Serve the real app over the LOCAL Supabase stack — measurement and review.

TEST HARNESS, NOT SHIPPED CODE. `eval/` is excluded from every deploy by
.vercelignore, and db/window/check_function_map.py fails any artifact that
would upload a file carrying the stub (NP-LOCAL-PREVIEW-STUB) or an identity
bypass — tests/test_local_stub_never_ships.py holds both.

Two seams, both LOCAL ONLY, and nothing else is changed:

  - SERVER: `guard.identify` returns a fixed local identity (member role)
    instead of verifying a Supabase token. The route table, handlers, queries,
    connection reuse and RLS (request_connection sets the `authenticated`
    role) are the real ones.
  - BROWSER (the local review mode, owner request 2026-09-30): the page this
    server returns carries one injected script, FIRST in <head> so it runs
    before the page's own sign-in gate. It stores a stub session when there is
    none (so a plain reload stays signed in) and shows a "LOCAL PREVIEW, not
    production" banner. Google sign-in cannot work on 127.0.0.1, and before
    this the page stopped at the Google landing page unless /__signin had
    been opened first.

REFUSES a production DSN (db.production_reason), because it writes a profile
row for the harness identity; listens on 127.0.0.1 only; and answers only a
Host of 127.0.0.1 / localhost (no DNS-rebinding reach from another origin).

    python3 eval/local_server.py [port]        # prints "READY <port>" when up
"""
from __future__ import annotations

import json
import mimetypes
import os
import re
import sys
from pathlib import Path
from wsgiref.simple_server import WSGIRequestHandler, WSGIServer, make_server

REPO = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(REPO), str(REPO / "web"), str(REPO / "api")]

from pipeline.lib import db                                           # noqa: E402

PUBLIC = REPO / "public"
LOCAL_SESSION = db.LOCAL_TEST_DSN
LOCAL_TRANSACTION = db.LOCAL_TEST_DSN_TRANSACTION
#: Every piece of the stub carries this marker; the deploy check refuses it.
MARKER = "NP-LOCAL-PREVIEW-STUB"
LOCAL_HOSTS = {"127.0.0.1", "localhost"}


class _Identity:
    subject = "00000000-0000-0000-0000-0000000000b3"
    email = "b3-measure-harness@interviewkickstart.com"   # synthetic, IK domain
    role = "member"

    def __getattr__(self, _):
        return None


def _environment():
    os.environ.setdefault(db.SESSION, LOCAL_SESSION)
    os.environ.setdefault(db.TRANSACTION, LOCAL_TRANSACTION)
    for var in (db.SESSION, db.TRANSACTION):
        reason = db.production_reason(os.environ[var])
        if reason:
            sys.exit(f"REFUSED: {var} is production ({reason}); this harness "
                     "writes a profile row and stubs authentication.")
    # Placeholders so the page takes the signed-in path; nothing verifies them.
    os.environ.setdefault("SUPABASE_URL", "http://127.0.0.1/local-harness")
    os.environ.setdefault("SUPABASE_ANON_KEY", "local-harness-not-a-key")
    os.environ.setdefault("GOOGLE_OAUTH_CLIENT_ID", "local-harness.apps.local")


def _ensure_profile():
    with db.connect(db.SESSION) as c, c.cursor() as cur:
        cur.execute("""insert into profiles(user_id,email,email_domain,role)
                       values (%s,%s,'interviewkickstart.com','member')
                       on conflict (user_id) do update set role='member'""",
                    (_Identity.subject, _Identity.email))


def preview_script(page: str) -> str:
    """The browser half of the stub. The storage key is read from the page
    itself (window.__NP.sessionKey), so the two can never disagree."""
    m = re.search(r"sessionKey:\s*'([^']+)'", page)
    key = m.group(1) if m else "np_session"
    return f"""<script>/* {MARKER}: injected by eval/local_server.py; never deployed */
(function(){{
  var k={json.dumps(key)}, day=86400;
  try{{
    var s=JSON.parse(localStorage.getItem(k)||'null');
    if(!s||!s.access_token||(s.expires_at||0)*1000<Date.now()+day*1000)
      localStorage.setItem(k,JSON.stringify({{access_token:'local-preview',
        refresh_token:'local-preview',expires_at:Math.floor(Date.now()/1000)+30*day}}));
  }}catch(e){{}}
  function banner(){{
    if(document.getElementById('np-local-preview'))return;
    var b=document.createElement('div'); b.id='np-local-preview';
    b.setAttribute('role','status');
    b.textContent='LOCAL PREVIEW, not production \\u00b7 signed in as a local stub user (member)';
    b.style.cssText='position:fixed;left:12px;bottom:12px;width:276px;z-index:2147483647;'+
      'box-sizing:border-box;padding:6px 8px;border:1px solid #f85149;border-radius:6px;'+
      'background:#3d1418;color:#ffdcd7;font:600 11px -apple-system,Segoe UI,sans-serif;'+
      'pointer-events:none';
    document.body.appendChild(b);
  }}
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',banner);
  else banner();
}})();
</script>"""


def application_factory(preview: bool = True):
    from lib import guard
    guard.identify = lambda headers: _Identity()
    import index as api_app                                    # api/index.py

    def application(environ, start_response):
        host = (environ.get("HTTP_HOST") or "").rsplit(":", 1)[0].strip("[]")
        if host and host not in LOCAL_HOSTS:
            start_response("403 FORBIDDEN", [("content-type", "text/plain")])
            return [b"local review server: 127.0.0.1 / localhost only"]
        path = environ.get("PATH_INFO", "/")
        if path.startswith("/api/"):
            return api_app.app(environ, start_response)
        if path == "/__signin":                   # older link: the page does it now
            start_response("302 FOUND", [("location", "/")])
            return [b""]
        rel = "index.html" if path in ("/", "") else path.lstrip("/")
        f = PUBLIC / rel
        if not f.is_file():
            start_response("404 NOT FOUND", [("content-type", "text/plain")])
            return [b"not found"]
        body = f.read_bytes()
        if preview and rel == "index.html":
            page = body.decode("utf-8")
            body = page.replace("<head>", "<head>" + preview_script(page), 1).encode("utf-8")
        ctype = mimetypes.guess_type(str(f))[0] or "application/octet-stream"
        start_response("200 OK", [("content-type", ctype),
                                  ("cache-control", "no-store"),
                                  ("content-length", str(len(body)))])
        return [body]
    return application


class _Quiet(WSGIRequestHandler):
    def log_message(self, *a):
        pass


def main() -> int:
    _environment()
    _ensure_profile()
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    srv = make_server("127.0.0.1", port, application_factory(),
                      server_class=WSGIServer, handler_class=_Quiet)
    print(f"READY {srv.server_address[1]}", flush=True)
    srv.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
