"""pipeline/lib/freshness.py — refuse a mastersheet cache older than Drive.

Offline: Drive is a fake. The refusals are tested as hard as the pass,
including could-not-look, because a freshness check that passes when it
could not look is no check.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from pipeline.lib import freshness as fr                                # noqa: E402

ID = "synthetic-mastersheet-id"
CACHED = {"id": ID, "modified": "2026-09-02T11:45:15.000Z"}
MD5 = "0" * 32


def drive(modified, md5=MD5, id_=ID):
    return {"id": id_, "name": fr.SHEET_FILE, "modifiedTime": modified, "md5Checksum": md5}


def test_an_identical_copy_is_fresh():
    ok, msg = fr.verdict(CACHED, MD5, drive("2026-09-02T11:45:15.000Z"))
    assert ok, msg


def test_a_newer_drive_copy_is_refused_naming_both_times():
    ok, msg = fr.verdict(CACHED, MD5, drive("2026-09-29T08:00:00.000Z"),
                         fetched_at="2026-09-16T21:00:10Z")
    assert not ok
    for t in ("2026-09-29T08:00:00.000Z", "2026-09-02T11:45:15.000Z", "2026-09-16T21:00:10Z"):
        assert t in msg, t


def test_same_time_different_bytes_is_refused():
    ok, msg = fr.verdict(CACHED, MD5, drive("2026-09-02T11:45:15.000Z", md5="f" * 32))
    assert not ok and "DIFFERENT bytes" in msg


@pytest.mark.parametrize("d", [None, {"id": ID, "error": "HttpError"}, {"id": ID}])
def test_could_not_look_is_a_refusal(d):
    ok, msg = fr.verdict(CACHED, MD5, d)
    assert not ok and "Could-not-look" in msg


def test_absent_from_the_manifest_is_a_refusal():
    assert fr.verdict(None, None, drive("2026-09-02T11:45:15.000Z"))[0] is False


def test_a_different_source_file_compares_times_only():
    """NP_MASTERSHEET_DRIVE_ID pointed at the live sheet: its bytes are not the
    cached file's, so only the times can be compared."""
    ok, _ = fr.verdict(CACHED, MD5, drive("2026-09-01T00:00:00.000Z", md5="f" * 32, id_="live"))
    assert ok
    ok, msg = fr.verdict(CACHED, MD5, drive("2026-09-29T00:00:00.000Z", id_="live"))
    assert not ok and "NEWER" in msg


class FakeDrive:
    def __init__(self, meta=None, exc=None):
        self.meta, self.exc, self.asked = meta, exc, []

    def files(self):
        return self

    def get(self, **kw):
        self.asked.append(kw)
        return self

    def execute(self):
        if self.exc:
            raise self.exc
        return self.meta


def test_require_fresh_refuses_a_stale_cache(monkeypatch):
    monkeypatch.delenv(fr.SKIP_ENV, raising=False)
    monkeypatch.setattr(fr, "check", lambda service=None: fr.verdict(
        CACHED, MD5, drive("2026-09-29T08:00:00.000Z")))
    with pytest.raises(SystemExit) as e:
        fr.require_fresh("project_graph")
    assert "project_graph" in str(e.value) and "REFUSED" in str(e.value)


def _fetched(tmp_path, monkeypatch, id_=ID, modified="2026-09-02T11:45:15.000Z"):
    """A fetch record + export, as pipeline/fetch_mastersheet.py leaves them."""
    import hashlib
    import json
    data = b"synthetic export bytes"
    (tmp_path / f"{id_}.xlsx").write_bytes(data)
    (tmp_path / f"{id_}.json").write_text(json.dumps({
        "id": id_, "modified": modified, "version": "7",
        "fetched_at": "2026-09-16T21:00:10Z",
        "sha256": hashlib.sha256(data).hexdigest()}), encoding="utf-8")
    monkeypatch.setenv(fr.DIR_ENV, str(tmp_path))
    monkeypatch.setenv(fr.SOURCE_ENV, id_)


