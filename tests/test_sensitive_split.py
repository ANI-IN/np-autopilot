"""DECISIONS §F.2 — the sensitive half must never be committable.

graph.json ships with the plugin and lives in git history. A personal repo has
no read-only tier, so adding a collaborator grants them everything in it,
permanently. Under the Q3 two-role decision the 277 hiring rejections and 1,625
in-pipeline candidates are `recruiting` data and the collaborators are not
cleared for it.

The split is only cheap because of a fact about the data: every sensitive node
carries ONLY provenance edges — zero teaches, zero expert_in — so withholding
them costs no teaching or expertise evidence and /staffing answers identically.
That fact is asserted here, not assumed. A future change that gives a rejected
candidate a teaching edge makes the split expensive, and it must not do so
quietly.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from pipeline.lib import graphio, taxonomy                              # noqa: E402

PUBLIC = REPO / "knowledge" / "graph.json"
SENSITIVE = REPO / "knowledge" / "graph-sensitive.json"


@pytest.fixture(scope="module")
def public():
    return json.loads(PUBLIC.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# it must not be committable
# --------------------------------------------------------------------------

def test_the_sensitive_half_is_gitignored():
    r = subprocess.run(["git", "check-ignore", "-v", "knowledge/graph-sensitive.json"],
                       cwd=REPO, capture_output=True, text=True)
    assert r.returncode == 0, (
        "knowledge/graph-sensitive.json is NOT ignored — `git add -A` would "
        "commit 277 hiring rejections about named external people"
    )


def test_the_sensitive_half_is_not_tracked():
    r = subprocess.run(["git", "ls-files", "knowledge/graph-sensitive.json"],
                       cwd=REPO, capture_output=True, text=True)
    assert not r.stdout.strip(), "the sensitive half is tracked by git"


def test_no_sensitive_node_is_in_the_committed_file(public):
    leaked = [n["label"] for n in public["nodes"] if n.get("sensitive")]
    assert not leaked, (
        f"{len(leaked)} sensitive nodes are in the committed graph, "
        f"e.g. {leaked[:3]}"
    )


def test_no_rejected_or_in_pipeline_status_survives_in_public(public):
    statuses = {n.get("pipeline_status") for n in public["nodes"]}
    assert "rejected" not in statuses
    assert "in_pipeline" not in statuses


# --------------------------------------------------------------------------
# the split must not be lossy where it matters
# --------------------------------------------------------------------------

def test_withholding_costs_no_teaching_or_expertise_evidence():
    """The fact that makes the split free. Asserted, not assumed."""
    g = graphio.load_graph()
    sensitive_ids = {n["id"] for n in g["nodes"] if n.get("sensitive")}
    evidence = {taxonomy.edge_for_role("instructor_module"),
                taxonomy.edge_for_role("instructor_domain")}
    lost = [e for e in g["edges"]
            if e["rel"] in evidence
            and (e["source"] in sensitive_ids or e["target"] in sensitive_ids)]
    assert not lost, (
        f"{len(lost)} evidence edges now touch a sensitive node. The split is no "
        "longer free: /staffing will answer differently for someone holding both "
        "halves than for someone holding only the public file. Decide "
        "deliberately before shipping this."
    )


def test_the_public_file_has_no_dangling_edge(public):
    ids = {n["id"] for n in public["nodes"]}
    dangling = [e for e in public["edges"]
                if e["source"] not in ids or e["target"] not in ids]
    assert not dangling, (
        f"{len(dangling)} edges in the public file point at withheld nodes"
    )


def test_the_union_reassembles_the_whole_graph(public):
    if not SENSITIVE.exists():
        pytest.skip("no sensitive half on this machine")
    sens = json.loads(SENSITIVE.read_text(encoding="utf-8"))
    union = graphio.load_graph()
    assert len(union["nodes"]) == len(public["nodes"]) + len(sens["nodes"])
    assert len(union["edges"]) == len(public["edges"]) + len(sens["edges"])
    assert union["meta"]["sensitive_loaded"] is True


def test_loading_without_the_sensitive_half_still_works(tmp_path):
    """A collaborator's clone, or the plugin cache. Smaller, not broken."""
    target = tmp_path / "graph.json"
    target.write_text(PUBLIC.read_text(encoding="utf-8"), encoding="utf-8")
    g = graphio.load_graph(target)
    assert g["meta"]["sensitive_loaded"] is False
    ids = {n["id"] for n in g["nodes"]}
    assert not [e for e in g["edges"]
                if e["source"] not in ids or e["target"] not in ids]


# --------------------------------------------------------------------------
# the reader must be told what they are missing
# --------------------------------------------------------------------------

def test_the_public_file_declares_what_was_withheld(public):
    w = public["meta"].get("withheld")
    assert w, "the public graph does not say anything was withheld"
    assert w["nodes"] > 0 and w["edges"] > 0
    assert "recruiting" in w["reason"] or "sensitive" in w["reason"]
    assert w["file"] == SENSITIVE.name


def test_the_generated_readme_block_names_the_withheld_count(public):
    text = (REPO / "README.md").read_text(encoding="utf-8")
    block = text.split("<!-- generated:counts -->", 1)[1].split("<!-- /generated", 1)[0]
    w = public["meta"]["withheld"]
    assert f"{w['nodes']:,}" in block, (
        "README reports counts without saying how many records are withheld, so "
        "a reader cannot tell their graph is a subset"
    )


def test_the_content_hash_covers_both_halves():
    """A change confined to the withheld half must still force a version bump."""
    g = graphio.load_graph()
    before = graphio.content_hash(g)
    g["nodes"] = [dict(n, label=n["label"] + "!") if n.get("sensitive") else n
                  for n in g["nodes"]]
    assert graphio.content_hash(g) != before, (
        "editing a withheld node does not change the content hash, so it would "
        "ship without a version bump"
    )


def test_the_hash_is_order_independent():
    """The union is assembled from two files; load order is not content."""
    g = graphio.load_graph()
    shuffled = {"nodes": list(reversed(g["nodes"])),
                "edges": list(reversed(g["edges"]))}
    assert graphio.content_hash(g) == graphio.content_hash(shuffled)
