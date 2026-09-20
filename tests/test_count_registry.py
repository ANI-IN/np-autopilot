"""The registry crawler counts and stops, and can prove it counted everything.

`REGISTRY-INVENTORY.md` was a floor and said so. This pass is supposed to be a
count, and "we enumerated everything" is exactly the kind of claim that is
comfortable to make and hard to check — so each of the three ways
exhaustiveness breaks silently gets a test that breaks it.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from pipeline import count_registry as cr          # noqa: E402

FOLDER = cr.FOLDER_MIME
SHORTCUT = cr.SHORTCUT_MIME
SHEET = "application/vnd.google-apps.spreadsheet"
DECK = "application/vnd.google-apps.presentation"


# --------------------------------------------------------------------------
# It counts. It does not fetch.
# --------------------------------------------------------------------------

def test_the_counter_cannot_fetch_anything():
    """A counting tool that can fetch is one flag away from an ingester.

    Static, over the module's own AST, because the claim in the docstring —
    "nothing is fetched" — is otherwise enforced by nobody. This is the
    instance-9 question asked of a sentence in a file I wrote today.
    """
    tree = ast.parse((REPO / "pipeline" / "count_registry.py").read_text())
    called = {n.func.attr for n in ast.walk(tree)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
    for verb in ("get_media", "export_media", "MediaIoBaseDownload"):
        assert verb not in called, (
            f"count_registry calls {verb} — it downloads bytes, and this pass "
            "exists to produce a number before anything is committed to")
    assert "list" in called and "get" in called, (
        "the metadata verbs are gone; this test is no longer checking anything")


# --------------------------------------------------------------------------
# 1 · Pagination
# --------------------------------------------------------------------------

class _PagedDrive:
    """Serves a folder's children across several pages."""

    def __init__(self, pages, fail_on_page=None):
        self.pages, self.fail_on_page = pages, fail_on_page
        self.calls = 0

    def files(self):
        return self

    def list(self, **kw):
        self._token = kw.get("pageToken")
        return self

    def get(self, **kw):
        self._token = "__get__"
        return self

    def execute(self):
        if self._token == "__get__":
            return {"name": "x", "owners": [{"emailAddress": "a@b.com"}]}
        idx = 0 if self._token is None else int(self._token)
        self.calls += 1
        if self.fail_on_page is not None and idx == self.fail_on_page:
            from googleapiclient.errors import HttpError

            class _R:
                status = 403
                reason = "Forbidden"
            raise HttpError(_R(), b'{"error":{"message":"nope"}}', uri="u")
        out = {"files": self.pages[idx]}
        if idx + 1 < len(self.pages):
            out["nextPageToken"] = str(idx + 1)
        return out


def test_every_page_is_followed_to_a_terminal_page():
    """The (File responses) listing stopped at 60 with a token outstanding.

    A reader that takes the first page reports a partial listing as complete.
    """
    pages = [[{"id": f"f{i}", "name": f"{i}.xlsx", "mimeType": SHEET}
              for i in range(p * 3, p * 3 + 3)] for p in range(4)]
    c = cr.Crawler(_PagedDrive(pages))
    got = c.list_all("root")
    assert len(got) == 12, f"only {len(got)} of 12 children across 4 pages"
    assert c.pages_total == 4


def test_a_listing_that_cannot_finish_raises_instead_of_returning_partial():
    """THE NEGATIVE CONTROL for pagination.

    Returning what was collected so far is precisely how a partial listing
    becomes a reported total. Page 0 succeeds, page 1 fails: the three items
    from page 0 must NOT come back.
    """
    from googleapiclient.errors import HttpError

    pages = [[{"id": "a", "name": "a.xlsx", "mimeType": SHEET}] * 3,
             [{"id": "b", "name": "b.xlsx", "mimeType": SHEET}]]
    c = cr.Crawler(_PagedDrive(pages, fail_on_page=1))
    with pytest.raises(HttpError):
        c.list_all("root")


def test_a_folder_whose_listing_failed_is_not_counted_as_opened():
    """A failure must subtract from `opened`, or coverage lies.

    This is the arithmetic the whole report rests on: if a failed folder stayed
    in `opened`, "every discovered folder was opened" would print while a
    subtree was missing.
    """
    c = cr.Crawler(_PagedDrive([[]], fail_on_page=0))
    c.discovered.add("root")
    c.walk("root", "R", 0)
    assert "root" not in c.opened, "a folder that failed to list was counted as opened"
    assert len(c.failures) == 1
    assert c.failures[0]["kind"] == "folder-listing"
    assert c.discovered - c.opened == {"root"}, (
        "the folder must remain discovered-but-not-opened, so the report can "
        "name it")


# --------------------------------------------------------------------------
# 2 · Cycles and repeats
# --------------------------------------------------------------------------

class _TreeDrive:
    def __init__(self, tree):
        self.tree, self.listed = tree, []

    def files(self):
        return self

    def list(self, **kw):
        self._fid = kw["q"].split("'")[1]
        self.listed.append(self._fid)
        self._mode = "list"
        return self

    def get(self, **kw):
        self._fid, self._mode = kw["fileId"], "get"
        return self

    def execute(self):
        if self._mode == "get":
            return {"id": self._fid, "name": f"target-{self._fid}",
                    "mimeType": SHEET,
                    "owners": [{"emailAddress": "someone@example.org"}]}
        return {"files": list(self.tree.get(self._fid, []))}


