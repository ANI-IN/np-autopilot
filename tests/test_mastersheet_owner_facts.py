"""config/mastersheet-owner-facts.yaml — a role the owner withdrew.

SD1/4 Backup 3 `Daniel Grundel` is red-highlighted in the sheet; the owner
says he no longer teaches it (Animesh Kumar, 2026-09-30). Pass 7 drops that
one mastersheet edge, keeps his node, and records WHY as a hand source.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from pipeline.lib import mastersheet as ms, taxonomy                  # noqa: E402

CONTENT = REPO / "knowledge" / "content_graph.json"
R_INS = taxonomy.edge_for_role("module_instructor")


@pytest.fixture(scope="module")
def g():
    return json.loads(CONTENT.read_text(encoding="utf-8"))


def test_the_fact_is_an_owner_fact():
    facts = ms.withdrawn_roles()
    key = ("full-stack", 4, "backup_3", "Daniel Grundel")
    assert key in facts
    f = facts[key]
    assert f["origin"] == "hand" and f["asserted_by"] and f["asserted_at"] == "2026-09-30"


def test_the_edge_is_gone_and_the_node_is_kept(g):
    N = {n["id"]: n for n in g["nodes"]}
    daniel = [n for n in g["nodes"] if n["label"] == "Daniel Grundel"]
    assert daniel, "withdrawing a role must not delete the person"
    fs4 = next(n for n in g["nodes"] if n["type"] == "module"
               and n.get("domain_slug") == "full-stack" and n.get("sequence") == 4)
    roles = [(e.get("instructor_role"), N[e["target"]]["label"]) for e in g["edges"]
             if e["rel"] == R_INS and e["source"] == fs4["id"]]
    assert ("backup_3", "Daniel Grundel") not in roles
    assert roles, "the module's other roles must remain"


def test_why_is_recorded_as_a_hand_source_that_names_no_file(g):
    d = next(n for n in g["nodes"] if n["label"] == "Daniel Grundel")
    assert d.get("withdrawn_roles")
    hand = [s for s in d.get("sources") or [] if s.get("origin") == "hand"
            and "withdrawn_roles" in (s.get("establishes") or [])]
    assert hand and all("file" not in s for s in hand)
    assert "Full Stack Engineering!E50" in hand[0]["evidence"]


def test_every_other_red_cell_is_reported_not_acted_on(g):
    assert g["meta"]["mastersheet_withdrawn_roles"] == ["sd1-4-daniel-grundel-backup-3"]
    assert g["meta"]["mastersheet_red_cells_unexplained"] == []


@pytest.mark.parametrize("drop", ["origin", "asserted_by", "fact"])
def test_an_incomplete_fact_is_refused(tmp_path, monkeypatch, drop):
    data = yaml.safe_load(ms.OWNER_FACTS.read_text(encoding="utf-8"))
    data["withdrawn_roles"][0].pop(drop)
    p = tmp_path / "facts.yaml"
    p.write_text(yaml.safe_dump(data), encoding="utf-8")
    monkeypatch.setattr(ms, "OWNER_FACTS", p)
    with pytest.raises(AssertionError):
        ms.withdrawn_roles()


def test_red_detection_on_the_real_sheet():
    path = REPO / ".drive-cache" / "02-curriculum" / ms.SHEET_FILE
    if not path.exists():
        pytest.skip("the corpus cache is absent; run pipeline/00_fetch_drive.py")
    red = ms.red_cells(path, "Full Stack Engineering")
    assert "Daniel Grundel" in {str(v).strip() for v in red.values()}
