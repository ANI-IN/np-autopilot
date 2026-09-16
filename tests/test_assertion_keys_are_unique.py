"""AUDIT §A.4 — every source entry must be addressable by a unique key.

The planned Supabase schema gives each assertion a content-addressed id derived
from its provenance coordinates. That only works if the coordinates are unique,
and they were not:

    sourced_from edges                              32,656
    distinct (source, target, rel)                   6,230   -> 26,426 collisions
    distinct (node, file, sheet, row, column, page) 32,724   ->      6 collisions

All six were the same person listed twice in one row of a grid sheet.
`extract_pairings` shared one provenance object between the module and every
instructor on the row, with `column: None` — the coordinate that disambiguates
was being discarded at extraction.

Fixed at source (the real column is recorded) and again structurally (an
ordinal). Both, deliberately: a content hash that is 99.98% unique is one that
fails once a year on a row nobody is watching.
"""
from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

GRAPH = REPO / "knowledge" / "graph.json"

#: The assertion key. Mirrors ASSERTION_COORDS in 03_resolve.py plus the node.
COORDS = ("origin", "file", "sheet", "row", "column", "page",
          "within_cell", "ordinal")


@pytest.fixture(scope="module")
def graph():
    return json.loads(GRAPH.read_text(encoding="utf-8"))


def _keys(graph):
    return collections.Counter(
        (n["id"],) + tuple(s.get(k) for k in COORDS)
        for n in graph["nodes"] for s in n.get("sources", [])
    )


def test_every_assertion_key_is_unique(graph):
    keys = _keys(graph)
    total = sum(keys.values())
    collisions = {k: c for k, c in keys.items() if c > 1}
    assert not collisions, (
        f"{len(collisions)} assertion keys collide out of {total} entries. "
        "A content-addressed id cannot be derived from these coordinates.\n  "
        + "\n  ".join(repr(k) for k in list(collisions)[:5])
    )


def test_the_column_fix_alone_removes_the_collisions(graph):
    """The ordinal is insurance, not the fix. Prove the source fix is real.

    If this ever fails while the test above passes, the ordinal has started
    papering over a genuine extraction gap.
    """
    without_ordinal = collections.Counter(
        (n["id"],) + tuple(s.get(k) for k in COORDS if k not in ("ordinal", "within_cell"))
        for n in graph["nodes"] for s in n.get("sources", [])
    )
    collisions = sum(c - 1 for c in without_ordinal.values() if c > 1)
    assert collisions == 0, (
        f"{collisions} collisions remain once the ordinal is removed — the "
        "extractor is still discarding a coordinate and the ordinal is hiding it"
    )


def test_grid_sourced_entries_record_a_column(graph):
    """The specific regression: the grid extractor dropped the column."""
    grid_file = "03-instructors/AgenticAI Instructors Training Plan.xlsx"
    grid_rows = [s for n in graph["nodes"] for s in n.get("sources", [])
                 if s.get("file") == grid_file and s.get("sheet") == "M_SME_App. GenAI"]
    assert grid_rows, "no entries from the grid sheet that produced the collisions"
    missing = [s for s in grid_rows if s.get("column") is None]
    assert not missing, (
        f"{len(missing)} grid-sourced entries still have no column"
    )


def test_every_source_entry_carries_an_ordinal(graph):
    """Uniform, so the key needs no 'missing means zero' special case."""
    missing = [(n["type"], n["label"]) for n in graph["nodes"]
               for s in n.get("sources", []) if "ordinal" not in s]
    assert not missing, f"{len(missing)} source entries have no ordinal, e.g. {missing[:3]}"


def test_duplicate_triples_are_still_present_and_legitimate(graph):
    """The duplicates are CORRECT and must survive — they are not the bug.

    sourced_from emits one edge per cited row, and expert_in asserts the same
    pair twice with different `basis`. Collapsing either would lose evidence
    /staffing exists to keep apart.
    """
    from pipeline.lib import taxonomy
    triples = collections.Counter(
        (e["source"], e["target"], e["rel"]) for e in graph["edges"])
    dupes = sum(c - 1 for c in triples.values() if c > 1)
    assert dupes > 0, "duplicate triples vanished — evidence has been merged away"

    expert = taxonomy.edge_for_role("instructor_domain")
    ei = [e for e in graph["edges"] if e["rel"] == expert]
    with_basis = collections.Counter(
        (e["source"], e["target"], e.get("basis")) for e in ei)
    assert not [k for k, c in with_basis.items() if c > 1], (
        "expert_in collides even with basis — the evidence classes have merged"
    )
