"""Corroboration is counted over a merged instructor's aliases and sources.

Owner review 2026-09-30: the panel said "named in one file only" for Robert
Kreznarich and Konstantinos Pappas. Both are identity merges; the node that
survives a merge is the lowest id, which was pass 7's (cross_validated=False,
no file count), and nothing recounted after the sources were unioned.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from pipeline.lib import graphio, mastersheet, module_merge            # noqa: E402

#: name -> the distinct source files the merged node must be counted over
#: (the corpus mastersheet copy and the live sheet are one workbook).
EXPECTED = {
    "Robert Kreznarich": {
        "03-instructors/Instructors Directory.xlsx",
        "05-operations/New Combined Schedule.xlsx",
        mastersheet.LIVE_CITATION,
    },
    "Konstantinos Pappas": {
        "03-instructors/Instructors Directory.xlsx",
        "03-instructors/SME Tracker - Bullseye_IK.xlsx",
        "03-instructors/SME_Interview_Demo Audit Rubrics.xlsx",
        "05-operations/New Combined Schedule.xlsx",
        mastersheet.LIVE_CITATION,
    },
}


@pytest.fixture(scope="module")
def merged():
    try:
        return graphio.load_merged()
    except FileNotFoundError as exc:            # CI without the built graphs
        pytest.skip(f"merged graph not available: {exc}")


def _node(g, name):
    hits = [n for n in g["nodes"] if n["type"] == "instructor" and n["label"] == name]
    assert len(hits) == 1, f"{name}: {len(hits)} instructor nodes"
    return hits[0]


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_a_merged_instructor_is_corroborated_over_all_its_sources(merged, name):
    n = _node(merged, name)
    assert n.get("merged_from"), f"{name} is no longer a merge; this test needs a new example"
    assert n["cross_validated"] is True
    assert n["file_count"] == len(EXPECTED[name])


def test_the_mastersheet_and_its_live_copy_count_once():
    """A name found only in the mastersheet is named in ONE workbook, even
    though the corpus copy and the live export are two paths."""
    sup = mastersheet.SUPERSEDED[0]["path"]
    main = {"meta": {}, "nodes": [{
        "id": "ins_a", "type": "instructor", "label": "Only In The Sheet",
        "sources": [{"file": sup}, {"file": mastersheet.LIVE_CITATION}]}], "edges": []}
    out = module_merge.merge(main, {"meta": {}, "nodes": [], "edges": []},
                             spec={"merges": []}, identities={})
    n = _node(out, "Only In The Sheet")
    assert n["file_count"] == 1 and n["cross_validated"] is False


def test_the_count_follows_the_merge_not_the_survivor():
    """Two spellings, one file each, merged: two files, corroborated — whatever
    the surviving node said before (pass 7 writes False)."""
    main = {"meta": {}, "nodes": [
        {"id": "ins_1", "type": "instructor", "label": "Ada L", "cross_validated": False,
         "sources": [{"file": "05-operations/New Combined Schedule.xlsx"}]},
        {"id": "ins_2", "type": "instructor", "label": "Ada Lovelace", "cross_validated": False,
         "sources": [{"file": "03-instructors/Instructors Directory.xlsx"}]}], "edges": []}
    ids = {"identities": [{"status": "confirmed", "canonical": "Ada Lovelace",
                           "aliases": ["Ada L"], "slug": "ada", "resolves": ["INS-T"]}]}
    out = module_merge.merge(main, {"meta": {}, "nodes": [], "edges": []},
                             spec={"merges": []}, identities=ids)
    n = _node(out, "Ada Lovelace")
    assert n["file_count"] == 2 and n["cross_validated"] is True
