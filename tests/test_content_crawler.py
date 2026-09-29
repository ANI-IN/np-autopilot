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


def test_two_long_paths_sharing_a_prefix_get_different_cache_names(mod):
    """FOUND IN THE FIRST REAL CRAWL. `_safe_name` truncated to 180 characters,
    so 61 files whose paths shared a long prefix collapsed onto 15 names and
    46 exports were silently overwritten — including 14 distinct foundational
    -content files in one SD2 folder.

    The manifest recorded each row's OWN sha256 while the file on disk held the
    last writer's text, so the manifest was wrong and resume was wrong with it.
    Nothing errored: the failure produced output.
    """
    base = ("/SD2: Frontend/IK: Frontend Content Repo/Week 4/"
            "4 - Leveling Up with Advanced JavaScript and CSS/1. Foundational "
            "Material/v1: FM Text/Leveling Up with Advanced Javascript and CSS- "
            "Foundational Content/")
    a = mod._safe_name(base + "11. Advanced CSS: Positioning w/ Translate")
    b = mod._safe_name(base + "6. Storage: cookies vs localStorage")
    assert a != b


def test_a_cache_name_still_cannot_escape_the_cache_directory(mod):
    """Negative control: the collision fix must not reintroduce separators."""
    n = mod._safe_name("/../../etc/passwd")
    assert "/" not in n and ".." not in n


def test_two_drive_files_with_the_same_path_get_different_cache_names(mod):
    """FOUND IN THE SECOND CRAWL. Drive allows two files with the SAME NAME in
    the SAME FOLDER, so a cache name derived from the path alone collides by
    construction — 2 of 919 exports, in SD1's JavaScript module.

    A path is not an identity here. The Drive file id is.
    """
    p = "/SD1: Full Stack/.../2. Live Class Slides/JS and WebD - Live Class by JD"
    assert mod._safe_name(p, "11symrzjyqvQBEQj") != mod._safe_name(p, "1VNWhrz1n7XVkqux")


# ---------------------------------------------------------------------------
# 1c — the end-of-run integrity check, made permanent
# ---------------------------------------------------------------------------

def test_the_manifest_hash_matches_the_bytes_on_disk_for_crlf_text(mod, tmp_path, world):
    """CRLF is why this test exists rather than a generic round-trip.

    The first integrity check I ran reported 259 sha256 mismatches. 258 were
    files containing CRLF and a check that used read_text(), which applies
    universal-newline translation. The crawler was correct; the CHECK was
    wrong, and it was one step from being reported as a crawler failure.
    So the permanent check compares RAW BYTES, and this fixture carries CRLF
    to keep it honest.
    """
    world.blobs["doc1"] = b"line one\r\nline two\r\nmail ops@interviewkickstart.com\r\n"
    out = mod.crawl(world, "ROOT", tmp_path, approved_domains=APPROVED)
    import hashlib
    row = out.manifest["doc1"]
    raw = (out.cache_dir / row["text_path"]).read_bytes()
    assert b"\r\n" in raw, "fixture must actually exercise CRLF"
    assert hashlib.sha256(raw).hexdigest() == row["sha256"]


def test_integrity_is_checked_at_the_end_of_every_run(mod, tmp_path, world):
    out = mod.crawl(world, "ROOT", tmp_path, approved_domains=APPROVED)
    assert out.integrity["sha256_mismatches"] == 0
    assert out.integrity["orphan_files"] == 0
    assert out.integrity["missing_files"] == 0
    assert out.integrity["colliding_text_paths"] == 0


def test_a_corrupted_cache_file_is_caught_rather_than_reported_clean(mod, tmp_path, world):
    """Negative control. An integrity check that cannot fail is furniture."""
    out = mod.crawl(world, "ROOT", tmp_path, approved_domains=APPROVED)
    victim = out.cache_dir / out.manifest["doc1"]["text_path"]
    victim.write_text("tampered", encoding="utf-8")
    again = mod.verify_cache(out.cache_dir)
    assert again["sha256_mismatches"] == 1


def test_an_orphan_file_in_the_cache_is_reported(mod, tmp_path, world):
    out = mod.crawl(world, "ROOT", tmp_path, approved_domains=APPROVED)
    (out.cache_dir / "text" / "left_behind.txt").write_text("x", encoding="utf-8")
    assert mod.verify_cache(out.cache_dir)["orphan_files"] == 1


def test_the_run_summary_is_written_to_a_durable_file(mod, tmp_path, world):
    out = mod.crawl(world, "ROOT", tmp_path, approved_domains=APPROVED)
    summary = out.cache_dir / mod.SUMMARY_FILE
    assert summary.exists()
    import json as _j
    body = _j.loads(summary.read_text(encoding="utf-8"))
    assert body["integrity"]["sha256_mismatches"] == 0
    assert body["stats"]["exported"] >= 1
    assert body["skips"]


# ---------------------------------------------------------------------------
# 2 — download-disabled-by-owner is its own reason, derived from metadata
# ---------------------------------------------------------------------------

def test_a_download_disabled_file_gets_its_own_reason_code(mod):
    entry = {"id": "x", "name": "Timed Test.docx",
             "capabilities": {"canDownload": False},
             "copyRequiresWriterPermission": True}
    assert mod.download_disabled(entry) is True


def test_an_ordinary_file_is_not_flagged_as_download_disabled(mod):
    """Negative control: 870 of 919 exports must not acquire this reason."""
    entry = {"id": "y", "name": "ok.docx",
             "capabilities": {"canDownload": True},
             "copyRequiresWriterPermission": False}
    assert mod.download_disabled(entry) is False


# ---------------------------------------------------------------------------
# 1d — redaction_version is part of the cache contract
# ---------------------------------------------------------------------------

