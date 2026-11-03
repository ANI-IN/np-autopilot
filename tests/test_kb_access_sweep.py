"""Run 6, F5 — the access sweep: EVERY API route, called as every kind of caller.

Callers: anonymous; a signed-in account OUTSIDE the IK domain (a genuine,
correctly signed session whose address is not @interviewkickstart.com); and an
IK viewer, contributor, editor and admin (tests/kb_support.py's synthetic
users).

The route list is DERIVED, so a new route is covered or fails this file:
  * api/index.py: READS and WRITES (the map's routes and curation), and every
    `path == "/api/..."` special case in app(), must each be in this file;
  * api/kb_routes.py: every path word its dispatcher compares (`head == ...`,
    `rest == [...]`, `action == ...`, the type ops tables) must appear in
    KB_ROUTES below.

The matrix, per route:
  anonymous                  -> 401 on every identified route
  outside the IK domain      -> 403 on every identified route (checked server
                                side, per request: web/lib/auth.require_allowed_domain)
  an IK role BELOW the route's minimum -> 403 (or 404 for a route about a
                                random id that is looked up first: never 2xx)
  an IK role AT or above it  -> never 401/403 (2xx, or a 4xx validation /
                                not-found answer for the empty body and random
                                ids sent here), never 5xx
and on every response: the security headers, no CORS grant, no secret value.

Plus the database: `authenticated` (and `anon`) cannot execute any
owner-only SECURITY DEFINER function in kb or public (listed from pg_proc).

LOCAL DATABASE ONLY (kb_support). No real data.
"""
from __future__ import annotations

import ast
import io
import json
import os
import re
import secrets
import time
import uuid
from pathlib import Path

import pytest

from kb_support import TEST_JWT_SECRET, USERS, Client, as_user, ensure_users, owner, requires_kb, reset

pytestmark = requires_kb

REPO = Path(__file__).resolve().parent.parent
RID = "00000000-0000-4000-8000-00000000f501"           # an id that exists nowhere
KEY = "kbsweep_no_such_type"                            # a type key that exists nowhere
ROLE_ORDER = ("viewer", "contributor", "editor", "admin")
OUTSIDER_ID = str(uuid.uuid5(uuid.NAMESPACE_URL, "np-kb-test/outside-the-domain"))
OUTSIDER_EMAIL = "kbtest-outsider@example.com"

