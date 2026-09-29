"""Every item's links, for all 20 modules.

THE MASTERSHEET IS NEVER AN ITEM'S LINK. It is the citation — it belongs under
Provenance — and a panel that linked it would answer "where is this?" with
"in the spreadsheet that mentions it", which is the one place the reader
already was.

Everyone at IK has view access to these folders and to Uplevel (owner fact,
config/out-of-corpus-facts.yaml), so absence of a link is never an access
statement. Where a kind is missing the UI states which and why; these tests
assert the link EXISTS where the data has one, and that nothing is invented.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from pipeline.lib import graphio, mastersheet as ms, taxonomy as tax   # noqa: E402

HTTP = re.compile(r"^https?://", re.I)
UPLEVEL = re.compile(r"^https?://([\w-]+\.)*uplevel\.interviewkickstart\.com/", re.I)
DRIVE = re.compile(r"^https?://([\w-]+\.)*(drive|docs)\.google\.com/", re.I)
SHEET_NAME = ms.SHEET_FILE.lower()

pytestmark = pytest.mark.skipif(
    not graphio.CONTENT_PUBLIC.exists(), reason="content graph not built")


@pytest.fixture(scope="module")
def g():
    return graphio.load_merged(include_sensitive=False)


#: Node type names are DERIVED from the edges that reach them — B2, the same
#: rule pass 7 follows. A literal here is a second source of truth.
def _t(role, end=1):
    return tax.edge_endpoints(tax.edge_for_role(role))[end]


T_SESSION = _t("module_session")
T_ASSIGN = _t("module_assignment")
T_REVIEW = _t("assignment_reviewed_in")
T_DECK = _t("module_deck")


@pytest.fixture(scope="module")
def rowb(g):
    return [n for n in g["nodes"] if n["type"] == "module" and n.get("domain_slug")]


def _links(n):
    return [v for k, v in n.items()
            if k.endswith(("_url", "_link")) and isinstance(v, str) and v]


def test_there_are_exactly_twenty_row_b_modules(rowb):
    assert len(rowb) == 20


def test_every_module_has_an_uplevel_link(rowb):
    missing = [m["label"] for m in rowb if not UPLEVEL.match(m.get("uplevel_link") or "")]
    assert not missing, f"modules with no Uplevel link: {missing}"


def test_every_session_has_an_uplevel_link(g):
    bad = [n["label"] for n in g["nodes"] if n["type"] == T_SESSION
           and not UPLEVEL.match(n.get("uplevel_link") or "")]
    assert not bad, f"{len(bad)} sessions with no Uplevel link, e.g. {bad[:3]}"


def test_every_assignment_artefact_has_a_drive_link(g):
    bad = [n["label"] for n in g["nodes"]
           if n["type"] in (T_ASSIGN, T_REVIEW)
           and not DRIVE.match(n.get("drive_url") or "")]
    assert not bad, f"{len(bad)} assignment artefacts with no Drive link"


def test_every_deck_has_a_drive_link_including_download_disabled_ones(g):
    """canDownload false stops an EXPORT, not a person opening it. 46 files are
    in that state and withholding their link would read as "you cannot see
    this" when the owner fact says every reader can."""
    decks = [n for n in g["nodes"] if n["type"] == T_DECK]
    assert decks
    bad = [n["label"] for n in decks if not DRIVE.match(n.get("drive_url") or "")]
    assert not bad, f"{len(bad)} decks with no Drive link"
    unavailable = [n for n in decks if n.get("content_available") is False]
    if unavailable:
        assert all(DRIVE.match(n.get("drive_url") or "") for n in unavailable), (
            "a download-disabled deck was denied its Drive link")


def test_no_link_anywhere_points_at_the_mastersheet(g):
    """The sheet is the citation, never the destination."""
    bad = []
    for n in g["nodes"]:
        for v in _links(n):
            if SHEET_NAME in v.lower():
                bad.append((n["type"], n["label"], v[:60]))
    for e in g["edges"]:
        for k, v in e.items():
            if k.endswith(("_url", "_link")) and isinstance(v, str) \
                    and SHEET_NAME in v.lower():
                bad.append((e["rel"], k, v[:60]))
    assert not bad, f"{len(bad)} links point at the mastersheet: {bad[:3]}"


def test_every_link_is_http_and_of_a_known_kind(g):
    """Only validated http(s) reaches the UI — which is also what excludes the
    two `mailto:` hyperlink targets carrying personal addresses."""
    bad = []
    for n in g["nodes"]:
        for v in _links(n):
            if not HTTP.match(v):
                bad.append((n["label"], v[:40]))
            elif not (UPLEVEL.match(v) or DRIVE.match(v)):
                bad.append((n["label"], v[:40]))
    assert not bad, f"{len(bad)} links are neither Uplevel nor Drive: {bad[:3]}"


def test_no_link_is_a_mailto_or_any_other_scheme(g):
    blob = json.dumps(g)
    assert "mailto:" not in blob, "a mailto: target reached the graph"


def test_a_matched_session_artefact_carries_its_own_link(g):
    rel = tax.edge_for_role("module_session")
    att = [e for e in g["edges"] if e["rel"] == rel and e.get("attached_file")]
    assert att, "no session has a matched artefact; the join is not firing"
    bad = [e["attached_file"] for e in att
           if not DRIVE.match(e.get("attached_drive_url") or "")]
    assert not bad, f"{len(bad)} matched artefacts with no Drive link"


def test_every_topic_locator_can_open_its_source(g):
    rel = tax.edge_for_role("module_topic")
    edges = [e for e in g["edges"] if e["rel"] == rel]
    assert edges
    located = [e for e in edges
               if any(e.get(k) is not None for k in ("slide", "page", "tab"))]
    assert len(located) == len(edges), (
        f"{len(edges) - len(located)} topic edges carry no locator")
    bad = [e for e in located if not DRIVE.match(e.get("deck_drive_url") or "")]
    assert not bad, f"{len(bad)} topic edges cannot open their source file"


def test_hyperlink_targets_are_preferred_over_display_text():
    """37 cells in the workbook display one thing and link to another. The
    graph must carry the TARGET; a value-only read carried neither."""
    sheet = REPO / ".drive-cache" / "02-curriculum" / ms.SHEET_FILE
    if not sheet.exists():
        pytest.skip("corpus cache absent")
    total = 0
    for tab in ms.DOMAIN_TABS:
        mism = ms.link_mismatches(sheet, tab)
        total += len(mism)
        for cell in mism:
            assert "withheld" in cell.target or HTTP.match(cell.target)
    assert total > 0, "no mismatches found; the hyperlink read is not working"


def test_best_link_never_returns_display_text_or_a_non_http_scheme():
    assert ms.best_link("SD3: Backend Engineering",
                        "https://drive.google.com/x") == "https://drive.google.com/x"
    assert ms.best_link("someone@example.org", "mailto:someone@example.org") == ""
    assert ms.best_link("not a url", None) == ""
    assert ms.best_link("https://uplevel.interviewkickstart.com/a", None) == \
        "https://uplevel.interviewkickstart.com/a"