def test_every_exported_row_records_the_redaction_version(mod, tmp_path, world):
    out = mod.crawl(world, "ROOT", tmp_path, approved_domains=APPROVED)
    exported = [r for r in out.manifest.values() if r["action"] == "export"]
    assert exported
    assert all(r["redaction_version"] == mod.rd.REDACTION_VERSION for r in exported)


def test_a_redaction_version_bump_re_exports_even_when_nothing_changed(mod, tmp_path, world):
    """The cache is redacted text, so the redaction rules are part of its
    contract. A file unchanged in Drive is still STALE if the rules that
    produced its text have moved — and a cache holding two versions cannot be
    reasoned about at all.
    """
    mod.crawl(world, "ROOT", tmp_path, approved_domains=APPROVED)
    world.exported.clear()
    man = tmp_path / mod.CACHE_SUBDIR / "manifest.json"
    body = json.loads(man.read_text())
    for r in body.values():
        if r["action"] == "export":
            r["redaction_version"] = mod.rd.REDACTION_VERSION - 1
    man.write_text(json.dumps(body))
    mod.crawl(world, "ROOT", tmp_path, approved_domains=APPROVED)
    assert world.exported, "a version bump must re-export"


def test_an_unchanged_run_at_the_same_version_still_exports_nothing(mod, tmp_path, world):
    """Negative control: version-awareness must not destroy resume."""
    mod.crawl(world, "ROOT", tmp_path, approved_domains=APPROVED)
    world.exported.clear()
    mod.crawl(world, "ROOT", tmp_path, approved_domains=APPROVED)
    assert world.exported == []


def test_the_cache_is_never_left_at_mixed_redaction_versions(mod, tmp_path, world):
    out = mod.crawl(world, "ROOT", tmp_path, approved_domains=APPROVED)
    assert out.integrity["mixed_redaction_versions"] == 0


def test_copy_restriction_alone_does_not_mean_we_cannot_download(mod):
    """FOUND BY THE INTEGRITY CHECK, v2 run. Two SD3 files exported fine under
    v1 and were reclassified `download-disabled-by-owner` under v2, leaving
    their exports as orphans on disk.

    Both have `copyRequiresWriterPermission: true` AND `canDownload: true`, and
    the first version of this check OR-ed the two. That is A7B instance 7 in my
    own code: `copyRequiresWriterPermission` describes the FILE's setting,
    while `capabilities.canDownload` is the value Drive evaluates FOR THE
    REQUESTING IDENTITY. Keying on the first is storing somebody's setting and
    calling it our capability.

    canDownload is now the test; the copy restriction is corroboration only.
    """
    entry = {"id": "x", "name": "Object Modelling.pptx",
             "capabilities": {"canDownload": True},
             "copyRequiresWriterPermission": True}
    assert mod.download_disabled(entry) is False


def test_a_missing_capabilities_block_does_not_silently_disable(mod):
    """Absence is not a refusal. If Drive did not return capabilities we must
    TRY the fetch, not record 'unavailable' on a guess."""
    assert mod.download_disabled({"id": "y", "name": "z"}) is False


# ---------------------------------------------------------------------------
# Spreadsheets: every tab, not just the first
# ---------------------------------------------------------------------------

def test_a_spreadsheet_is_exported_with_every_tab(mod, tmp_path):
    """FOUND WHILE BUILDING PHASE 3. The crawler exported Sheets as `text/csv`,
    and Drive's CSV export returns ONLY THE FIRST TAB. `Backend: Lesson plans`
    has five; the cache held one, and the `Interview questions` tab was simply
    absent. The export succeeded and produced plausible output, so nothing
    errored — the same shape as the binary-decode bug.

    CLAUDE.md §0 already says why this matters, about pass 0's own export map:
    "Sheets -> xlsx preserves every tab, which is the whole point of this
    pass." This crawler chose csv and lost that property.

    42 exported files are spreadsheets and 23 of them are curriculum documents
    — the primary topic source for Phase 3.
    """
    import io
    import openpyxl
    wb = openpyxl.Workbook()
    wb.active.title = "Curriculum Outline"
    wb.active["A1"] = "Module"
    wb.create_sheet("Interview questions")["A1"] = "What is idempotency?"
    buf = io.BytesIO(); wb.save(buf)

    drive = _FakeDrive({"ROOT": [_f("dom", "SD3: Backend Engineering", FOLDER)],
                        "dom": [_f("sheet1", "Backend: Lesson plans",
                                   "application/vnd.google-apps.spreadsheet")]},
                       {"sheet1": buf.getvalue()})
    out = mod.crawl(drive, "ROOT", tmp_path, approved_domains=APPROVED)
    text = (out.cache_dir / out.manifest["sheet1"]["text_path"]).read_text()
    assert "Interview questions" in text, "the second tab is missing"
    assert "What is idempotency?" in text
    assert "[tab " in text, "tab boundaries must be locatable for provenance"


def test_the_extract_version_is_recorded_and_drives_resume(mod, tmp_path, world):
    """Extraction rules are part of the cache contract too, and they move
    independently of redaction — so they get their own version rather than
    riding on REDACTION_VERSION, which would re-export 922 files to fix 42."""
    out = mod.crawl(world, "ROOT", tmp_path, approved_domains=APPROVED)
    exported = [r for r in out.manifest.values() if r["action"] == "export"]
    assert all("extract_version" in r for r in exported)
    world.exported.clear()
    man = tmp_path / mod.CACHE_SUBDIR / "manifest.json"
    body = json.loads(man.read_text())
    for r in body.values():
        if r["action"] == "export":
            r["extract_version"] = 0
    man.write_text(json.dumps(body))
    mod.crawl(world, "ROOT", tmp_path, approved_domains=APPROVED)
    assert world.exported, "an extract-version bump must re-export"
