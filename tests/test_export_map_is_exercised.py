"""Pass 0's export path, exercised on purpose before it matters.

WHY THIS FILE EXISTS
--------------------
`CLAUDE.md` §0 records that pass 0 was written to export native Google files —
which sync as unreadable URL stubs — and that **the export map has never
fired**, because all 75 files in the corpus folder are already binaries. That
sentence has been true since pass 0 was written, and it is the reason the
hand-export matched byte for byte.

On 2026-09-20 it stopped being safe to leave alone. A native Google Sheet named
`links` appeared **inside the corpus folder** — the scale-up registry
(`docs/REGISTRY-INVENTORY.md` §0). `EXPORT_MAP` maps spreadsheets to `.xlsx`, so
the next pass 0 run would have exported it: the first firing ever, on an
unexercised code path, on a file that decides the corpus boundary.

    A config file becoming a `file` node is harmless.
    An untested export path deciding the corpus boundary on its first-ever run
    is not.

So two things were done, and this file is the second:

  1. `links` is excluded in `config/taxonomy.yaml -> excluded.files`, so the
     path stays unexercised **against Drive**;
  2. it is exercised **here**, against a fake service, so "never run" stops
     being true in the place where being wrong is cheap.

This is instance 9's rule applied forwards rather than backwards. A constraint
that lives only in prose ("the export map has never fired") is one nothing would
notice becoming false. Now something does.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

FETCH = REPO / "pipeline" / "00_fetch_drive.py"

from pipeline.lib import taxonomy                       # noqa: E402


@pytest.fixture(scope="module")
def fetch_mod():
    spec = importlib.util.spec_from_file_location("np_fetch_drive", FETCH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# --------------------------------------------------------------------------
# The registry sheet is excluded, and excluded by the name pass 0 actually uses
# --------------------------------------------------------------------------

def test_the_registry_sheet_is_excluded_from_ingestion():
    """A configuration file must not become a `file` node.

    Not a privacy decision — a scope one. If `links` is ingested, the graph
    cites the crawl list as evidence about the corpus it selected.
    """
    assert "links" in taxonomy.excluded_files(), (
        "the scale-up registry sheet is not excluded; pass 1 treats an added "
        "file as expected traffic and would ingest it")


def test_the_exclusion_key_is_the_pre_export_name_not_the_written_filename(fetch_mod):
    """THE TRAP, pinned. `links.xlsx` here would silently never match.

    `rel_of` keys on `safe_name` — the Drive title — while `target_path`
    appends `.xlsx` only when deciding where to WRITE. The two names differ for
    exactly the native files the export map handles, which is the entire
    population this exclusion is about. Getting it wrong fails open.
    """
    entry = {
        "safe_name": "links",
        "mimeType": "application/vnd.google-apps.spreadsheet",
        "rel_dir": Path("."),
    }
    written = fetch_mod.target_path(entry, Path("/cache"))
    assert written.name == "links.xlsx", (
        "target_path no longer appends the export extension; if it now matches "
        "the exclusion key, this whole asymmetry is gone and the comment in "
        "taxonomy.yaml is stale")

    excluded = set(taxonomy.excluded_files())
    assert written.name not in excluded, (
        "the exclusion list now carries the POST-export name. Pass 0 compares "
        "against the pre-export name, so this entry cannot match and the file "
        "is silently ingested. Use `links`, not `links.xlsx`.")


# --------------------------------------------------------------------------
# The export path itself — the thing that has never run
# --------------------------------------------------------------------------

class _FakeRequest:
    """Stands in for a Drive media request. Carries only its payload.

    `fetch()` hands this to `MediaIoBaseDownload`, which is patched out by the
    `no_real_download` fixture — so the request needs no HTTP surface, and the
    branch under test (which verb, which mime, which note) runs for real.
    """

    def __init__(self, payload: bytes):
        self.payload = payload


class _FakeFiles:
    """Records which Drive API verb was chosen, and with what arguments."""

    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    def export_media(self, **kw):
        self.calls.append(("export_media", kw))
        return _FakeRequest(b"PK\x03\x04exported-bytes")

    def get_media(self, **kw):
        self.calls.append(("get_media", kw))
        return _FakeRequest(b"raw-bytes")


class _FakeService:
    def __init__(self):
        self._files = _FakeFiles()

    def files(self):
        return self._files


@pytest.fixture(autouse=True)
def no_real_download(fetch_mod, monkeypatch):
    """Replace the chunked downloader; keep every decision above it real.

    What is being tested is pass 0's BRANCH — export vs download, which target
    mime, which extension, how a failure is reported. Nothing here should touch
    the network, and a test that needed the network would not run in CI.
    """
    class _FakeDownloader:
        def __init__(self, buf, req, chunksize=None):
            self._buf, self._req = buf, req

        def next_chunk(self):
            self._buf.write(getattr(self._req, "payload", b""))
            return None, True

    monkeypatch.setattr(fetch_mod, "MediaIoBaseDownload", _FakeDownloader)


@pytest.mark.parametrize(
    "mime,expected_ext,expected_target",
    [
        ("application/vnd.google-apps.spreadsheet", ".xlsx",
         "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        ("application/vnd.google-apps.document", ".docx",
         "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        ("application/vnd.google-apps.presentation", ".pptx",
         "application/vnd.openxmlformats-officedocument.presentationml.presentation"),
        ("application/vnd.google-apps.drawing", ".pdf", "application/pdf"),
    ],
)
def test_every_native_type_exports_to_the_declared_binary(
        fetch_mod, tmp_path, mime, expected_ext, expected_target):
    """All four entries in EXPORT_MAP, not just the one that was about to fire.

    Parametrised deliberately: the registry sheet is a spreadsheet, so testing
    only spreadsheets would leave three quarters of the map in the state this
    file exists to fix.
    """
    assert mime in fetch_mod.EXPORT_MAP, f"{mime} fell out of EXPORT_MAP"
    target_mime, ext = fetch_mod.EXPORT_MAP[mime]
    assert ext == expected_ext
    assert target_mime == expected_target, (
        "the export target mime changed; Drive would return a different "
        "format than the extension claims")

    entry = {"id": "fake-id", "safe_name": "a native file",
             "mimeType": mime, "rel_dir": Path(".")}
    dest = fetch_mod.target_path(entry, tmp_path)
    assert dest.suffix == expected_ext

    service = _FakeService()
    ok, note = fetch_mod.fetch(service, entry, dest)

    assert ok, f"export failed: {note}"
    assert note == "exported", (
        f"a native file took the download path, not the export path: {note!r}")
    verb, kw = service.files().calls[-1]
    assert verb == "export_media", (
        "fetch() called get_media on a native Google file — that is the bug "
        "this pass was written to prevent, and it would write a URL stub")
    assert kw["mimeType"] == target_mime
    assert dest.read_bytes(), "the export wrote nothing"


def test_a_binary_file_still_takes_the_download_path(fetch_mod, tmp_path):
    """POSITIVE CONTROL, and the one that matters.

    'Export everything' and 'export the right things' both pass the test above.
    Only this distinguishes them — and every file in the corpus today is a
    binary, so a regression here breaks all 75 while the export tests stay
    green.
    """
    entry = {"id": "fake-id", "safe_name": "Already Binary.xlsx",
             "mimeType": ("application/vnd.openxmlformats-officedocument"
                          ".spreadsheetml.sheet"),
             "rel_dir": Path(".")}
    dest = fetch_mod.target_path(entry, tmp_path)
    assert dest.name == "Already Binary.xlsx", (
        "target_path appended an extension to a file that already had one")

    service = _FakeService()
    ok, note = fetch_mod.fetch(service, entry, dest)

    assert ok
    assert note != "exported"
    verb, _ = service.files().calls[-1]
    assert verb == "get_media", (
        "a binary took the export path; Drive refuses to export a non-native "
        "file, so this would fail every fetch in the corpus")


def test_target_path_does_not_double_the_extension(fetch_mod, tmp_path):
    """`links` has no extension; a Google Sheet literally named `sheet.xlsx`
    has one already. Both are native, and only one needs appending."""
    native = "application/vnd.google-apps.spreadsheet"
    bare = fetch_mod.target_path(
        {"safe_name": "links", "mimeType": native, "rel_dir": Path(".")},
        tmp_path)
    suffixed = fetch_mod.target_path(
        {"safe_name": "sheet.xlsx", "mimeType": native, "rel_dir": Path(".")},
        tmp_path)
    assert bare.name == "links.xlsx"
    assert suffixed.name == "sheet.xlsx", "extension doubled to .xlsx.xlsx"


def test_the_export_size_limit_is_reported_not_swallowed(fetch_mod, tmp_path):
    """Drive refuses to export a native file whose output exceeds ~10 MB.

    REGISTRY-INVENTORY §6 found a 17.66 MB deck, so this ceiling is not
    hypothetical at 2,000 files — it is the normal case for a slide deck. The
    requirement is that the failure is REPORTED, because a silently missing
    file is the corpus shrinking without anyone noticing.
    """
    assert fetch_mod.EXPORT_LIMIT_HINT == 10 * 1024 * 1024

    from googleapiclient.errors import HttpError

    class _Resp:
        status = 403
        reason = "Forbidden"

    class _Files(_FakeFiles):
        def export_media(self, **kw):
            self.calls.append(("export_media", kw))
            raise HttpError(
                _Resp(),
                b'{"error":{"errors":[{"reason":"exportSizeLimitExceeded"}],'
                b'"message":"This file is too large to be exported."}}',
                uri="https://www.googleapis.com/drive/v3/files/big/export")

    class _Svc:
        def __init__(self):
            self._f = _Files()

        def files(self):
            return self._f

    entry = {"id": "big", "safe_name": "huge deck",
             "mimeType": "application/vnd.google-apps.presentation",
             "rel_dir": Path(".")}
    dest = fetch_mod.target_path(entry, tmp_path)
    ok, note = fetch_mod.fetch(_Svc(), entry, dest)

    assert not ok, "an over-limit export reported success"
    assert "export too large" in note, (
        f"the size-limit failure is not named in the note: {note!r}")


def test_claude_md_still_says_the_map_has_not_fired_against_drive():
    """The prose and the world, pinned together — instance 9's actual lesson.

    `CLAUDE.md` claims the export map has never fired. That stays true ONLY
    because `links` is excluded. If the exclusion is removed, the claim becomes
    false on the next run and nothing else in the program would notice.
    """
    text = (REPO / "CLAUDE.md").read_text(encoding="utf-8")
    claims_never_fired = "export map has never fired" in text
    excluded = "links" in taxonomy.excluded_files()
    assert claims_never_fired == excluded or not claims_never_fired, (
        "CLAUDE.md says the export map has never fired, but the registry sheet "
        "is no longer excluded — so the next pass 0 run makes that false. "
        "Either restore the exclusion or rewrite CLAUDE.md §0 to say the map "
        "now runs, and say what it ran on.")