V, C, E, A = ROLE_ORDER
#: (method, path after /api/kb, the lowest role that may use it, body).
#: `owner_rows`: a route about a row only its owner may change; for a random id
#: every caller is refused 403 ("only the person who saved it"), by design.
KB_ROUTES = [
    ("GET", "me", V, None), ("GET", "types", V, None), ("GET", "types?archived=1", V, None),
    ("POST", "types/rule", A, {}), ("GET", "types/edge-similar?label=kbsweep", V, None),
    ("POST", "types/node", E, {}), ("POST", "types/edge", C, {}), ("POST", "types/link", E, {}),
    ("PATCH", f"types/node/{KEY}", E, {}), ("PATCH", f"types/edge/{KEY}", E, {}), ("PATCH", f"types/link/{KEY}", E, {}),
    ("POST", f"types/node/{KEY}/archive", E, {}), ("POST", f"types/node/{KEY}/restore", E, {}),
    ("POST", f"types/node/{KEY}/duplicate", E, {}), ("POST", f"types/node/{KEY}/change-type", E, {}),
    ("POST", f"types/edge/{KEY}/archive", E, {}), ("POST", f"types/edge/{KEY}/merge", A, {}),
    ("POST", f"types/link/{KEY}/archive", E, {}),
    ("GET", "nodes/check-name?type=module&name=kbsweep", V, None),
    ("POST", "nodes/bulk", C, {}), ("POST", "nodes/bulk-archive", C, {}),
    ("GET", f"nodes/{RID}/completeness", V, None), ("GET", f"nodes/{RID}/delete-impact", V, None),
    ("GET", f"resources/{RID}/delete-impact", V, None), ("GET", f"resources/{RID}/completeness", V, None),
    ("GET", "archived", V, None), ("GET", "outline", V, None), ("POST", "outline/reorder", C, {}),
    ("GET", "flags", V, None), ("POST", "flags", V, {}),
    ("POST", f"flags/{RID}/resolve", V, {}), ("POST", f"flags/{RID}/dismiss", V, {}),
    ("GET", "templates", V, None), ("POST", "templates", E, {}),
    ("POST", f"templates/{RID}/instantiate", E, {}), ("POST", f"templates/{RID}/archive", E, {}),
    ("POST", f"templates/{RID}/restore", E, {}), ("PATCH", f"templates/{RID}", E, {}),
    ("GET", "views", V, None), ("POST", "views", V, {}),
    ("PATCH", f"views/{RID}", V, {}, "owner_rows"), ("DELETE", f"views/{RID}", V, None, "owner_rows"),
    ("GET", "views/teaching", V, None), ("GET", "views/timeline", V, None),
    ("GET", "realtime", V, None), ("PATCH", f"attachments/{RID}", C, {}),
    ("POST", f"attachments/{RID}/detach", C, {}),
    ("GET", "dashboard", V, None), ("GET", "counts", V, None),
    ("GET", "tags", V, None), ("PATCH", f"tags/{RID}", E, {}), ("GET", f"tags/{RID}/impact", V, None),
    ("POST", f"tags/{RID}/merge", E, {}), ("POST", f"tags/{RID}/archive", E, {}), ("POST", f"tags/{RID}/restore", E, {}),
    ("GET", "search?q=kbsweep", V, None),
    ("GET", "sync", A, None), ("POST", "sync/run", A, {}), ("GET", "quality/sync", E, None),
    ("POST", f"nodes/{RID}/account", A, {}), ("DELETE", f"nodes/{RID}/account", A, None),
    ("GET", "graph", V, None), ("GET", "graph/positions", V, None),
    ("POST", "graph/positions", C, {}), ("DELETE", "graph/positions", C, None),
    ("GET", "activity", V, None), ("GET", "activity?format=csv", V, None),
    ("GET", "changes", V, None), ("GET", "changes?since=0", V, None),
    ("GET", "quality", V, None), ("GET", "quality/missing-resources", V, None),
    ("GET", "quality/duplicates", V, None), ("GET", "quality/link-candidates", V, None),
    ("POST", "quality/link-results", E, {}), ("GET", "quality/legacy-expertise", V, None),
    ("GET", "quality/no-owner", V, None),
    ("GET", "people", V, None), ("GET", "instructors", V, None),
    ("GET", "nodes", V, None), ("POST", "nodes", C, {}), ("GET", f"nodes/{RID}", V, None),
    ("PATCH", f"nodes/{RID}", C, {}), ("DELETE", f"nodes/{RID}", A, None),
    ("GET", f"nodes/{RID}/validate", V, None), ("GET", f"nodes/{RID}/impact", V, None),
    ("GET", f"nodes/{RID}/history", V, None), ("GET", f"nodes/{RID}/neighbourhood", V, None),
    ("POST", f"nodes/{RID}/archive", C, {}), ("POST", f"nodes/{RID}/restore", E, {}),
    ("POST", f"nodes/{RID}/duplicate", E, {}), ("POST", f"nodes/{RID}/resources", C, {}),
    ("POST", f"nodes/{RID}/tags", C, {}), ("DELETE", f"nodes/{RID}/tags/{RID}", C, None),
    ("GET", "courses", V, None), ("POST", "courses", C, {}), ("GET", "programs", V, None), ("POST", "programs", C, {}),
    ("GET", "edges", V, None), ("POST", "edges", C, {}), ("GET", f"edges/{RID}", V, None),
    ("PATCH", f"edges/{RID}", C, {}), ("DELETE", f"edges/{RID}", A, None),
    ("POST", f"edges/{RID}/archive", C, {}), ("POST", f"edges/{RID}/restore", E, {}),
    ("POST", f"edges/{RID}/retype", C, {}), ("GET", f"edges/{RID}/history", V, None),
    ("GET", "resources", V, None), ("POST", "resources", C, {}), ("GET", f"resources/{RID}", V, None),
    ("PATCH", f"resources/{RID}", C, {}), ("DELETE", f"resources/{RID}", A, None),
    ("POST", f"resources/{RID}/archive", C, {}), ("POST", f"resources/{RID}/restore", E, {}),
    ("GET", f"resources/{RID}/history", V, None),
    ("GET", "proposals", V, None), ("POST", f"proposals/{RID}/approve", E, {}), ("POST", f"proposals/{RID}/reject", E, {}),
    ("GET", "tokens", V, None), ("POST", "tokens", V, {}), ("POST", f"tokens/{RID}/revoke", V, {}),
    ("GET", "members", A, None), ("POST", "members/invite", A, {}),
    ("POST", f"members/invites/{RID}", A, {}), ("POST", f"members/invites/{RID}/revoke", A, {}),
    ("POST", f"members/{RID}", A, {}), ("POST", f"members/{RID}/remove", A, {}),
    ("GET", "person-records", A, None), ("POST", "person-records/preview", A, {}), ("POST", "person-records/link", A, {}),
    ("POST", "my/link", V, {}), ("GET", "my/owned", V, None), ("POST", "claims", V, {}),
]

