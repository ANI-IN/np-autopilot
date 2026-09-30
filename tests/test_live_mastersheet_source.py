"""The live mastersheet is the source; the corpus copy is superseded.

Owner decision (Animesh Kumar, 2026-09-30, checklist review part 3): every
mastersheet-derived fact comes from the live Google Sheet; the corpus copy
stays in the graph, marked superseded, and is not read for those facts.
Runs on the committed graphs, so it holds in CI.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from pipeline.lib import graphio, mastersheet as ms, taxonomy          # noqa: E402

CONTENT = json.loads((REPO / "knowledge" / "content_graph.json").read_text(encoding="utf-8"))
CORPUS_COPY = ms.SUPERSEDED[0]["path"]
T_FILE = taxonomy.edge_endpoints(taxonomy.edge_for_role("provenance"))[1]
T_DOMAIN = taxonomy.edge_endpoints(taxonomy.edge_for_role("domain_module"))[0]


def _sources(g):
    for n in g["nodes"]:
        for s in n.get("sources") or []:
            yield n, s
    for e in g["edges"]:
        for s in e.get("sources") or []:
            yield e, s


def test_row_b_cites_the_live_sheet_and_never_the_corpus_copy():
    files = {s.get("file") for _, s in _sources(CONTENT)}
    assert ms.LIVE_CITATION in files
    assert CORPUS_COPY not in files, "a row-B fact still reads the superseded corpus copy"


def test_the_live_sheet_is_a_file_node_with_its_drive_link():
    n = [n for n in CONTENT["nodes"] if n["type"] == T_FILE
         and n.get("relative_path") == ms.LIVE_CITATION]
    assert len(n) == 1
    assert n[0]["drive_file_id"] == "1setMmRvBUNu9_85nT4xvvUFySodB6kiWb7bQ8qLEqAQ"
    assert n[0]["drive_url"].startswith("https://docs.google.com/spreadsheets/d/1setMm")


def test_the_corpus_copy_is_kept_and_marked_superseded():
    g = graphio.load_merged(include_sensitive=False)
    n = [n for n in g["nodes"] if n.get("relative_path") == CORPUS_COPY]
    assert len(n) == 1, "the superseded copy must stay in the graph"
    assert n[0]["superseded_by"] == ms.LIVE_CITATION
    assert g["meta"]["superseded_files"] == [CORPUS_COPY]


def test_every_domain_has_its_uplevel_link_from_uplevel_resources():
    doms = [n for n in CONTENT["nodes"] if n["type"] == T_DOMAIN]
    assert len(doms) == 4
    for d in doms:
        assert (d.get("uplevel_link") or "").startswith("https://uplevel.interviewkickstart.com/"), d["label"]
        assert any(s.get("sheet") == ms.UPLEVEL_TAB and s.get("file") == ms.LIVE_CITATION
                   for s in d["sources"]), d["label"]


def test_sd1_1_has_its_three_instructors():
    """The regression: `Week 1/5: Databases` was skipped for weeks."""
    N = {n["id"]: n for n in CONTENT["nodes"]}
    m = next(n for n in CONTENT["nodes"] if n["type"] == "module"
             and n.get("domain_slug") == "full-stack" and n.get("sequence") == 1)
    rel = taxonomy.edge_for_role("module_instructor")
    roles = sorted((e["instructor_role"], N[e["target"]]["label"]) for e in CONTENT["edges"]
                   if e["rel"] == rel and e["source"] == m["id"])
    assert roles == [("backup_1", "Ashish Kaila"), ("backup_2", "Nikhil Kolekar"),
                     ("primary", "Konstantinos Pappas")]


def test_the_exclusions_are_recorded_on_the_build():
    assert set(CONTENT["meta"]["mastersheet_excluded_tabs"]) == set(ms.EXCLUDED_TABS)
    assert CONTENT["meta"]["mastersheet_source"] == ms.LIVE_CITATION


def test_the_projection_registers_the_live_sheet_as_a_file():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "project_graph", REPO / "pipeline" / "project_graph.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    rows = {r[0]: r for r in mod._file_rows()}
    assert ms.LIVE_CITATION in rows
    assert rows[ms.LIVE_CITATION][5] == ms.LIVE_DRIVE_ID