def test_require_fresh_refuses_when_drive_is_unreachable(monkeypatch, tmp_path):
    monkeypatch.delenv(fr.SKIP_ENV, raising=False)
    _fetched(tmp_path, monkeypatch)
    fake = FakeDrive(exc=OSError("network down"))
    with pytest.raises(SystemExit) as e:
        fr.require_fresh("mastersheet_rederive", service=fake)
    assert "Could-not-look" in str(e.value)
    assert fake.asked and fake.asked[0]["fileId"] == ID


def test_the_source_id_is_configurable(monkeypatch, tmp_path):
    _fetched(tmp_path, monkeypatch, id_="the-live-sheet")
    fake = FakeDrive(meta=drive("2026-09-02T11:45:15.000Z", id_="the-live-sheet"))
    assert fr.check(service=fake)[0]
    assert fake.asked[0]["fileId"] == "the-live-sheet"


def test_the_default_source_is_the_owners_live_sheet(monkeypatch):
    monkeypatch.delenv(fr.SOURCE_ENV, raising=False)
    assert fr.source_id() == "1setMmRvBUNu9_85nT4xvvUFySodB6kiWb7bQ8qLEqAQ"


def test_a_live_edit_after_the_fetch_is_refused(monkeypatch, tmp_path):
    _fetched(tmp_path, monkeypatch)
    ok, msg = fr.check(service=FakeDrive(meta=drive("2026-09-30T09:00:00.000Z")))
    assert not ok and "NEWER" in msg and "version 7" in msg


def test_an_export_changed_since_its_fetch_is_refused(monkeypatch, tmp_path):
    _fetched(tmp_path, monkeypatch)
    (tmp_path / f"{ID}.xlsx").write_bytes(b"tampered")
    ok, msg = fr.check(service=FakeDrive(meta=drive("2026-09-02T11:45:15.000Z")))
    assert not ok and "not the file its fetch record describes" in msg


def test_never_fetched_is_refused(monkeypatch, tmp_path):
    monkeypatch.setenv(fr.DIR_ENV, str(tmp_path))
    ok, msg = fr.check(service=FakeDrive(meta=drive("2026-09-02T11:45:15.000Z")))
    assert not ok and "fetch_mastersheet.py" in msg


def test_the_fetch_refuses_to_write_inside_the_repo(monkeypatch):
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "fetch_mastersheet", REPO / "pipeline" / "fetch_mastersheet.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setenv(fr.DIR_ENV, str(REPO / "knowledge"))
    with pytest.raises(SystemExit, match="inside the repo"):
        mod.target_dir()


def test_the_skip_must_carry_a_reason_and_says_so(monkeypatch, capsys):
    monkeypatch.setenv(fr.SKIP_ENV, "rehearsal on a local copy")
    monkeypatch.setattr(fr, "check", lambda service=None: (_ for _ in ()).throw(
        AssertionError("must not look when skipped")))
    fr.require_fresh("project_graph")
    assert "NOT CHECKED" in capsys.readouterr().err
    monkeypatch.setenv(fr.SKIP_ENV, "   ")
    monkeypatch.setattr(fr, "check", lambda service=None: (False, "REFUSED: x"))
    with pytest.raises(SystemExit):
        fr.require_fresh("project_graph")


@pytest.mark.parametrize("script", ["pipeline/project_graph.py", "eval/mastersheet_rederive.py"])
def test_both_derivations_are_gated(script):
    src = (REPO / script).read_text(encoding="utf-8")
    assert "freshness.require_fresh(" in src


def test_it_uses_pass_zeros_readonly_authentication():
    src = (REPO / "pipeline" / "lib" / "freshness.py").read_text(encoding="utf-8")
    assert "mod.authenticate(" in src and "scopes=" not in src


def test_a_probe_without_the_drive_libraries_writes_no_pass0_log(monkeypatch, tmp_path):
    """Found live: loading pass 0 without its libraries appended
    '00_fetch_drive (FAILED)' to BUILD_LOG.md three times."""
    import importlib.util
    log = tmp_path / "BUILD_LOG.md"
    monkeypatch.setenv("NP_BUILD_LOG", str(log))
    monkeypatch.setattr(importlib.util, "find_spec", lambda name, *a: None)
    with pytest.raises(RuntimeError):
        fr._drive_service()
    assert not log.exists()
