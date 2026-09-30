"""Every file and every current module and domain carries its link (B4 (i)).

Owner requirement, 2026-09-30: every file node has an Open link; every current
(mastersheet) module and domain has its Drive folder link; every module and
session has its Uplevel link; a session with no folder SAYS so. Holds on the
committed graphs, so it runs in CI.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from pipeline.lib import folder_links as fl, graphio, taxonomy          # noqa: E402

T_FILE = taxonomy.edge_endpoints(taxonomy.edge_for_role("provenance"))[1]
T_SESSION = taxonomy.edge_endpoints(taxonomy.edge_for_role("module_session"))[1]


@pytest.fixture(scope="module")
def g():
    return graphio.load_merged(include_sensitive=False)


def test_every_file_node_has_an_open_link(g):
    missing = [n["label"] for n in g["nodes"] if n["type"] == T_FILE and not n.get("drive_url")]
    assert not missing, f"{len(missing)} file nodes have no Open link, e.g. {missing[:3]}"


def test_every_current_module_has_its_drive_folder_and_uplevel_link(g):
    mods = [n for n in g["nodes"] if n["type"] == "module" and n.get("domain_slug")]
    assert len(mods) == 20
    assert not [n["label"] for n in mods if not n.get("drive_folders")]
    assert not [n["label"] for n in mods if not n.get("uplevel_link")]
    assert all(f["url"].startswith(fl.FOLDER_URL.format("")) for n in mods
               for f in n["drive_folders"])


def test_every_current_domain_has_its_drive_folder_and_uplevel_link(g):
    doms = [n for n in g["nodes"] if n["type"] == "domain" and n.get("uplevel_link")]
    assert len(doms) == 4
    assert all(n.get("drive_folder_url") for n in doms)


def test_every_session_has_an_uplevel_link_and_an_answer_about_its_folder(g):
    ses = [n for n in g["nodes"] if n["type"] == T_SESSION]
    assert ses
    assert not [n["label"] for n in ses if not n.get("uplevel_link")]
    # a list, possibly EMPTY: empty is an answer ("No folder for this session");
    # a missing key would mean nobody looked
    assert not [n["label"] for n in ses if not isinstance(n.get("drive_folders"), list)]


def test_the_checklist_shows_the_counts_and_says_no_folder_in_words():
    text = (REPO / "docs" / "ACCEPTANCE-CHECKLIST.md").read_text(encoding="utf-8")
    assert "**Links**" in text and "file nodes — Open link" in text
    assert "No folder for this session" in text
    assert "missing — a defect" not in text


# --- the matching rules, on synthetic folders -------------------------------

def _folders():
    F = {}
    def add(fid, path, parent):
        F[fid] = {"name": path.rsplit("/", 1)[-1], "path": path, "parent": parent}
    add("d", "/SD3: Backend Engineering", "root")
    add("m", "/SD3: Backend Engineering/Module-3: API Design", "d")
    add("c1", "/SD3: Backend Engineering/Module-3: API Design/1. Foundational Material", "m")
    add("c2", "/SD3: Backend Engineering/Module-3: API Design/2. Live Class Slides", "m")
    add("c3", "/SD3: Backend Engineering/Module-3: API Design/3. Assignments", "m")
    add("c4", "/SD3: Backend Engineering/Module-3: API Design/Revamp 2024", "m")
    add("u", "/SD3: Backend Engineering/Module-1: Database Design/Uplevel shared/Week 3/5 - API Design", "x")
    add("u1", "/SD3: Backend Engineering/Module-1: Database Design/Uplevel shared/Week 3/5 - API Design/Slides", "u")
    return F


def test_module_folders_are_content_first_then_uplevel_shared():
    mods = fl.module_folders(_folders())
    assert [e["where"] for e in mods[("SD3: Backend Engineering", 3)]] == ["content", "uplevel shared"]


def test_session_folders_match_by_name_and_never_guess():
    s = fl.session_folders(_folders())
    k = ("SD3: Backend Engineering", 3)
    assert [e["name"] for e in s[(*k, "class")]] == ["2. Live Class Slides", "Slides"]
    assert [e["name"] for e in s[(*k, "task")]] == ["3. Assignments"]
    assert [e["name"] for e in s[(*k, "pre_class")]] == ["1. Foundational Material"]
    assert (*k, "post_class") not in s, "no practice-problems folder: no link, not a guess"
    assert (*k, "review") not in s
    assert not any(e["name"] == "Revamp 2024" for v in s.values() for e in v)


def test_public_entries_carry_no_internal_id():
    entries = fl.module_folders(_folders())[("SD3: Backend Engineering", 3)]
    assert all(set(e) == {"url", "name", "where"} for e in fl.public(entries))
