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
from lib.guard import audit, bearer, identify                                  # noqa: E402

import config                                                          # noqa: E402

#: THE ROUTE TABLE IS NAMES, AND THE MODULE IS IMPORTED WHEN IT IS SERVED.
#:
#: Importing all eleven endpoint modules at module load meant a cold start
#: serving /api/overview also paid for `session` -> `gotrue` ->
#: `urllib.request`, and for `curate` -> the curation service. Measured at
#: ~77 ms of import on a cold start, most of it for code the request will not
#: touch.
#:
#: THE GUARD PROPERTY IS UNCHANGED, and it is the reason this is a table of
#: NAMES rather than a dispatch each module registers for itself: `_serve_read`
#: is still the only path from a request to a connection, and it still calls
#: identify() unconditionally before it loads anything. A lazily imported
#: module cannot bring its own front door either.
#:
#: The path IS the module name for every endpoint —
#: `tests/test_lazy_route_table.py` fails if one ever stops matching, because
#: the failure mode is a silent 404 on a route that exists.
READ_NAMES = ("aliases", "coverage", "me", "neighbourhood", "node", "overview",
              "search", "staffing", "structure")
WRITE_NAMES = ("curate",)

READS = {f"/api/{n}" for n in READ_NAMES}
WRITES = {f"/api/{n}" for n in WRITE_NAMES}

_ENDPOINTS: dict = {}


def endpoint_for(path: str):
    """(name, fn) for a route, importing its module the first time only."""
    name = path[len("/api/"):]
    if name not in _ENDPOINTS:
        import importlib
        mod = importlib.import_module(name)
        ep = mod.ENDPOINT
        if ep[0] != name:
            raise RuntimeError(
                f"{name}.py declares ENDPOINT {ep[0]!r}; the router maps "
                f"/api/{name} to the module of the same name, so this route "
                f"would 404 while looking present")
        _ENDPOINTS[name] = ep
    return _ENDPOINTS[name][:2]


def endpoint_options(name: str) -> dict:
    """The optional third ENDPOINT element: etag / cache / compress (B3)."""
    ep = _ENDPOINTS.get(name) or ()
    return ep[2] if len(ep) > 2 else {}

MAX_BODY = 16 * 1024

#: Applied to every response. The CSP and HSTS for static assets come from
#: vercel.json; these are the ones that matter on a JSON body.
BASE_HEADERS = [
    ("content-type", "application/json"),
    ("x-content-type-options", "nosniff"),
    ("referrer-policy", "no-referrer"),
]


def _respond(start_response, status: int, body: dict, *, no_store: bool = False,
             cache: str | None = None, etag: str | None = None,
             accept_encoding: str | None = None):
    raw = json.dumps(body, default=str, separators=(",", ":") if cache else None).encode()
    headers = list(BASE_HEADERS)
    # A session response carries refresh tokens; authorised data must not sit in
    # a shared cache either. An endpoint may opt into PRIVATE caching (B3):
    # `private` still keeps it out of every shared cache.
    headers.append(("cache-control", cache if cache and not no_store else
                    ("no-store, private" if no_store else "private, no-store")))
    if etag:
        headers.append(("etag", etag))
    if cache:
        headers.append(("vary", "Authorization, Accept-Encoding"))
    if accept_encoding is not None:
        raw, enc = _compress(raw, accept_encoding)
        if enc:
            headers.append(("content-encoding", enc))
    headers.append(("content-length", str(len(raw))))
    start_response(f"{status} {'OK' if status < 400 else 'ERROR'}", headers)
    return [raw]


#: Compressed bodies, keyed by the SHA-256 of the exact bytes and the encoding.
#: The payload is still built from a query under the caller's RLS on every
#: request — only the compression of IDENTICAL bytes is reused, so nothing one
#: caller was allowed to see can reach another.
_COMPRESSED: dict = {}