def test_a_folder_reachable_by_two_paths_is_walked_once_and_recorded_twice():
    """"5 files" and "5 files counted twice" must not look the same."""
    drive = _TreeDrive({
        "root": [{"id": "shared", "name": "Shared", "mimeType": FOLDER},
                 {"id": "b", "name": "B", "mimeType": FOLDER}],
        "b": [{"id": "shared", "name": "Shared", "mimeType": FOLDER}],
        "shared": [{"id": "x", "name": "x.xlsx", "mimeType": SHEET}],
    })
    c = cr.Crawler(drive)
    c.discovered.add("root")
    c.walk("root", "R", 0)

    assert drive.listed.count("shared") == 1, "the shared subtree was walked twice"
    assert len(c.files) == 1, f"file counted {len(c.files)} times, expected once"
    assert len(c.repeats) == 1, "the second encounter was dropped, not recorded"
    assert c.repeats[0]["first_seen"] == "R/Shared"
    assert c.repeats[0]["again_at"] == "R/B/Shared"


# --------------------------------------------------------------------------
# 3 · D3 / D6 / D4
# --------------------------------------------------------------------------

def test_shortcuts_are_recorded_and_classified_but_never_walked():
    drive = _TreeDrive({
        "root": [
            {"id": "real", "name": "Real", "mimeType": FOLDER},
            {"id": "s1", "name": "Points inside", "mimeType": SHORTCUT,
             "shortcutDetails": {"targetId": "inside_file",
                                 "targetMimeType": SHEET}},
            {"id": "s2", "name": "Points away", "mimeType": SHORTCUT,
             "shortcutDetails": {"targetId": "elsewhere",
                                 "targetMimeType": FOLDER}},
        ],
        "real": [{"id": "inside_file", "name": "in.xlsx", "mimeType": SHEET}],
        "elsewhere": [{"id": "zz", "name": "zz.xlsx", "mimeType": SHEET}],
    })
    c = cr.Crawler(drive)
    c.discovered.add("root")
    c.walk("root", "R", 0)
    c.classify_shortcuts()

    assert "elsewhere" not in drive.listed, "a shortcut target folder was walked"
    assert {s["verdict"] for s in c.shortcuts} == {"inside", "outside"}
    assert len(c.files) == 1, "a file behind a shortcut was counted"


def test_file_responses_folders_are_skipped_by_name_and_reported():
    drive = _TreeDrive({
        "root": [{"id": "fr", "name": "Capstone (File responses)",
                  "mimeType": FOLDER},
                 {"id": "ok", "name": "Slides", "mimeType": FOLDER}],
        "fr": [{"id": "big", "name": "learner.zip",
                "mimeType": "application/zip", "size": "999999999"}],
        "ok": [{"id": "d", "name": "deck", "mimeType": DECK}],
    })
    c = cr.Crawler(drive)
    c.discovered.add("root")
    c.walk("root", "R", 0)

    assert "fr" not in drive.listed, "the responses folder was descended into"
    assert len(c.skipped_responses) == 1
    assert c.skipped_responses[0]["path"] == "R/Capstone (File responses)"
    assert [f["path"] for f in c.files] == ["R/Slides/deck"]
    assert "fr" in c.discovered - c.opened, (
        "a skipped folder must stay discovered-but-not-opened so the coverage "
        "line accounts for it rather than pretending it does not exist")


def test_the_skip_is_declared_not_a_size_threshold():
    """D6's whole argument. A size cap would also drop a 17.66 MB deck."""
    src = (REPO / "pipeline" / "count_registry.py").read_text()
    assert "RESPONSES_RE" in src
    assert not any(t in src for t in ("MAX_SIZE", "size_limit", "SIZE_CAP")), (
        "a size threshold appeared; D6 is a declared skip by name precisely so "
        "that a large legitimate file is never dropped by the same rule")


def test_owner_is_recorded_as_a_domain_never_an_address():
    """D4, and the assertion the decision specified."""
    assert cr.owner_domain(
        {"owners": [{"emailAddress": "Someone.Real@Gmail.com"}]}) == "gmail.com"
    assert cr.owner_domain({}) == "unknown"
    assert cr.owner_domain({"owners": [{"emailAddress": "broken"}]}) == "unknown"

    drive = _TreeDrive({"root": [
        {"id": "f", "name": "f.xlsx", "mimeType": SHEET,
         "owners": [{"emailAddress": "person@interviewkickstart.com"}]}]})
    c = cr.Crawler(drive)
    c.discovered.add("root")
    c.walk("root", "R", 0)
    blob = repr(c.files)
    assert "interviewkickstart.com" in blob
    assert "@" not in blob, (
        "an address reached a stored record; D4 is that provenance carries the "
        "domain and never the identifier")


# --------------------------------------------------------------------------
# Coverage arithmetic — the claim that turns a floor into a count
# --------------------------------------------------------------------------

def test_a_clean_walk_leaves_nothing_discovered_but_unopened():
    drive = _TreeDrive({
        "root": [{"id": "a", "name": "A", "mimeType": FOLDER}],
        "a": [{"id": "b", "name": "B", "mimeType": FOLDER}],
        "b": [{"id": "f", "name": "f.xlsx", "mimeType": SHEET}],
    })
    c = cr.Crawler(drive)
    c.discovered.add("root")
    depth = c.walk("root", "R", 0)
    assert c.discovered == c.opened, (
        "discovered and opened diverged on a tree with no skips or failures")
    assert depth == 2, f"max depth {depth}, expected 2"
    assert len(c.files) == 1
