"""D3: shortcuts are resolved and reported, never followed.

WHY THIS REVERSES RUNNING CODE
------------------------------
Until 2026-09-20 `00_fetch_drive.py:walk()` resolved a shortcut to its target
and, when the target was a folder, recursed into it. That is fine for a corpus
which is one folder owned by the B2C account — a shortcut there can only point
somewhere already controlled.

It is not fine for the scale-up. `docs/REGISTRY-INVENTORY.md` measured ~1 file
in 10 in the registry folders as a shortcut, and a shortcut's target may live
anywhere in Drive. Following them means **the corpus boundary is whatever a
third party linked to.**

Skipping them outright is the opposite error: four of the seven in the registry
are named like the most important documents in their folder
(`Embedded Software Engineering Curriculum`, `Embedded SW - Slides and
Documents`). So D3 records the pointer, fetches nothing, and **names** the ones
whose target the walk did not reach anyway.

Measured before the change: the existing corpus contains ZERO shortcuts, so
this removes nothing from it. The branch being replaced had never fired on real
data — the same shape as the export map (`test_export_map_is_exercised.py`).
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

FETCH = REPO / "pipeline" / "00_fetch_drive.py"

FOLDER = "application/vnd.google-apps.folder"
SHORTCUT = "application/vnd.google-apps.shortcut"
SHEET = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@pytest.fixture(scope="module")
def fetch_mod():
    spec = importlib.util.spec_from_file_location("np_fetch_drive", FETCH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _FakeDrive:
    """A tiny Drive. `tree` maps folder id -> list of child resources.

    Records every folder id it was asked to list, which is how "did the walk
    follow that shortcut?" is answered without inspecting the return value.
    """

    def __init__(self, tree):
        self.tree = tree
        self.listed: list[str] = []

    # -- the two-call shape googleapiclient uses -------------------------
    def files(self):
        return self

    def list(self, **kw):
        q = kw["q"]
        fid = q.split("'")[1]
        self.listed.append(fid)
        self._batch = {"files": list(self.tree.get(fid, []))}
        return self

    def execute(self):
        return self._batch


def _tree_with_a_shortcut_to_a_folder():
    return _FakeDrive({
        "root": [
            {"id": "f1", "name": "Real Folder", "mimeType": FOLDER},
            {"id": "sc1", "name": "Curriculum Link", "mimeType": SHORTCUT,
             "shortcutDetails": {"targetId": "outside",
                                 "targetMimeType": FOLDER}},
        ],
        "f1": [{"id": "a", "name": "A.xlsx", "mimeType": SHEET}],
        "outside": [{"id": "b", "name": "Outside.xlsx", "mimeType": SHEET}],
    })


def test_a_shortcut_to_a_folder_is_not_recursed_into(fetch_mod):
    """THE REVERSAL. The old code called walk() on the target."""
    drive = _tree_with_a_shortcut_to_a_folder()
    shortcuts: list = []
    entries = fetch_mod.walk(drive, "root", Path("."), set(), None, shortcuts)

    assert "outside" not in drive.listed, (
        "walk() listed the shortcut's target folder — it is still following "
        "shortcuts, which is the behaviour D3 reverses")
    names = {e["safe_name"] for e in entries}
    assert names == {"A.xlsx"}, (
        f"expected only the real file, got {names} — a file behind a shortcut "
        "reached the fetch list")


def test_the_shortcut_is_recorded_rather_than_dropped(fetch_mod):
    """Not following is only half of D3. Silence would be the other failure."""
    drive = _tree_with_a_shortcut_to_a_folder()
    shortcuts: list = []
    fetch_mod.walk(drive, "root", Path("."), set(), None, shortcuts)

    assert len(shortcuts) == 1, "the shortcut was dropped, not recorded"
    rec = shortcuts[0]
    assert rec["target_id"] == "outside"
    assert rec["target_mime"] == FOLDER
    assert "Curriculum Link" in rec["path"], (
        "the record must carry the path a human can act on")


def test_a_shortcut_to_a_file_does_not_become_a_fetchable_entry(fetch_mod):
    """The old code rewrote the entry's id/mime and fetched the target."""
    drive = _FakeDrive({
        "root": [
            {"id": "sc2", "name": "Handbook", "mimeType": SHORTCUT,
             "shortcutDetails": {"targetId": "t2", "targetMimeType": SHEET}},
        ],
    })
    shortcuts: list = []
    entries = fetch_mod.walk(drive, "root", Path("."), set(), None, shortcuts)

    assert entries == [], "a shortcut to a file still produced a fetch entry"
    assert len(shortcuts) == 1
    assert shortcuts[0]["target_id"] == "t2"


def test_a_shortcut_with_no_target_is_still_recorded(fetch_mod):
    """A broken shortcut is a finding, not a no-op.

    The old code did `if not target: continue` and moved on, so a shortcut
    whose target had been deleted left no trace at all.
    """
    drive = _FakeDrive({
        "root": [{"id": "sc3", "name": "Dangling", "mimeType": SHORTCUT,
                  "shortcutDetails": {}}],
    })
    shortcuts: list = []
    entries = fetch_mod.walk(drive, "root", Path("."), set(), None, shortcuts)

    assert entries == []
    assert len(shortcuts) == 1 and shortcuts[0]["target_id"] is None, (
        "a shortcut with no target vanished without a record")


def test_report_classifies_inside_and_outside_by_what_was_walked(fetch_mod, capsys):
    """DERIVED, NOT LISTED — instance 8.

    "Inside the declared tree" is membership of the ids this walk discovered,
    not a path prefix somebody maintains. A target that its own parent already
    delivered needs no action; anything else is named.
    """
    entries = [{"id": "a"}, {"id": "b"}]
    walked = {"root", "f1"}
    shortcuts = [
        {"path": "./dup", "shortcut_id": "s1", "target_id": "a",
         "target_mime": SHEET},                       # already in entries
        {"path": "./into-tree", "shortcut_id": "s2", "target_id": "f1",
         "target_mime": FOLDER},                      # a folder we walked
        {"path": "./elsewhere", "shortcut_id": "s3", "target_id": "zzz",
         "target_mime": SHEET},                       # genuinely outside
    ]
    outside = fetch_mod.report_shortcuts(shortcuts, entries, walked)

    assert [s["path"] for s in outside] == ["./elsewhere"]
    out = capsys.readouterr().out
    assert "3 found" in out and "2 resolve inside" in out
    assert "elsewhere" in out, "the outside shortcut must be named, not counted"
    assert "dup" not in out, (
        "a shortcut that duplicates a file already in the tree is noise; "
        "naming it would bury the one that matters (CLAUDE.md §5)")


def test_a_tree_with_no_shortcuts_reports_zero_and_stays_quiet(fetch_mod, capsys):
    """POSITIVE CONTROL. The corpus has zero shortcuts today.

    "Reports nothing because there are none" and "reports nothing because the
    classifier is broken" must not look the same — so the count line prints
    either way, and only the named list is conditional.
    """
    outside = fetch_mod.report_shortcuts([], [{"id": "a"}], {"root"})
    assert outside == []
    out = capsys.readouterr().out
    assert "SHORTCUTS: 0 found" in out, (
        "with no shortcuts the report went silent; absence and success must "
        "stay textually distinguishable (A7B)")
    assert "OUTSIDE" not in out