#: QUALITY 5, NOT 11. Measured on the 504,596 B structure payload: q11 is
#: 109,626 B in 550 ms, q5 is 127,261 B in 7 ms. Quality 11 first shipped and
#: raised the local cold-start premium from 13.5 ms to 578 ms — every new
#: instance paid it before its memo was warm. 14% smaller is not worth that,
#: and q5 is still well under the 150 KB target.
BROTLI_QUALITY = 5


def _compress(raw: bytes, accept_encoding: str) -> tuple[bytes, str | None]:
    import hashlib
    offered = {t.split(";")[0].strip().lower() for t in accept_encoding.split(",")}
    enc = None
    if "br" in offered:
        try:
            import brotli                                             # noqa: F401
            enc = "br"
        except ImportError:
            enc = None
    if enc is None and "gzip" in offered:
        enc = "gzip"
    if enc is None:
        return raw, None
    key = (hashlib.sha256(raw).digest(), enc)
    hit = _COMPRESSED.get(key)
    if hit is None:
        if enc == "br":
            import brotli
            hit = brotli.compress(raw, quality=BROTLI_QUALITY)
        else:
            import gzip
            hit = gzip.compress(raw, compresslevel=9)
        if len(_COMPRESSED) >= 4:
            _COMPRESSED.pop(next(iter(_COMPRESSED)))
        _COMPRESSED[key] = hit
    return hit, enc


def _not_modified(start_response, etag: str, cache: str):
    start_response("304 Not Modified",
                   [("etag", etag), ("cache-control", cache),
                    ("vary", "Authorization, Accept-Encoding"),
                    ("x-content-type-options", "nosniff"),
                    ("referrer-policy", "no-referrer")])
    return [b""]


def _etag_matches(header: str | None, etag: str) -> bool:
    if not header:
        return False
    if header.strip() == "*":
        return True
    return etag in {t.strip().removeprefix("W/") for t in header.split(",")}


def _serve_read(path: str, params: dict, environ, start_response):
    """The only path from an HTTP request to a database connection."""
    started = time.time()
    # IDENTIFY FIRST, then load the module. The table lookup used to be free,
    # so the order did not matter; `endpoint_for` performs an IMPORT, and an
    # unauthenticated caller should not be able to make the server do work it
    # would otherwise skip. Asserted by tests/test_lazy_route_table.py.
    try:
        identity = identify(_Headers(environ))
    except AuthError as exc:
        return _respond(start_response, 401,
                        {"error": "unauthorised", "reason": str(exc)})
    name, fn = endpoint_for(path)
    opts = endpoint_options(name)
    etag = None
    try:
        with data.request_connection(identity.subject) as conn:
            # CONDITIONAL GET, before the payload query (B3). The validator is
            # derived from the projection and the caller's role; on a match the
            # browser keeps its own private copy and nothing is rebuilt.
            if opts.get("etag"):
                etag = opts["etag"](conn)
                if etag and _etag_matches(environ.get("HTTP_IF_NONE_MATCH"), etag):
                    audit(identity, name, params, 0, started)
                    return _not_modified(start_response, etag, opts["cache"])
            payload, rows = fn(conn, identity, params)
    except data.DepthExceeded as exc:
        return _respond(start_response, 400,
                        {"error": "depth_exceeded", "reason": str(exc)})
    except Exception:                                                  # noqa: BLE001
        # Never return the exception text: it can carry row values.
        print(traceback.format_exc(), file=sys.stderr)
        return _respond(start_response, 500, {"error": "internal"})
    audit(identity, name, params, rows, started)
    return _respond(start_response, 200, payload, cache=opts.get("cache"),
                    etag=etag,
                    accept_encoding=(environ.get("HTTP_ACCEPT_ENCODING", "")
                                     if opts.get("compress") else None))


