"""Run 6, F6: old addresses people may have bookmarked still lead somewhere.

The KB is a hash-routed page (public/kb/js/app.js ROUTES). Run 6 renamed pages
in the sidebar ("Resources" -> "Links", "Programme timeline" -> "Program
timeline") and moved People into Settings, so public/kb/js/aliases.js maps the
addresses a person would have typed or bookmarked to the page they became, and
the router replaces the address before it looks up ROUTES. One test per alias.

No server path was removed in run 6 (docs/LEGACY_REMOVAL.md "Redirects"); the
server half asserts that every server path that existed before run 6 is still
routed (a 405 for the wrong method, never a 404), without a database.

No browser: the alias table and the router are read from source, and the
resolver is run with node when node is on PATH.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
JS = REPO / "public" / "kb" / "js"
APP = (JS / "app.js").read_text(encoding="utf-8")
ALIASES_SRC = (JS / "aliases.js").read_text(encoding="utf-8")

#: alias -> the hash it must land on (with the query `open=x` carried along).
EXPECTED = {
    "links": "#/resources?open=x",
    "people": "#/settings?tab=people&open=x",
    "members": "#/settings?tab=members&open=x",
    "sync": "#/settings?tab=sync&open=x",
    "tokens": "#/settings?tab=tokens&open=x",
    "reviews": "#/approvals?tab=reviews&open=x",
    "dashboard": "#/?open=x",
    "program-timeline": "#/timeline?open=x",
    "programme-timeline": "#/timeline?open=x",
    "who-teaches-what": "#/teaching?open=x",
    "record": "#/r?open=x",
}


def _aliases() -> dict[str, str]:
    body = re.search(r"export const ALIASES = \{(.*?)\n\};", ALIASES_SRC, re.S).group(1)
    return {k: v for k, v in re.findall(r"^\s*'?([\w-]+)'?\s*:\s*'([^']*)'", body, re.M)}


def _routes() -> set[str]:
    body = re.search(r"const ROUTES = \{(.*?)\n\};", APP, re.S).group(1)
    return {k.strip("'") for k in re.findall(r"('[\w-]*'|[\w-]+)\s*:", body)}


def _settings_tabs() -> set[str]:
    src = (JS / "views" / "settings.js").read_text(encoding="utf-8")
    return set(re.findall(r"\['(\w+)', '", re.search(r"const TABS = \[(.*?)\];", src).group(1)))


def test_the_alias_table_is_the_one_this_test_covers():
    assert set(_aliases()) == set(EXPECTED), "an alias was added or removed: give it a case in EXPECTED"


def test_no_alias_shadows_a_page():
    """An alias that is also a ROUTES key would never be reached (or would hide the page)."""
    assert not set(_aliases()) & _routes()


@pytest.mark.parametrize("alias", sorted(EXPECTED))
def test_alias_lands_on_a_page_that_exists(alias):
    target = _aliases()[alias]
    path, _, query = target.partition("?")
    assert path.split("/")[0] in _routes(), f"#/{alias} -> #/{target}: no such page"
    tab = dict(p.split("=") for p in query.split("&") if p).get("tab")
    if path == "settings":
        assert tab in _settings_tabs(), f"#/{alias} -> Settings tab {tab!r}, which does not exist"
    if path == "approvals":
        approvals = (JS / "views" / "approvals.js").read_text(encoding="utf-8")
        assert f"r.q.tab === '{tab}'" in approvals


def test_the_router_redirects_before_it_looks_up_a_page():
    assert "import { aliasTarget } from './aliases.js';" in APP
    route = APP[APP.index("export function route()"):]
    i_alias, i_routes = route.index("aliasTarget(r.path, r.q)"), route.index("ROUTES[key]")
    assert i_alias < i_routes
    # replace(), not assign: the old address must not stay in the history.
    assert "location.replace(moved)" in route[:i_routes]


NODE = shutil.which("node")


@pytest.mark.skipif(NODE is None, reason="node is not on PATH")
def test_alias_target_resolves_every_alias_with_node():
    url = (JS / "aliases.js").resolve().as_uri()
    cases = {k: [k] for k in EXPECTED}
    cases["record/<id>"] = ["record", "abc"]
    cases["not an alias"] = ["records"]
    script = ("import(%s).then((m) => { const c = %s; const out = {};"
              " for (const k of Object.keys(c)) out[k] = m.aliasTarget(c[k], { open: 'x' });"
              " console.log(JSON.stringify(out)); })") % (json.dumps(url), json.dumps(cases))
    out = json.loads(subprocess.run([NODE, "-e", script], check=True, capture_output=True,
                                    text=True, timeout=60).stdout)
    for alias, want in EXPECTED.items():
        assert out[alias] == want, (alias, out[alias])
    assert out["record/<id>"] == "#/r/abc?open=x"
    assert out["not an alias"] is None


# ---------------------------------------------------------------------------- server paths

#: Every server path before run 6 (commit 9a739f9, api/index.py), with a method
#: the router refuses with 405 — reached without a session or a database.
PRE_RUN6_SERVER_PATHS = {
    "/api/aliases": "POST", "/api/coverage": "POST", "/api/me": "POST", "/api/neighbourhood": "POST",
    "/api/node": "POST", "/api/overview": "POST", "/api/search": "POST", "/api/staffing": "POST",
    "/api/structure": "POST", "/api/curate": "GET", "/api/session": "GET", "/api/cron/kb-sync": "PUT",
}


@pytest.fixture(scope="module")
def index():
    sys.path.insert(0, str(REPO / "web"))
    sys.path.insert(0, str(REPO / "api"))
    import index as mod
    return mod


def _call(index, path, method):
    seen = {}

    def start_response(status, headers):
        seen["status"] = int(status.split()[0])
    body = b"".join(index.app({"PATH_INFO": path, "REQUEST_METHOD": method, "QUERY_STRING": ""}, start_response))
    return seen["status"], json.loads(body or b"{}")


@pytest.mark.parametrize("path", sorted(PRE_RUN6_SERVER_PATHS))
def test_a_pre_run6_server_path_is_still_routed(index, path):
    status, _ = _call(index, path, PRE_RUN6_SERVER_PATHS[path])
    assert status == 405, f"{path}: {status} (a removed server path needs a redirect, not a 404)"


def test_an_unknown_server_path_is_a_404_that_lists_the_endpoints(index):
    status, body = _call(index, "/api/no-such-thing", "GET")
    assert status == 404
    listed = set(body["endpoints"])
    assert {p for p in PRE_RUN6_SERVER_PATHS if p != "/api/cron/kb-sync"} <= listed
    assert "/api/stats" in listed


def test_the_static_pages_and_the_stats_fallback_are_still_shipped():
    """`/` (the map), `/kb/` and public/stats.json (the landing numbers' fallback
    with NP_MAP_SOURCE=old) are static files: removing one would 404."""
    for rel in ("public/index.html", "public/kb/index.html", "public/stats.json"):
        assert (REPO / rel).is_file(), rel