#: The special cases in api/index.py's app(): (method, the statuses EVERY caller gets).
PUBLIC_OR_SECRET = {
    # Public by design (docs/run6/SECURITY_SWEEP.md): what a browser needs to start a sign-in.
    "/api/config": ("GET", {200}),
    # Public by decision (SECURITY_SWEEP.md): the landing numbers, counts only (kb.landing_stats);
    # 404 when the map reads the old tables (NP_MAP_SOURCE=old).
    "/api/stats": ("GET", {200, 404}),
    # Its own credential is the Google ID token in the BODY; an empty body is a 400 for everyone.
    "/api/session": ("POST", {400}),
    # Only the scheduler's secret opens it; no user token ever does, an admin's included.
    "/api/cron/kb-sync": ("POST", {401}),
}

SECURITY_HEADERS = {
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "no-referrer",
}


# ---------------------------------------------------------------- the derivation
def _index_special_paths() -> set[str]:
    src = (REPO / "api" / "index.py").read_text(encoding="utf-8")
    return set(re.findall(r'path == "(/api/[^"]+)"', src))


def _kb_route_words() -> set[str]:
    """Every path word api/kb_routes.py's dispatcher compares against."""
    tree = ast.parse((REPO / "api" / "kb_routes.py").read_text(encoding="utf-8"))
    subjects = {"head", "rest", "sub", "action", "act"}

    def subject(n):
        while isinstance(n, ast.Subscript):
            n = n.value
        return n.id if isinstance(n, ast.Name) else None

    words: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare) and subject(node.left) in subjects:
            for comp in node.comparators:
                words |= {c.value for c in ast.walk(comp) if isinstance(c, ast.Constant) and isinstance(c.value, str)}
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id in ("TYPED", "kinds", "ops")
                                                for t in node.targets) and isinstance(node.value, ast.Dict):
            for k in node.value.keys:
                words |= {c.value for c in ast.walk(k) if isinstance(c, ast.Constant) and isinstance(c.value, str)}
    return words


def test_every_index_route_is_in_the_sweep():
    import index
    assert _index_special_paths() == set(PUBLIC_OR_SECRET), (
        "api/index.py's special-cased paths changed: add the new one to PUBLIC_OR_SECRET with its reason")
    assert index.READS and index.WRITES
    assert index.WRITES == {"/api/curate"}, "a new write route: add its expected matrix to this file"


def test_every_kb_route_word_is_in_the_sweep():
    words = _kb_route_words()
    assert {"members", "nodes", "invite", "check-name"} <= words, "the derivation found nothing: it is broken"
    covered = {seg for _, path, *_ in KB_ROUTES for seg in re.split(r"[/?&=]", path)}
    missing = sorted(words - covered)
    assert not missing, f"api/kb_routes.py dispatches on {missing}, which no KB_ROUTES entry calls"


# ---------------------------------------------------------------- the callers
def _token(sub: str, email: str) -> str:
    import jwt
    now = int(time.time())
    return jwt.encode({"sub": sub, "aud": "authenticated", "role": "authenticated", "exp": now + 600, "iat": now,
                       "email": email}, TEST_JWT_SECRET, algorithm="HS256")


