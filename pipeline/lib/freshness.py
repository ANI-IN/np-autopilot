"""Mastersheet freshness — refuse to derive from a cache older than Drive.

Owner request (Animesh Kumar, 2026-09-30, checklist review part 2 §B.3). The
SD1/1 review found the live sheet naming instructors the graph did not have.
eval/mastersheet_rederive.py and Phase C (pipeline/project_graph.py) now
refuse when the cached copy is older than Drive, naming both times.

WHAT IT COMPARES. Since 2026-09-30 the source is the LIVE Google Sheet
(config/mastersheet-scope.yaml; NP_MASTERSHEET_DRIVE_ID overrides). Its
export, written by pipeline/fetch_mastersheet.py outside the repo, carries a
fetch record: Drive modifiedTime and version at fetch, and the export's sha256.
Refused when Drive's CURRENT modifiedTime is newer than the record's, or the
export on disk is no longer the bytes the record describes. A native Sheet has
no md5Checksum, so bytes are checked locally, times against Drive.

A CORRECTION, recorded where the wrong claim was made. This guard was first
written saying the SD1/1 gap came from the owner's live sheet being a different
file. It did not: the corpus copy always held SD1/1's three instructors, in a
row written "Week 1/5: Databases", and the parser — and the "independent"
re-derivation, which copied its regex — skipped the ":" silently. The files
really are different Drive files, and the owner chose the live one as
authoritative; the gap itself was the extractor (CLAUDE.md §6).

FAILS CLOSED. Could-not-look is a refusal, not a pass (the R21 lesson: a
check that goes green when it could not look is how a public repo lasted 13
days). The only way past it is NP_FRESHNESS_SKIP set to a REASON, which is
printed. The test suite sets it — it projects synthetic fixtures into a local
stack, never production.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from pipeline.lib.paths import REPO_ROOT

SHEET_FILE = "Resource Collection Mastersheet (Software + System).xlsx"
SOURCE_ENV = "NP_MASTERSHEET_DRIVE_ID"
DIR_ENV = "NP_MASTERSHEET_DIR"
SKIP_ENV = "NP_FRESHNESS_SKIP"
#: Read as YAML here, NOT through pipeline/lib/mastersheet.py: the independent
#: re-derivation imports this module and must not import the parser it checks.
SCOPE_FILE = REPO_ROOT / "config" / "mastersheet-scope.yaml"


def source_id() -> str:
    """The live sheet (config/mastersheet-scope.yaml, owner decision
    2026-09-30); NP_MASTERSHEET_DRIVE_ID overrides it."""
    import yaml
    env = os.environ.get(SOURCE_ENV, "").strip()
    if env:
        return env
    return yaml.safe_load(SCOPE_FILE.read_text(encoding="utf-8"))["source"]["drive_id"]


def live_dir() -> Path:
    return Path(os.environ.get(DIR_ENV, "~/.config/np-autopilot/mastersheet")).expanduser()


def live_path() -> Path:
    """Where pipeline/fetch_mastersheet.py put the export — outside the repo."""
    return live_dir() / f"{source_id()}.xlsx"


def _t(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def verdict(cached: dict | None, cached_md5: str | None, drive: dict | None,
            fetched_at: str | None = None) -> tuple[bool, str]:
    """(ok, message). Pure: every input is passed in, so it is testable offline."""
    if not cached or not cached.get("modified"):
        return False, (f"REFUSED: the mastersheet has not been fetched to {live_dir()} "
                       "(no fetch record); run pipeline/fetch_mastersheet.py")
    held = (f"the cache holds the version modified {cached['modified']}"
            + (f", version {cached['version']}" if cached.get("version") else "")
            + (f" (fetched {fetched_at})" if fetched_at else ""))
    if not drive or not drive.get("modifiedTime"):
        return False, (f"REFUSED: could not read Drive's modifiedTime for "
                       f"{(drive or {}).get('id') or 'the source'}; {held}. "
                       "Could-not-look is not a pass.")
    same_file = drive.get("id") == cached.get("id")
    newer = _t(drive["modifiedTime"]) > _t(cached["modified"])
    differs = bool(same_file and drive.get("md5Checksum") and cached_md5
                   and drive["md5Checksum"] != cached_md5)
    if newer or differs:
        why = "is NEWER than the cache" if newer else "has DIFFERENT bytes from the cache"
        return False, (f"REFUSED: Drive {drive.get('name') or drive.get('id')} "
                       f"({drive.get('id')}) was modified {drive['modifiedTime']} and "
                       f"{why}; {held}. Re-fetch it (pass 0, read-only) and rebuild "
                       "passes 7-8 before deriving anything from it.")
    return True, (f"fresh: Drive modified {drive['modifiedTime']}, {held}"
                  + ("" if same_file else f" (source {drive.get('id')} is not the "
                     "cached file; times compared, bytes cannot be)"))


def _drive_service():
    """Pass 0's own authentication: service account, drive.readonly, no
    delegation. Imported, not copied, so the scope cannot drift."""
    # Checked BEFORE loading pass 0: its import-time dependency check calls
    # abort(), which appends "00_fetch_drive (FAILED)" to BUILD_LOG.md — a
    # freshness probe is not a pass-0 run and must not leave that record
    # (it did, three times, while this was written; reverted).
    for dep in ("googleapiclient", "google.oauth2"):
        if importlib.util.find_spec(dep.split(".")[0]) is None:
            raise RuntimeError(f"{dep} is not installed — use the pipeline "
                               "environment (requirements.txt), e.g. python3")
    spec = importlib.util.spec_from_file_location(
        "fetch_drive", REPO_ROOT / "pipeline" / "00_fetch_drive.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.write_log = lambda *a, **k: None
    return mod.authenticate(mod.load_config())[0]


def drive_metadata(file_id: str, service=None) -> dict:
    service = service or _drive_service()
    return service.files().get(
        fileId=file_id, supportsAllDrives=True,
        fields="id,name,modifiedTime,md5Checksum,version").execute()


def check(service=None) -> tuple[bool, str]:
    sid = source_id()
    rec_path = live_dir() / f"{sid}.json"
    try:
        cached = json.loads(rec_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        cached = None
    if cached:
        # The export must still be the bytes its record describes.
        path = live_dir() / f"{sid}.xlsx"
        digest = hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None
        if digest != cached.get("sha256"):
            return False, (f"REFUSED: {path} is not the file its fetch record "
                           "describes (missing or changed since the fetch); re-fetch")
    try:
        drive = drive_metadata(sid, service)
    except BaseException as exc:          # SystemExit from pass 0's abort() too
        if isinstance(exc, KeyboardInterrupt):
            raise
        # type only: a message can carry a key path or a token
        drive = {"id": sid, "error": type(exc).__name__}
    ok, msg = verdict(cached, None, drive, (cached or {}).get("fetched_at"))
    if not ok and drive and drive.get("error"):
        msg += f" ({drive['error']})"
    return ok, msg


def require_fresh(what: str, service=None) -> None:
    """Call before deriving from the mastersheet. Exits on refusal."""
    reason = os.environ.get(SKIP_ENV, "").strip()
    if reason:
        print(f"  !! mastersheet freshness NOT CHECKED for {what}: "
              f"{SKIP_ENV}={reason!r}", file=sys.stderr)
        return
    ok, msg = check(service)
    if not ok:
        sys.exit(f"{what}: {msg}\n(set {SKIP_ENV}=<reason> only for a run that "
                 "never reaches production)")
    print(f"  mastersheet {msg}")
