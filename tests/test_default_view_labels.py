"""Every current module and instructor in the default view has a visible label.

Owner review 2026-09-30: in the domain cards "every other module has no
label" — the placer DROPPED a label that collided. Labels of current domains,
current modules and current instructors are now never hidden and never
shortened; an overlap is resolved by MOVING the label.

This runs the page's own layout and label placer (eval/default_view_labels.mjs)
on the REAL merged graph, packed by the server's own encoder, at six window
sizes including one with the side panel open, and asserts for every one of
those nodes: a label is drawn, in full, inside the canvas area, overlapping no
other such label.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(REPO), str(REPO / "web")]

from pipeline.lib import graphio, taxonomy                               # noqa: E402

_STRUCTURAL = {"id", "type", "label", "label_raw", "sources", "sensitive"}


def _end(role: str, i: int = 1) -> str:
    return taxonomy.edge_endpoints(taxonomy.edge_for_role(role))[i]


DECK, SESSION, WEEK = _end("module_deck"), _end("module_session"), _end("module_week")
ASSIGNMENT, TOPIC, CODE_REPO = _end("module_assignment"), _end("module_topic"), _end("module_repo")
CURRIC = _end("curriculum_module", 0)
key = lambda a, b: "-".join(sorted((a, b)))                                 # noqa: E731
_EDGE_KEYS = {"source", "target", "rel", "id", "sources", "provenance"}


def _payload(tmp_path: Path) -> Path:
    from lib import data                                                  # web/lib/data.py
    g = graphio.load_merged()
    types = set(data.STRUCTURE_TYPES)
    nodes = sorted((n for n in g["nodes"] if n["type"] in types and not n.get("sensitive")),
                   key=lambda n: n["id"])
    keep = {n["id"] for n in nodes}
    prov = taxonomy.edge_for_role("provenance")
    rows_n = [(n["id"], n["type"], n["label"], n.get("label_raw"),
               {k: v for k, v in n.items() if k not in _STRUCTURAL}, None, None)
              for n in nodes]
    edges = [e for e in g["edges"] if e["rel"] != prov
             and e["source"] in keep and e["target"] in keep]
    rows_e = [(i + 1, e["rel"], e["source"], e["target"],
               {k: v for k, v in e.items() if k not in _EDGE_KEYS})
              for i, e in enumerate(edges)]
    out = data.pack_structure(rows_n, rows_e)
    p = tmp_path / "structure.json"
    p.write_text(json.dumps(out), encoding="utf-8")
    return p


@pytest.fixture(scope="module")
def views(tmp_path_factory):
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    try:
        path = _payload(tmp_path_factory.mktemp("labels"))
    except FileNotFoundError as exc:
        pytest.skip(f"merged graph not available: {exc}")
    r = subprocess.run([node, str(REPO / "eval" / "default_view_labels.mjs"), str(path)],
                       cwd=REPO, capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stderr[-2000:]
    return json.loads(r.stdout.strip().splitlines()[-1])


def test_the_test_sees_the_current_curriculum(views):
    # 4 domains + 20 modules + 25 instructors today; a floor, not an exact
    # count, so a new module does not break the test — but an empty set would
    # make every assertion below vacuous
    assert views["want"] >= 40, views["want"]


@pytest.mark.parametrize("i", range(6))
def test_every_current_label_is_shown_in_full(views, i):
    v = views["views"][i]
    assert not v["missing"], f"{v['size']}: no label for {v['missing']}"
    assert not v["cut"], f"{v['size']}: label shortened for {v['cut']}"
    assert not v["outside"], f"{v['size']}: label outside the canvas area: {v['outside']}"
    assert v["overlaps"] == 0, f"{v['size']}: {v['overlaps']} overlapping labels: {v.get('pairs')}"


def test_the_default_map_holds_every_current_type(views):
    """Owner review 2026-09-30: one network of everything current; topics,
    files, repos, curriculum docs and programmes stay behind their chips."""
    got = views["defaultMap"]["nodes"]
    for t in ("domain", "module", WEEK, SESSION, ASSIGNMENT,
              DECK, "instructor", "person", "theme", "workflow", "group"):
        assert got.get(t), f"the default map shows no {t}: {got}"
    for t in (TOPIC, "file", CODE_REPO, CURRIC, "program"):
        assert not got.get(t), f"{t} is on the default map: {got}"
    assert views["defaultMap"]["list"] is False
    # decks hang off their session (or module), instructors off their modules
    e = views["defaultMap"]["edges"]
    assert e.get(key(SESSION, DECK), 0) > 300, e
    assert e.get("instructor-module", 0) >= 50, e


def test_a_chip_filters_the_map_not_a_list(views):
    got = views["decksModules"]
    assert got["list"] is False
    # the Modules chip also brings its collapsed "Legacy modules" group
    assert set(got["nodes"]) - {"group"} == {"module", DECK}, got["nodes"]
    # sessions are off: they stay as GHOST anchors, so every deck still shows
    # where it hangs (its session, or its module)
    tied = got["edges"].get(key(SESSION, DECK), 0) + got["edges"].get(key("module", DECK), 0)
    assert tied >= got["nodes"][DECK] * 0.95, got
    assert set(got["ghosts"]) <= {SESSION, "domain"}, got["ghosts"]


def test_clicking_a_chip_removes_that_type_from_the_map(views):
    got = views["afterDeckChip"]
    assert got["list"] is False, "a type chip switched to a list"
    assert not got["nodes"].get(DECK), got["nodes"]
    assert got["nodes"].get(SESSION) and got["nodes"].get("instructor"), got["nodes"]


def test_sessions_alone_are_never_bare_dots(views):
    """Owner review 2026-09-30: "Sessions only" shows the sessions with edges
    to their ghosted modules, and each cluster carries its module's name."""
    got = views["sessionsOnly"]
    assert set(got["nodes"]) == {SESSION}, got["nodes"]
    assert got["ghosts"].get("module") == 20, got["ghosts"]
    assert got["edges"].get(key("module", SESSION), 0) >= got["nodes"][SESSION], got["edges"]
    assert got["clusterLabels"] == 20, got