CALLERS = {
    "anonymous": None,
    "outside": lambda: _token(OUTSIDER_ID, OUTSIDER_EMAIL),
    **{r: (lambda r=r: _token(USERS[r], f"kbtest-{r}@interviewkickstart.com")) for r in ROLE_ORDER},
}


def _call(method: str, path: str, token, body=None):
    Client(None)                                   # sets the test secret and the DSN, as every KB test does
    import index
    raw = json.dumps(body).encode() if body is not None else b""
    path, _, query = path.partition("?")
    env = {"REQUEST_METHOD": method, "PATH_INFO": path, "QUERY_STRING": query,
           "CONTENT_LENGTH": str(len(raw)), "wsgi.input": io.BytesIO(raw)}
    if token:
        env["HTTP_AUTHORIZATION"] = "Bearer " + token
    out = {}

    def start_response(status, headers):
        out["status"] = int(status.split()[0])
        out["headers"] = [(k.lower(), v) for k, v in headers]

    payload = b"".join(index.app(env, start_response))
    return out["status"], out["headers"], payload


@pytest.fixture(scope="module")
def world():
    ensure_users()
    reset()
    with owner() as c:
        # The outsider has a real account row and even a (misconfigured) admin
        # membership: it must still get nothing, from the app AND the database.
        c.execute("insert into auth.users (id, email, created_at) values (%s, %s, now()) on conflict (id) do nothing",
                  (OUTSIDER_ID, OUTSIDER_EMAIL))
        c.execute("insert into kb.memberships (user_id, role) values (%s, 'admin') "
                  "on conflict (user_id) do update set role = 'admin', archived_at = null", (OUTSIDER_ID,))
    yield
    reset()
    with owner() as c:
        c.execute("delete from kb.memberships where user_id = %s", (OUTSIDER_ID,))
        c.execute("delete from auth.users where id = %s", (OUTSIDER_ID,))
        c.execute("delete from kb.member_invites")


@pytest.fixture
def env(monkeypatch):
    secret = "kbsweep-" + secrets.token_hex(16)
    monkeypatch.setenv("KB_SYNC_SECRET", secret)
    monkeypatch.setenv("KB_SYNC_ENABLED", "false")          # Sync now answers "disabled", never runs
    return {"KB_SYNC_SECRET": secret, "SUPABASE_JWT_SECRET": TEST_JWT_SECRET}


def _check_response(where, status, headers, payload, secrets_, problems):
    h = dict(headers)
    for k, want in SECURITY_HEADERS.items():
        if h.get(k) != want:
            problems.append(f"{where}: header {k} is {h.get(k)!r}")
    csp = h.get("content-security-policy", "")
    if "frame-ancestors 'none'" not in csp or "default-src 'none'" not in csp:
        problems.append(f"{where}: content-security-policy is {csp!r}")
    if "max-age=" not in h.get("strict-transport-security", ""):
        problems.append(f"{where}: no strict-transport-security")
    if any(k.startswith("access-control-") for k in h):
        problems.append(f"{where}: a CORS header: {[k for k in h if k.startswith('access-control-')]}")
    text = payload.decode("utf-8", errors="replace")
    for name, value in secrets_.items():
        if value and value in text:
            problems.append(f"{where}: the response body contains {name}")


def _rank(role: str) -> int:
    return ROLE_ORDER.index(role)


def test_the_kb_route_matrix(world, env):
    problems: list[str] = []
    from pipeline.lib import db
    secrets_ = {**env, "the session DSN": os.environ.get(db.SESSION) or "",
                "the transaction DSN": os.environ.get(db.TRANSACTION) or ""}
    for entry in KB_ROUTES:
        method, path, need, body = entry[:4]
        owner_rows = "owner_rows" in entry[4:]
        has_id = RID in path or KEY in path
        for who, mk in CALLERS.items():
            status, headers, payload = _call(method, "/api/kb/" + path, mk() if mk else None, body)
            where = f"{who:11} {method:6} /api/kb/{path}"
            _check_response(where, status, headers, payload, secrets_, problems)
            if who == "anonymous":
                ok = status == 401
            elif who == "outside":
                ok = status == 403
            elif _rank(who) < _rank(need):
                ok = status == 403 or (has_id and status == 404)
            else:
                ok = status < 500 and status != 401 and (status != 403 or owner_rows)
            if not ok:
                problems.append(f"{where} -> {status} (lowest role: {need}) {payload[:160]!r}")
    assert not problems, "access matrix:\n  " + "\n  ".join(problems)


