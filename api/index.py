"""The ONE HTTP surface. Every request to the application arrives here.

Vercel's supported Python runtime takes a single WSGI/ASGI entrypoint rather
than a handler per file, so the per-file `BaseHTTPRequestHandler` shells are
gone. That turned out to strengthen the property DECISIONS §D cares about
rather than weaken it:

    THERE IS NO LONGER A ROUTE THAT CAN FORGET THE GUARD.

Previously each file built its own shell with `serve(...)`, and "a route that
forgets the guard" was a real shape — layer 4's documented failure mode is a
matcher that silently stops matching, and `guard.py` is written to be
unnecessary precisely because of it. Now `_serve_read` below is the only code
path to a database connection, and it calls `identify()` unconditionally. A new
endpoint is a function in a table; it cannot bring its own front door.

The defence-in-depth argument is unchanged and still load-bearing: if this file
were bypassed entirely, `web/lib/data.py` would still connect as
`authenticated` with no identity, `auth.uid()` would be null, `np_role()` would
return 'none', and RLS would return zero rows.

ROUTING. Static files are served by Vercel from `public/` and never reach
this module. Only `/api/*` does.
"""
from __future__ import annotations

import json
import sys
import time
import traceback
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "web"))
sys.path.insert(0, str(HERE))

from lib import data                                                   # noqa: E402
from lib.auth import AuthError                                         # noqa: E402
from lib.guard import audit, identify                                  # noqa: E402

import aliases, config, coverage, me, neighbourhood, node              # noqa: E402,E401
import search, session, staffing                                       # noqa: E402,E401

#: path -> (endpoint name, read function). Every one of these is served by
#: _serve_read, which is the only place a request meets a connection.
READS = {f"/api/{mod.ENDPOINT[0]}": mod.ENDPOINT
         for mod in (aliases, coverage, me, neighbourhood, node, search, staffing)}

MAX_BODY = 16 * 1024

#: Applied to every response. The CSP and HSTS for static assets come from
#: vercel.json; these are the ones that matter on a JSON body.
BASE_HEADERS = [
    ("content-type", "application/json"),
    ("x-content-type-options", "nosniff"),
    ("referrer-policy", "no-referrer"),
]


def _respond(start_response, status: int, body: dict, *, no_store: bool = False):
    raw = json.dumps(body, default=str).encode()
    headers = list(BASE_HEADERS)
    # A session response carries refresh tokens; authorised data must not sit in
    # a shared cache either.
    headers.append(("cache-control",
                    "no-store, private" if no_store else "private, no-store"))
    headers.append(("content-length", str(len(raw))))
    start_response(f"{status} {'OK' if status == 200 else 'ERROR'}", headers)
    return [raw]


def _serve_read(path: str, params: dict, environ, start_response):
    """The only path from an HTTP request to a database connection."""
    name, fn = READS[path]
    started = time.time()
    try:
        identity = identify(_Headers(environ))
    except AuthError as exc:
        return _respond(start_response, 401,
                        {"error": "unauthorised", "reason": str(exc)})
    try:
        with data.request_connection(identity.subject) as conn:
            payload, rows = fn(conn, identity, params)
    except data.DepthExceeded as exc:
        return _respond(start_response, 400,
                        {"error": "depth_exceeded", "reason": str(exc)})
    except Exception:                                                  # noqa: BLE001
        # Never return the exception text: it can carry row values.
        print(traceback.format_exc(), file=sys.stderr)
        return _respond(start_response, 500, {"error": "internal"})
    audit(identity, name, params, rows, started)
    return _respond(start_response, 200, payload)


class _Headers:
    """Adapts a WSGI environ to the .get() interface guard.bearer expects."""

    def __init__(self, environ):
        self._e = environ

    def get(self, key, default=None):
        return self._e.get("HTTP_" + key.upper().replace("-", "_"), default)


def app(environ, start_response):
    path = urlparse(environ.get("PATH_INFO", "")).path.rstrip("/") or "/"
    method = environ.get("REQUEST_METHOD", "GET").upper()

    if path == "/api/config" and method == "GET":
        return _respond(start_response, 200, config.payload())

    if path == "/api/session":
        if method != "POST":
            return _respond(start_response, 405,
                            {"error": "method_not_allowed",
                             "reason": "POST an action to /api/session"})
        try:
            length = int(environ.get("CONTENT_LENGTH") or 0)
        except ValueError:
            length = 0
        if length <= 0 or length > MAX_BODY:
            return _respond(start_response, 400,
                            {"error": "bad_request",
                             "reason": "missing or oversized body"}, no_store=True)
        try:
            body = json.loads(environ["wsgi.input"].read(length) or b"{}")
        except Exception:                                              # noqa: BLE001
            return _respond(start_response, 400,
                            {"error": "bad_request", "reason": "body is not JSON"},
                            no_store=True)
        try:
            status, out = session.handle(
                (body.get("action") or "signin").strip().lower(), body)
        except Exception:                                              # noqa: BLE001
            print(traceback.format_exc(), file=sys.stderr)
            status, out = 500, {"error": "internal"}
        return _respond(start_response, status, out, no_store=True)

    if path in READS:
        if method != "GET":
            return _respond(start_response, 405, {"error": "method_not_allowed"})
        params = {k: (v[0] if len(v) == 1 else v)
                  for k, v in parse_qs(environ.get("QUERY_STRING", "")).items()}
        return _serve_read(path, params, environ, start_response)

    return _respond(start_response, 404,
                    {"error": "not_found",
                     "reason": f"no endpoint at {path}",
                     "endpoints": sorted(READS) + ["/api/config", "/api/session"]})