def _serve_write(path: str, environ, start_response):
    """The only path from an HTTP request to a curation write.

    Mirrors _serve_read deliberately: identify() first, unconditionally, then a
    connection scoped to that identity. What it does NOT do is decide whether
    the caller may write — `curation_service` does that, because the role check,
    the optimistic lock and the audit row belong together and a route that
    pre-checked the role would be a second place that has to stay correct.
    """
    _, fn = endpoint_for(path)
    started = time.time()
    try:
        identity = identify(_Headers(environ))
    except AuthError as exc:
        return _respond(start_response, 401,
                        {"error": "unauthorised", "reason": str(exc)})
    try:
        length = int(environ.get("CONTENT_LENGTH") or 0)
    except ValueError:
        length = 0
    if length <= 0 or length > MAX_BODY:
        return _respond(start_response, 400,
                        {"error": "bad_request",
                         "reason": "missing or oversized body"})
    try:
        body = json.loads(environ["wsgi.input"].read(length) or b"{}")
    except Exception:                                                  # noqa: BLE001
        return _respond(start_response, 400,
                        {"error": "bad_request", "reason": "body is not JSON"})
    if not isinstance(body, dict):      # run 6 audit A9b: an array body crashed the audit line below
        return _respond(start_response, 400,
                        {"error": "bad_request", "reason": "body must be an object"})

    try:
        with data.request_connection(identity.subject) as conn:
            status, payload = fn(conn, identity, body)
            # The service raises on every refusal, so reaching here with a 200
            # means the row and its audit entry are both written. Commit only
            # then: request_connection rolls back on the way out.
            if status == 200:
                conn.commit()
    except Exception:                                                  # noqa: BLE001
        print(traceback.format_exc(), file=sys.stderr)
        return _respond(start_response, 500, {"error": "internal"})

    # Audited on the HTTP side as well as in curation_audit: that table records
    # WHAT changed and why, this line records that the request happened at all,
    # including the refusals, which never reach the table.
    audit(identity, "curate", {"table": body.get("table"),
                               "key": body.get("key"), "status": status},
          1 if status == 200 else 0, started)
    return _respond(start_response, status, payload, no_store=True)


#: KB bodies carry long-form text (up to 100k characters of body), so the cap is
#: wider than the curation one — still bounded.
KB_MAX_BODY = 512 * 1024
KB_METHODS = {"GET", "POST", "PATCH", "DELETE"}


KB_TOKEN_PREFIX = "ikkb_"


class _TokenIdentity:
    """What audit() needs to know about a token caller: the user it acts as."""

    def __init__(self, subject: str):
        self.subject = subject
        self.email = None
        self.is_shared_account = False


def _identify_kb_token(token: str):
    """Hash → kb.resolve_token (0023/0025) → the owning user, or AuthError.
    Expired and revoked tokens resolve to nothing."""
    import hashlib
    digest = hashlib.sha256(token.encode()).hexdigest()
    with data.request_connection(None) as conn:
        with conn.cursor() as cur:
            cur.execute("select kb.resolve_token(%s)", (digest,))
            row = cur.fetchone()
        conn.commit()                       # keeps last_used_at
    if not row or not row[0]:
        raise AuthError("API token is invalid, expired or revoked")
    return _TokenIdentity(str(row[0]))