def test_the_map_and_curation_routes(world, env):
    """api/index.py READS (the "/" map's routes, which read the KB) and WRITES."""
    import index
    problems: list[str] = []
    params = {"/api/node": f"id={RID}", "/api/neighbourhood": f"id={RID}", "/api/search": "q=kbsweep"}
    routes = [("GET", p, None) for p in sorted(index.READS)] + [("POST", p, {}) for p in sorted(index.WRITES)]
    for method, path, body in routes:
        for who, mk in CALLERS.items():
            q = params.get(path)
            status, headers, payload = _call(method, path + ("?" + q if q else ""), mk() if mk else None, body)
            where = f"{who:11} {method:4} {path}"
            _check_response(where, status, headers, payload, env, problems)
            if who == "anonymous":
                ok = status == 401
            elif who == "outside":
                ok = status == 403
            elif method == "POST":
                # Curation is for np admins; these synthetic users are np members. Never a 2xx.
                ok = status in (400, 403)
            else:
                ok = status < 500 and status not in (401, 403)
            if not ok:
                problems.append(f"{where} -> {status} {payload[:160]!r}")
    assert not problems, "map routes:\n  " + "\n  ".join(problems)


def test_the_public_and_secret_routes(world, env):
    problems: list[str] = []
    for path, (method, want) in PUBLIC_OR_SECRET.items():
        for who, mk in CALLERS.items():
            status, headers, payload = _call(method, path, mk() if mk else None, None)
            _check_response(f"{who} {path}", status, headers, payload, env, problems)
            if status not in want:
                problems.append(f"{who:11} {method} {path} -> {status}, want {sorted(want)}")
    # /api/config hands out the PUBLIC values only.
    _, _, raw = _call("GET", "/api/config", None)
    assert set(json.loads(raw)) <= {"supabase_url", "supabase_anon_key", "google_client_id", "allowed_hd", "error"}
    # /api/stats, when on: aggregate counts only, never a row.
    status, _, raw = _call("GET", "/api/stats", None)
    if status == 200:
        st = json.loads(raw)
        assert set(st) <= {"source", "nodes", "edges", "files", "links", "by_type", "built_as_of", "head"}, sorted(st)
        assert all(isinstance(st[k], int) for k in ("nodes", "edges", "files", "links", "head") if k in st)
        assert all(isinstance(c, int) for c in (st.get("by_type") or {}).values()), "by_type holds counts only"
        assert st.get("built_as_of") is None or re.fullmatch(r"\d{4}-\d{2}-\d{2}", st["built_as_of"])
    # The cron route opens with its secret, and with nothing else.
    status, _, _ = _call("POST", "/api/cron/kb-sync", env["KB_SYNC_SECRET"])
    assert status == 200, "the scheduler's own secret must still open the cron route (sync disabled -> 200)"
    assert not problems, "\n  ".join(problems)


# ---------------------------------------------------------------- the domain check itself
@pytest.mark.parametrize("email", [
    "kbtest-x@example.com", "kbtest-x@interviewkickstart.com.example.com", "kbtest-x@notinterviewkickstart.com",
    "kbtest-x@interviewkickstart.co", "kbtest-x@sub.interviewkickstart.com", "", "kbtest-x",
])
def test_only_an_ik_address_passes_the_per_request_check(email):
    from lib.auth import DomainRefused, Identity, require_allowed_domain
    with pytest.raises(DomainRefused):
        require_allowed_domain(Identity(subject=OUTSIDER_ID, email=email, hosted_domain="", email_verified=True))


def test_an_ik_address_passes_the_per_request_check():
    from lib.auth import Identity, require_allowed_domain
    ident = Identity(subject=USERS["viewer"], email="KBTEST-viewer@InterviewKickstart.com",
                     hosted_domain="", email_verified=True)
    assert require_allowed_domain(ident) is ident