def test_a_dragged_node_pulls_its_neighbours_and_all_settle_home(views):
    s = views["springs"]
    assert s["neighbours"] > 0 and s["pulled"] > 5, s
    assert s["home"] and s["settledIn"] < 600, s


# ---- THE URL IS ONE VIEW, NEVER A PILE (owner review 2026-09-30) --------------
# 20 real clicks through the page's own handlers (modules, instructors, a domain,
# a group, chips, Esc, the matrix and back), with a history that really pushes,
# replaces, goes Back and Forward.

def test_twenty_clicks_leave_at_most_one_item_in_the_url(views):
    steps = views["url"]["steps"]
    assert len(steps) == 20
    for s in steps:
        assert s["ok"], f"after '{s['name']}' the URL piles up: {s['url']}"
        assert s["roundTrip"], f"after '{s['name']}' the URL is not the state: {s['url']}"


def test_breadcrumb_chips_and_count_agree_after_every_step(views):
    for s in views["url"]["steps"]:
        assert not s["bad"], f"after '{s['name']}': {s['bad']}"


def test_back_and_forward_restore_each_view(views):
    u = views["url"]
    assert u["pushes"] >= 10, "opening items and switching views must push history"
    for step in u["back"] + u["forward"]:
        assert not step["bad"], step
        assert step["same"] is not False, f"Back/Forward to {step['url']} did not restore that view"


def test_a_shared_link_reproduces_the_same_view(views):
    for f in views["url"]["fresh"]:
        assert f["same"] and not f["bad"], f


def test_an_old_open_list_keeps_only_its_last_item(views):
    o = views["url"]["oldLink"]
    assert o["ok"] and o["sel"] == o["want"], o
    assert "open=" not in o["url"], o


# ---- THE MAP IS 2D ONLY (owner, 2026-11-07) ----------------------------------
# The 3D view, its toggle, its bundle and its slow-machine fallback are gone. An
# old ?dim=3d or ?dim=2d link opens the 2D map and is rewritten without it.

def test_an_old_dim_link_opens_the_2d_map_without_the_parameter(views):
    for link in views["dimLinks"]:
        assert "dim=" not in link["url"], link
        assert link["view"] == "matrix", f"the rest of the old link was lost: {link}"
        assert link["hasDim"] is False, link


def test_the_3d_bundle_and_toggle_are_gone():
    page = (REPO / "public" / "index.html").read_text(encoding="utf-8")
    for gone in ("np3d", "dimtog", "V3", "state.dim"):
        assert gone not in page, f"{gone} is still in public/index.html"
    assert not (REPO / "public" / "vendor" / "np3d.min.js").exists()