def _serve_kb(path: str, method: str, environ, start_response):
    """The only path from an HTTP request to the KB service (web/lib/kb).

    Same discipline as _serve_read / _serve_write: identify() first,
    unconditionally, then a connection scoped to that identity, so RLS (0023)
    applies to every statement. Commit only on success; any refusal rolls the
    whole request back, which is what makes a multi-step create atomic.
    """
    started = time.time()
    actor_type = "human"
    try:
        token = bearer(_Headers(environ))
        if token and token.startswith(KB_TOKEN_PREFIX):
            # A per-user KB API token (MCP clients). Resolved to its owner and
            # acted on AS that user under RLS, attributed as 'ai'. Only the KB
            # routes accept it; the corpus explorer's routes never do.
            identity = _identify_kb_token(token)
            actor_type = "ai"
        else:
            identity = identify(_Headers(environ))
    except AuthError as exc:
        return _respond(start_response, 401,
                        {"error": "unauthorised", "reason": str(exc)})
    if method not in KB_METHODS:
        return _respond(start_response, 405, {"error": "method_not_allowed"})
    body = None
    if method in ("POST", "PATCH"):
        try:
            length = int(environ.get("CONTENT_LENGTH") or 0)
        except ValueError:
            length = 0
        if length < 0 or length > KB_MAX_BODY:     # run 6 audit A11: read(-1) had no cap
            return _respond(start_response, 413, {"error": "too_large"})
        try:
            body = json.loads(environ["wsgi.input"].read(length) or b"{}") if length else {}
        except Exception:                                              # noqa: BLE001
            return _respond(start_response, 400,
                            {"error": "bad_request", "reason": "body is not JSON"})
        if not isinstance(body, dict):
            return _respond(start_response, 400,
                            {"error": "bad_request", "reason": "body must be an object"})
    params = {k: (v[0] if len(v) == 1 else v)
              for k, v in parse_qs(environ.get("QUERY_STRING", "")).items()}
    parts = [p for p in path[len("/api/kb/"):].split("/") if p]
    import kb_routes                                                  # noqa: PLC0415
    status, payload = 500, {"error": "internal"}
    try:
        with data.request_connection(identity.subject) as conn:
            try:
                status, payload = kb_routes.handle(
                    conn, kb_routes.svc.Actor(identity.subject, actor_type),
                    method, parts, params, body)
            except kb_routes.KbError as exc:
                # 202 = the change was recorded as a PROPOSAL: that row is the
                # successful write, so it commits. Every other refusal rolls back.
                if exc.status == 202:
                    conn.commit()
                else:
                    conn.rollback()
                status, payload = exc.status, exc.payload()
            else:
                if method != "GET":
                    conn.commit()
    except Exception:                                                  # noqa: BLE001
        print(traceback.format_exc(), file=sys.stderr)
        return _respond(start_response, 500, {"error": "internal"})
    audit(identity, "kb", {"method": method, "path": "/".join(parts[:1]),
                           "status": status}, 1 if status < 300 else 0, started)
    return _respond(start_response, status, payload, no_store=True)


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
            import session                                          # noqa: PLC0415
            status, out = session.handle(
                (body.get("action") or "signin").strip().lower(), body)
        except Exception:                                              # noqa: BLE001
            print(traceback.format_exc(), file=sys.stderr)
            status, out = 500, {"error": "internal"}
        return _respond(start_response, status, out, no_store=True)

    if path == "/api/cron/kb-sync":
        # The scheduled sync (docs/DEPLOYMENT.md "Scheduled sync"): called by the
        # database's pg_cron + pg_net with a secret. No user session reaches it,
        # and nothing but the secret opens it.
        if method not in ("GET", "POST"):
            return _respond(start_response, 405, {"error": "method_not_allowed"})
        from lib.kb import sync_api
        if not sync_api.cron_authorised(environ.get("HTTP_AUTHORIZATION")):
            return _respond(start_response, 401, {"error": "unauthorised"}, no_store=True)
        try:
            out = sync_api.run_now("cron", None)
        except Exception:                                              # noqa: BLE001
            print(traceback.format_exc(), file=sys.stderr)
            return _respond(start_response, 500, {"error": "internal"}, no_store=True)
        code = 200 if out.get("status") in ("ok", "skipped", "disabled") else 500
        return _respond(start_response, code, {k: out.get(k) for k in ("status", "run_id", "partial", "message", "seconds")},
                        no_store=True)

    if path.startswith("/api/kb/"):
        return _serve_kb(path, method, environ, start_response)

    if path in WRITES:
        if method != "POST":
            return _respond(start_response, 405,
                            {"error": "method_not_allowed",
                             "reason": "POST a curation change to this path"})
        return _serve_write(path, environ, start_response)

    if path in READS:
        if method != "GET":
            return _respond(start_response, 405, {"error": "method_not_allowed"})
        params = {k: (v[0] if len(v) == 1 else v)
                  for k, v in parse_qs(environ.get("QUERY_STRING", "")).items()}
        return _serve_read(path, params, environ, start_response)

    return _respond(start_response, 404,
                    {"error": "not_found",
                     "reason": f"no endpoint at {path}",
                     "endpoints": sorted(READS) + sorted(WRITES)
                                  + ["/api/config", "/api/session"]})