def test_an_api_token_of_an_account_without_an_ik_profile_reads_nothing(world):
    """The ikkb_ token path resolves to its owner without an e-mail claim; the
    database is what refuses a non-IK owner: kb.role() is 'none' (0035)."""
    import hashlib
    raw = "ikkb_" + secrets.token_urlsafe(32)
    with owner() as c:
        c.execute("insert into kb.nodes (type_id, name) select id, 'Kbsweep visible' from kb.node_types where key = 'module'")
        c.execute("insert into kb.api_tokens (user_id, name, token_hash, prefix, expires_at) "
                  "values (%s, 'kbsweep', %s, %s, now() + interval '1 day')",
                  (OUTSIDER_ID, hashlib.sha256(raw.encode()).hexdigest(), raw[:12]))
    status, _, payload = _call("GET", "/api/kb/nodes", raw)
    assert status == 200 and json.loads(payload)["items"] == [], payload[:200]
    assert _call("GET", "/api/kb/members", raw)[0] == 403
    assert _call("POST", "/api/kb/nodes", raw, {"type": "module", "name": "Kbsweep nope"})[0] == 403


def test_a_membership_grants_nothing_without_an_ik_profile(world):
    with owner() as c:
        c.execute("insert into kb.nodes (type_id, name) select id, 'Kbsweep row' from kb.node_types where key = 'module'")
    with as_user(OUTSIDER_ID) as c:
        assert c.execute("select kb.role()").fetchone()[0] == "none"
        assert c.execute("select count(*) from kb.nodes").fetchone()[0] == 0
    with as_user(USERS["admin"]) as c:
        assert c.execute("select kb.role()").fetchone()[0] == "admin"


# ---------------------------------------------------------------- database functions
#: SECURITY DEFINER functions `authenticated` is MEANT to execute, each with why.
#: Every other definer function in kb/public (not a trigger) is owner-only.
FOR_AUTHENTICATED = {
    "public.np_role": "every RLS policy resolves the caller's role through it",
    "kb.role": "every KB policy and require() resolves the caller's KB role through it",
    "kb.resolve_token": "api/index.py resolves an ikkb_ token by its hash, before it knows the owner",
    "kb.people": "member names for owners and person fields; checks role_at_least('viewer') itself",
    "kb.my_scope_ids": "the editor's own scope for the audit policy",
    "kb.record_history": "a record's History tab, filtered by the caller's rights",
    "kb.actor_emails": "names on Activity entries",
    "kb.landing_stats": "the landing numbers (/api/stats), counts only",
    "kb.link_me": "links only auth.uid() to its person record",
    "kb.person_candidates_for_me": "names and ids of unlinked records matching the caller's own name",
    "kb.claim_person": "a claim proposal by the caller; checks the role itself",
    "kb.apply_claim": "applying an approved claim; refuses anyone but an admin itself",
}


def _definer_functions():
    with owner() as c:
        roles = {r[0] for r in c.execute("select rolname from pg_roles where rolname in ('authenticated', 'anon')")}
        rows = c.execute("""
            select n.nspname || '.' || p.proname, p.oid::regprocedure::text,
                   has_function_privilege('authenticated', p.oid, 'execute'),
                   case when %s then has_function_privilege('anon', p.oid, 'execute') else false end
              from pg_proc p join pg_namespace n on n.oid = p.pronamespace
             where n.nspname in ('kb', 'public') and p.prosecdef
               and p.prorettype <> 'trigger'::regtype
               and not exists (select 1 from pg_depend d where d.objid = p.oid and d.deptype = 'e')
             order by 1""", ("anon" in roles,)).fetchall()
    return rows


