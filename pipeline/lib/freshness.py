"""Mastersheet freshness — refuse to derive from a cache older than Drive.

Owner request (Animesh Kumar, 2026-09-30, checklist review part 2 §B.3). The
SD1/1 review found the live sheet naming instructors the graph did not have.
eval/mastersheet_rederive.py and Phase C (pipeline/project_graph.py) now
refuse when the cached copy is older than Drive, naming both times.

WHAT IT COMPARES. The cached copy's Drive `modifiedTime` (recorded by pass 0
in .drive-cache/.manifest.json) against the file's CURRENT `modifiedTime`, and
the cached bytes' md5 against Drive's `md5Checksum`. Either disagreeing is a
refusal.

WHAT IT WOULD NOT HAVE CAUGHT. The SD1/1 case: the corpus file and the cache
were identical (same modifiedTime, version 12, same md5) — the sheet the owner
reads is a different Drive file that the service account cannot see. That is
why the source id is configurable (NP_MASTERSHEET_DRIVE_ID): pointed at the
live sheet, once it is shared with the service account, the same check
compares it against the cache.

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
CACHE = REPO_ROOT / ".drive-cache"
MANIFEST = CACHE / ".manifest.json"
SOURCE_ENV = "NP_MASTERSHEET_DRIVE_ID"
SKIP_ENV = "NP_FRESHNESS_SKIP"


def _t(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def cached_entry(manifest: dict) -> dict | None:
    """The manifest row for the mastersheet copy the pipeline reads."""
    return next((f for f in manifest.get("files") or []
                 if f.get("path", "").rsplit("/", 1)[-1] == SHEET_FILE), None)


def verdict(cached: dict | None, cached_md5: str | None, drive: dict | None,
            fetched_at: str | None = None) -> tuple[bool, str]:
    """(ok, message). Pure: every input is passed in, so it is testable offline."""
    if not cached or not cached.get("modified"):
        return False, (f"REFUSED: {SHEET_FILE} is not in the cache manifest "
                       f"({MANIFEST.relative_to(REPO_ROOT)}); run pass 0")
    held = f"the cache holds the version modified {cached['modified']}" + (
        f" (fetched {fetched_at})" if fetched_at else "")
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
    try:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return False, f"REFUSED: cannot read the cache manifest ({type(exc).__name__})"
    cached = cached_entry(manifest)
    md5 = None
    if cached:
        path = CACHE / cached["path"]
        if path.exists():
            md5 = hashlib.md5(path.read_bytes()).hexdigest()
    source = os.environ.get(SOURCE_ENV) or (cached or {}).get("id")
    try:
        drive = drive_metadata(source, service) if source else None
    except BaseException as exc:          # SystemExit from pass 0's abort() too
        if isinstance(exc, KeyboardInterrupt):
            raise
        # type only: a message can carry a key path or a token
        drive = {"id": source, "error": type(exc).__name__}
    ok, msg = verdict(cached, md5, drive, manifest.get("fetched_at"))
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
