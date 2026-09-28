"""The row-B content crawler's own contracts, against a fake Drive.

Separate from `test_content_crawl_guards.py` on purpose: that file tests the
DECISIONS, this one tests that the crawler actually applies them and that its
cache and manifest behave. A guard that is correct and never called is
`docs/A7B.md`'s "control that never worked" — so every rule proved in the
guard file is also asserted here at the point it is used.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

CRAWLER = REPO / "pipeline" / "06_crawl_content.py"

FOLDER = "application/vnd.google-apps.folder"
SHORTCUT = "application/vnd.google-apps.shortcut"
DOC = "application/vnd.google-apps.document"
SLIDES = "application/vnd.google-apps.presentation"
MP4 = "video/mp4"

#: What D2a's approval block ticks. Passed explicitly by every caller.
APPROVED = ["SD3: Backend Engineering"]


@pytest.fixture(scope="module")
def mod():
    spec = importlib.util.spec_from_file_location("np_crawl_content", CRAWLER)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class _FakeDrive:
    """Records every id it was asked to list, export or download.

    Those three lists are how "did the crawler follow that shortcut / download
    that video / open that folder" is answered without inspecting a return
    value — the same technique as tests/test_shortcuts_are_not_followed.py.
    """

    def __init__(self, tree, blobs):
        self.tree, self.blobs = tree, blobs
        self.listed, self.exported, self.downloaded = [], [], []

    # -- the googleapiclient surface the crawler uses -----------------------
    def files(self):
        return self

    def list(self, **kw):
        q = kw["q"]
        fid = q.split("'")[1]
        self.listed.append(fid)
        return _Resp({"files": list(self.tree.get(fid, []))})

    def get(self, **kw):
        return _Resp({"id": kw["fileId"], "name": "root", "mimeType": FOLDER})

    def export(self, **kw):
        self.exported.append(kw["fileId"])
        return _Resp(self.blobs.get(kw["fileId"], b""), raw=True)

    def get_media(self, **kw):
        self.downloaded.append(kw["fileId"])
        return _Resp(self.blobs.get(kw["fileId"], b""), raw=True)


class _Resp:
    def __init__(self, payload, raw=False):
        self._p, self._raw = payload, raw

    def execute(self):
        return self._p


def _f(i, name, mime, **kw):
    d = {"id": i, "name": name, "mimeType": mime, "modifiedTime": "2026-01-01T00:00:00Z"}
    d.update(kw)
    return d


@pytest.fixture
def world():
    """One domain, one module, one of every decision."""
    tree = {
        "ROOT": [_f("dom", "SD3: Backend Engineering", FOLDER),
                 _f("other", "Sys3: Embedded Software Engineering", FOLDER)],
        "dom": [_f("mod", "Module-1: Database Design", FOLDER)],
        "mod": [_f("doc1", "Database Design: Assignment", DOC),
                _f("deck1", "Database Design Live Class", SLIDES),
                _f("vid1", "databaseoverview.mp4", MP4, size="9999999"),
                _f("resp", "Assignment Submission Form (File responses)", FOLDER),
                _f("sc1", "Backend SME Links", SHORTCUT,
                   shortcutDetails={"targetId": "elsewhere", "targetMimeType": FOLDER})],
        "resp": [_f("learner", "student-upload.zip", "application/zip")],
        "elsewhere": [_f("secret", "outside-the-registry.doc", DOC)],
    }
    blobs = {
        "doc1": b"Email ops@interviewkickstart.com about the DB assignment.",
        "deck1": b"Slide 1: normalisation. Slide 2: BCNF.",
    }
    return _FakeDrive(tree, blobs)


# ---------------------------------------------------------------------------

def test_the_cache_goes_in_its_own_subdirectory(mod, tmp_path, world):
    out = mod.crawl(world, "ROOT", tmp_path, approved_domains=APPROVED)
    assert out.cache_dir.name == mod.CACHE_SUBDIR
    assert out.cache_dir.parent == tmp_path


def test_the_crawler_never_writes_outside_its_own_subdirectory(mod, tmp_path, world):
    """CLAUDE.md §1: the corpus is read-only, and `.drive-cache/` already holds
    the 75-file corpus. A content crawl must not be able to touch it."""
    (tmp_path / "00-master").mkdir()
    sentinel = tmp_path / "00-master" / "Domains_Courses Owners.xlsx"
    sentinel.write_bytes(b"CORPUS")
    mod.crawl(world, "ROOT", tmp_path, approved_domains=APPROVED)
    assert sentinel.read_bytes() == b"CORPUS"
    written = {p for p in tmp_path.rglob("*") if p.is_file()}
    assert all(mod.CACHE_SUBDIR in p.parts or p == sentinel for p in written)


def test_the_manifest_records_modified_time_and_sha256(mod, tmp_path, world):
    out = mod.crawl(world, "ROOT", tmp_path, approved_domains=APPROVED)
    entry = out.manifest["doc1"]
    assert entry["modifiedTime"] == "2026-01-01T00:00:00Z"
    assert len(entry["sha256"]) == 64


def test_a_second_run_with_an_unchanged_manifest_exports_nothing(mod, tmp_path, world):
    mod.crawl(world, "ROOT", tmp_path, approved_domains=APPROVED)
    first = list(world.exported)
    world.exported.clear()
    mod.crawl(world, "ROOT", tmp_path, approved_domains=APPROVED)
    assert first, "the first run must have exported something"
    assert world.exported == [], "the second run re-exported an unchanged file"


def test_a_changed_modified_time_is_re_exported(mod, tmp_path, world):
    mod.crawl(world, "ROOT", tmp_path, approved_domains=APPROVED)
    world.exported.clear()
    world.tree["mod"][0]["modifiedTime"] = "2026-06-01T00:00:00Z"
    mod.crawl(world, "ROOT", tmp_path, approved_domains=APPROVED)
    assert "doc1" in world.exported


def test_redaction_happens_before_the_bytes_reach_disk(mod, tmp_path, world):
    out = mod.crawl(world, "ROOT", tmp_path, approved_domains=APPROVED)
    on_disk = (out.cache_dir / out.manifest["doc1"]["text_path"]).read_text()
    assert "@" not in on_disk
    assert out.manifest["doc1"]["redacted"] == {"email": 1}


def test_media_is_recorded_but_never_downloaded(mod, tmp_path, world):
    out = mod.crawl(world, "ROOT", tmp_path, approved_domains=APPROVED)
    assert "vid1" in out.manifest
    assert out.manifest["vid1"]["action"] == "metadata_only"
    assert world.downloaded == []


def test_a_file_responses_folder_is_never_listed(mod, tmp_path, world):
    mod.crawl(world, "ROOT", tmp_path, approved_domains=APPROVED)
    assert "resp" not in world.listed
    assert "learner" not in world.exported


def test_a_shortcut_target_is_never_listed(mod, tmp_path, world):
    mod.crawl(world, "ROOT", tmp_path, approved_domains=APPROVED)
    assert "elsewhere" not in world.listed
    assert "secret" not in world.exported


def test_an_out_of_scope_domain_folder_is_not_walked(mod, tmp_path, world):
    mod.crawl(world, "ROOT", tmp_path, approved_domains=APPROVED)
    assert "other" not in world.listed


def test_skips_are_counted_per_rule(mod, tmp_path, world):
    out = mod.crawl(world, "ROOT", tmp_path, approved_domains=APPROVED)
    assert out.skips["D6"] == 1
    assert out.skips["no-media-download"] == 1


def test_the_report_counts_rather_than_enumerates(mod, tmp_path, world, capsys):
    """CLAUDE.md §5: one line per category, not one line per record."""
    mod.crawl(world, "ROOT", tmp_path, approved_domains=APPROVED, report=True)
    lines = capsys.readouterr().out.strip().splitlines()
    assert len(lines) < 30


def test_crawl_refuses_when_no_domain_is_approved(mod, tmp_path, world):
    """The gate, at the point of use. A signature with nothing ticked must not
    read as 'all of them'."""
    with pytest.raises(ValueError, match="approved_domains is empty"):
        mod.crawl(world, "ROOT", tmp_path, approved_domains=[])