def test_authenticated_cannot_execute_owner_only_functions():
    rows = _definer_functions()
    names = {r[0] for r in rows}
    assert "kb.apply_person_owner" in names and "kb.role" in names, "the pg_proc listing found nothing"
    missing = sorted(set(FOR_AUTHENTICATED) - names)
    assert not missing, f"listed as granted but no longer exist: {missing}"
    leaks = [sig for name, sig, auth, _anon in rows if auth and name not in FOR_AUTHENTICATED]
    assert not leaks, f"`authenticated` can execute owner-only SECURITY DEFINER functions: {leaks}"
    owner_only = [(name, sig) for name, sig, _a, _b in rows if name not in FOR_AUTHENTICATED]
    assert owner_only, "expected some owner-only functions (the sync's, the sign-in linking)"
    with as_user(USERS["admin"]) as c:
        import psycopg
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("select kb.apply_person_owner(%s)", (RID,))


def test_anon_cannot_execute_owner_only_functions():
    leaks = [sig for name, sig, _auth, anon in _definer_functions() if anon and name not in FOR_AUTHENTICATED]
    assert not leaks, f"`anon` can execute owner-only SECURITY DEFINER functions: {leaks}"


# ---------------------------------------------------------------- tokens, the cron secret
def test_mcp_tokens_are_hashed_scoped_expiring_and_revocable(world):
    admin = Client(USERS["admin"])
    s, tok = admin.post("/api/kb/tokens", {"name": "kbsweep", "expires_in_days": 1})
    assert s == 201 and tok["token"].startswith("ikkb_")
    with owner() as c:
        row = c.execute("select token_hash, prefix from kb.api_tokens where id = %s", (tok["id"],)).fetchone()
        assert row[0] != tok["token"] and len(row[0]) == 64 and tok["token"] not in row[1]
        logged = c.execute("select count(*) from kb.audit_log where table_name = 'api_tokens' "
                           "and (coalesce(after, before)::text like %s or coalesce(after, before) ? 'token_hash')",
                           ("%" + tok["token"] + "%",)).fetchone()[0]
        assert logged == 0, "a token or its hash reached the audit log"
    # never without an expiry (run 6 audit A10)
    assert admin.post("/api/kb/tokens", {"name": "kbsweep", "expires_in_days": None})[0] == 422
    # scoped: an admin's token is the AI assistant, which may not grant roles or invite
    assert _call("POST", f"/api/kb/members/{USERS['viewer']}", tok["token"], {"role": "editor"})[0] == 403
    assert _call("POST", "/api/kb/members/invite", tok["token"],
                 {"email": "kbtest-sweep-ai@interviewkickstart.com", "role": "admin"})[0] == 403
    # and it never opens the map's routes, only /api/kb
    assert _call("GET", "/api/structure", tok["token"])[0] == 401
    # revocable
    assert admin.post(f"/api/kb/tokens/{tok['id']}/revoke")[0] == 200
    assert _call("GET", "/api/kb/me", tok["token"])[0] == 401


def test_the_cron_secret_is_compared_in_constant_time_and_has_a_minimum_length(monkeypatch):
    from lib.kb import sync_api
    src = (REPO / "web" / "lib" / "kb" / "sync_api.py").read_text(encoding="utf-8")
    assert "hmac.compare_digest" in src
    monkeypatch.setenv("KB_SYNC_SECRET", "s" * 23)
    assert not sync_api.cron_authorised("Bearer " + "s" * 23), "a secret under 24 characters must open nothing"
    monkeypatch.setenv("KB_SYNC_SECRET", "s" * 24)
    assert sync_api.cron_authorised("Bearer " + "s" * 24)
    assert not sync_api.cron_authorised("Bearer " + "s" * 25) and not sync_api.cron_authorised(None)


def test_nothing_the_browser_can_fetch_names_a_server_secret():
    """Extends test_login_flow's check (service role, JWT secret) with the
    other server-only names: the cron secret, the database DSNs, the Drive key."""
    from pipeline.lib import db
    banned = ("KB_SYNC_SECRET", "NP_DRIVE_SA_KEY", "postgresql://", "postgres://", db.SESSION, db.TRANSACTION,
              "GOOGLE_OAUTH_CLIENT_SECRET", "private_key")
    for path in sorted((REPO / "public").rglob("*")):
        if not path.is_file() or path.name.startswith(".") or path.suffix in (".png", ".jpg", ".webp", ".ico", ".woff2"):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for b in banned:
            assert b not in text, f"{path.relative_to(REPO)} mentions {b!r}"
