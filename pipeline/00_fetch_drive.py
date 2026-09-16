#!/usr/bin/env python3
"""Pass 0 — fetch the corpus from Google Drive into a local cache.

Replaces the Drive-desktop-sync assumption in brief section 1.4. Native Google
files (Sheets/Docs/Slides) sync to disk as tiny URL stubs that no parser can
read; this pass exports them to real .xlsx/.docx/.pptx via the Drive export
endpoint, so every tab of every Sheet survives into the cache.

Separation of passes is deliberate (same rule as B4): this script only fetches.
01_walk_corpus.py reads the cache from disk and never calls the network, so
parsing can be re-run without re-downloading. Do not fuse them.

Auth: a SERVICE ACCOUNT, scope drive.readonly, with the Drive folder shared to
its address. No domain-wide delegation. The pipeline must never hold write
access to Drive. The key is named by path through NP_DRIVE_SA_KEY and is never
read from inside the repo.

Usage:
    python3 pipeline/00_fetch_drive.py                 # incremental
    python3 pipeline/00_fetch_drive.py --force         # re-download everything
    python3 pipeline/00_fetch_drive.py --dry-run       # list, fetch nothing
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# The repo imports come FIRST, before the third-party ones, so that a missing
# dependency can still be recorded in the build log. Ordered the other way, the
# one failure most likely to hit a freshly provisioned scheduler — the libraries
# are not installed — was the one failure that left no trace.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.lib.paths import DRIVE_CONFIG, REPO_ROOT, build_log      # noqa: E402

# Pass 0 must not become a second place where a repo path is decided. ROOT,
# CONFIG and BUILD_LOG were all re-derived here; they now come from
# pipeline/lib/paths.py like every other pass.
ROOT = REPO_ROOT
CONFIG = DRIVE_CONFIG


def write_log(outcome: str, detail: str, **context) -> None:
    """Append one record for a terminal outcome. Never raises.

    Called on EVERY path that ends the run, success or failure. A logging bug
    must not become the reason a real failure goes unreported, so this swallows
    its own errors and says so on stderr.
    """
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
    lines = [f"\n## {ts} — 00_fetch_drive ({outcome})\n\n"]
    for key, value in context.items():
        if value not in (None, ""):
            lines.append(f"- {key.replace('_', ' ').capitalize()}: `{value}`\n")
    for line in str(detail).strip().splitlines():
        lines.append(f"- {line.strip()}\n")
    try:
        log = build_log()
        log.parent.mkdir(parents=True, exist_ok=True)
        if not log.exists():
            log.write_text("# BUILD_LOG\n", encoding="utf-8")
        with log.open("a", encoding="utf-8") as fh:
            fh.write("".join(lines))
    except OSError as exc:                                    # pragma: no cover
        print(f"  WARNING: could not write the build log: {exc}", file=sys.stderr)


def abort(detail: str, **context):
    """Record the failure, then exit non-zero. The ONLY way this pass fails.

    Pass 0 is the pass most likely to run unattended, and every one of its
    terminal failures used to sys.exit() straight past append_build_log. The
    empty-enumeration guard — the single most important check in the file —
    left no trace at all, so a nightly job that fetched nothing looked exactly
    like a nightly job that never ran.
    """
    write_log("FAILED", detail, **context)
    sys.exit(detail)


try:
    import yaml
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    from googleapiclient.http import MediaIoBaseDownload
except ImportError as exc:                                    # pragma: no cover
    abort(f"missing dependency: {exc.name}\n"
          "pip install google-api-python-client google-auth pyyaml")

# Read-only. Never widen this — a write scope would let a pipeline bug modify
# the team's Drive. If a future pass needs to write, it gets its own credential.
SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

# Native Google types have no bytes to download; they must be exported.
# Sheets -> xlsx preserves every tab, which is the whole point of this pass.
EXPORT_MAP = {
    "application/vnd.google-apps.spreadsheet": (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", ".xlsx"),
    "application/vnd.google-apps.document": (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document", ".docx"),
    "application/vnd.google-apps.presentation": (
        "application/vnd.openxmlformats-officedocument.presentationml.presentation", ".pptx"),
    "application/vnd.google-apps.drawing": ("application/pdf", ".pdf"),
}
FOLDER_MIME = "application/vnd.google-apps.folder"
SHORTCUT_MIME = "application/vnd.google-apps.shortcut"

# Drive refuses to export a native file whose generated form exceeds 10 MB.
EXPORT_LIMIT_HINT = 10 * 1024 * 1024

FIELDS = (
    "nextPageToken, files(id, name, mimeType, modifiedTime, size, md5Checksum, "
    "trashed, shortcutDetails(targetId, targetMimeType))"
)


def load_config() -> dict:
    if not CONFIG.exists():
        abort(f"missing {CONFIG.relative_to(ROOT)}\n"
              f"cp {CONFIG.relative_to(ROOT)}.example {CONFIG.relative_to(ROOT)}, "
              "then set folder_id — never hardcode it in this script.")
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8")) or {}
    if not cfg.get("folder_id"):
        abort(f"{CONFIG.name}: folder_id is required")
    cfg.setdefault("cache_dir", ".drive-cache")
    return cfg


def key_path(cfg: dict) -> Path:
    """Where the service-account key lives. NP_DRIVE_SA_KEY wins over config.

    The key is a credential, so it is named by PATH and never copied into the
    repo. `.gitignore` refuses to stage one at the repo root, but an ignore rule
    stops a commit, not a `cp` into a build context — so this also refuses to
    read a key from inside the repo at all.
    """
    raw = os.environ.get("NP_DRIVE_SA_KEY") or cfg.get("service_account_key")
    if not raw:
        abort("no service-account key configured. "
              "export NP_DRIVE_SA_KEY=/path/to/key.json, or set "
              f"service_account_key in {CONFIG.name} (a PATH, never the key)")
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = (ROOT / path).resolve()
    if not path.exists():
        abort(f"service-account key not found at {path}")
    try:
        path.relative_to(ROOT)
    except ValueError:
        pass                                   # outside the repo — correct
    else:
        abort("refusing to read a service-account key from inside the repo: "
              f"{path}. Move it out (e.g. ~/.config/np-autopilot/) and chmod 600.")
    mode = path.stat().st_mode & 0o777
    if mode & 0o077:
        print(f"  WARNING: key is mode {mode:o}; tighten it with chmod 600 {path}",
              file=sys.stderr)
    return path


def authenticate(cfg: dict):
    """Service-account auth. Returns (service, account_email).

    Replaces the installed-app OAuth flow. A headless job cannot complete a
    browser consent, and a token tied to one person's account dies when they
    leave — both of which made the old flow unusable for a scheduled refresh.

    NO DOMAIN-WIDE DELEGATION. There is deliberately no `with_subject()` call
    here: access comes from the Drive folder being shared to the service
    account's address, which is revocable in one click by whoever owns the
    folder. Delegation would let this key impersonate any user in the
    workspace, which is a far larger blast radius than reading one folder.

    Scope stays drive.readonly and nothing wider. A write scope would let a
    pipeline bug modify the team's Drive. If a future pass needs to write, it
    gets its own credential.
    """
    creds = service_account.Credentials.from_service_account_file(
        str(key_path(cfg)), scopes=SCOPES)
    service = build("drive", "v3", credentials=creds, cache_discovery=False)
    account = getattr(creds, "service_account_email", None) or "unknown"
    try:
        about = service.about().get(fields="user(emailAddress)").execute()
        account = about["user"]["emailAddress"]
    except HttpError:
        pass
    return service, account


def drive_kind(service, folder_id: str) -> tuple[str, str | None, str]:
    """Is the folder in a Shared Drive or in My Drive? Returns (kind, drive_id, name).

    Determined BEFORE any listing, because the answer changes what a correct
    listing call looks like — and gets it wrong silently. Without
    supportsAllDrives/includeItemsFromAllDrives, a Shared Drive folder returns
    an empty file list with HTTP 200: no error, no warning, just a successful
    build over nothing. That is the worst failure shape available here, and it
    is why the empty-enumeration guard below is fatal rather than a warning.
    """
    f = service.files().get(
        fileId=folder_id,
        fields="id, name, mimeType, driveId, trashed",
        supportsAllDrives=True,
    ).execute()
    if f.get("mimeType") != FOLDER_MIME:
        abort(f"folder id resolves to a {f.get('mimeType')}, not a folder",
              folder_id=folder_id)
    if f.get("trashed"):
        abort("the configured folder is in the trash", folder_id=folder_id)
    drive_id = f.get("driveId")
    return ("shared_drive" if drive_id else "my_drive"), drive_id, f.get("name", "")


def list_folder(service, folder_id: str, drive_id: str | None = None):
    """Yield non-trashed children of one folder.

    supportsAllDrives and includeItemsFromAllDrives are mandatory on EVERY call,
    not only when we believe we are on a Shared Drive — a shortcut can point
    into one from a My Drive tree. tests/test_drive_all_drives_flags.py asserts
    both are present on every listing call in this file.
    """
    page = None
    while True:
        params = dict(
            q=f"'{folder_id}' in parents and trashed = false",
            fields=FIELDS,
            pageSize=1000,
            pageToken=page,
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        )
        if drive_id:
            # Scope the query to the Shared Drive explicitly. Not strictly
            # required alongside includeItemsFromAllDrives, but it makes a
            # permission problem surface as an error instead of an empty page.
            params.update(corpora="drive", driveId=drive_id)
        resp = service.files().list(**params).execute()
        for f in resp.get("files", []):
            yield f
        page = resp.get("nextPageToken")
        if not page:
            return


def walk(service, folder_id: str, prefix: Path, seen: set,
         drive_id: str | None = None) -> list:
    """Recursively enumerate the folder tree. Returns a flat list of entries."""
    if folder_id in seen:                       # Drive allows folder cycles
        print(f"  ! cycle at {prefix}, skipping", file=sys.stderr)
        return []
    seen.add(folder_id)

    out = []
    for f in list_folder(service, folder_id, drive_id):
        name = f["name"].replace("/", "_")
        mime = f["mimeType"]

        if mime == SHORTCUT_MIME:
            details = f.get("shortcutDetails") or {}
            target, tmime = details.get("targetId"), details.get("targetMimeType")
            if not target:
                continue
            if tmime == FOLDER_MIME:
                out += walk(service, target, prefix / name, seen, drive_id)
                continue
            f = {**f, "id": target, "mimeType": tmime}
            mime = tmime

        if mime == FOLDER_MIME:
            out += walk(service, f["id"], prefix / name, seen, drive_id)
        else:
            out.append({**f, "rel_dir": prefix, "safe_name": name})
    return out


def target_path(entry: dict, cache: Path) -> Path:
    name, mime = entry["safe_name"], entry["mimeType"]
    if mime in EXPORT_MAP:
        ext = EXPORT_MAP[mime][1]
        if not name.lower().endswith(ext):
            name += ext
    return cache / entry["rel_dir"] / name


def fetch(service, entry: dict, dest: Path) -> tuple[bool, str]:
    """Download or export one file. Returns (ok, note)."""
    mime = entry["mimeType"]
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        if mime in EXPORT_MAP:
            req = service.files().export_media(fileId=entry["id"], mimeType=EXPORT_MAP[mime][0])
            note = "exported"
        else:
            req = service.files().get_media(fileId=entry["id"], supportsAllDrives=True)
            note = "downloaded"

        buf = io.BytesIO()
        downloader = MediaIoBaseDownload(buf, req, chunksize=8 * 1024 * 1024)
        done = False
        while not done:
            _, done = downloader.next_chunk()

        tmp = dest.with_suffix(dest.suffix + ".part")
        tmp.write_bytes(buf.getvalue())
        tmp.replace(dest)
        return True, note
    except HttpError as exc:
        if exc.resp.status == 403 and "exportSizeLimitExceeded" in str(exc):
            return False, f"export too large (Drive caps native exports near {EXPORT_LIMIT_HINT // 1024 // 1024} MB)"
        return False, f"HTTP {exc.resp.status}: {exc.reason}"
    except Exception as exc:
        return False, str(exc)


def is_current(entry: dict, dest: Path) -> bool:
    if not dest.exists():
        return False
    mtime = datetime.fromisoformat(entry["modifiedTime"].replace("Z", "+00:00"))
    local = datetime.fromtimestamp(dest.stat().st_mtime, tz=timezone.utc)
    if local < mtime:
        return False
    size = entry.get("size")
    # Exported files have no source size to compare; mtime is all we have.
    return True if size is None else dest.stat().st_size > 0


def append_build_log(account: str, folder_id: str, stats: dict, cache: Path,
                     location: str = "", drive_id: str | None = None) -> None:
    """The SUCCESS record. Routed through write_log so there is one writer.

    Every build records who ran it and against which folder. Different people
    have different Drive visibility, so a corpus delta explained by "someone
    else ran it" must be visible here rather than mysterious.
    """
    detail = [
        f"Files seen: {stats['seen']} | fetched: {stats['fetched']} "
        f"| exported: {stats['exported']} | skipped current: {stats['skipped']} "
        f"| failed: {stats['failed']}"
    ]
    for name, why in stats["failures"]:
        detail.append(f"  FAILED `{name}` — {why}")
    write_log("partial" if stats["failed"] else "ok", "\n".join(detail),
              account=account, folder_id=folder_id, location=location,
              drive_id=drive_id, scope=SCOPES[0], cache=cache)


def probe_folder(service, folder_id: str) -> str:
    """Diagnose an empty or failed enumeration. Returns a human-readable line."""
    try:
        f = service.files().get(
            fileId=folder_id,
            fields="id, name, mimeType, driveId, trashed, capabilities(canListChildren)",
            supportsAllDrives=True,
        ).execute()
    except HttpError as exc:
        if exc.resp.status == 404:
            return ("404 — the id is not visible to this account. Either the id is "
                    "wrong, or the folder belongs to a Shared Drive / another "
                    "account that has not shared it with you.")
        return f"HTTP {exc.resp.status}: {exc.reason}"
    if f.get("mimeType") != FOLDER_MIME:
        return f"id resolves to a {f.get('mimeType')}, not a folder"
    if f.get("trashed"):
        return "folder is in the trash"
    bits = [f"name={f.get('name')!r}"]
    bits.append(f"shared drive={f['driveId']}" if f.get("driveId") else "My Drive")
    if not f.get("capabilities", {}).get("canListChildren", True):
        bits.append("NO canListChildren permission")
    return ", ".join(bits) + " — folder is visible but returned no children (it may genuinely be empty)"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="re-fetch even if current")
    ap.add_argument("--dry-run", action="store_true", help="enumerate only")
    args = ap.parse_args()

    cfg = load_config()
    cache = ROOT / cfg["cache_dir"]
    service, account = authenticate(cfg)
    folder_id = cfg["folder_id"]

    kind, drive_id, folder_name = drive_kind(service, folder_id)

    print(f"account : {account}")
    print(f"folder  : {folder_id}  ({folder_name!r})")
    print(f"location: {kind}" + (f", driveId {drive_id}" if drive_id else ""))
    print(f"cache   : {cache.relative_to(ROOT)}")
    print(f"scope   : {SCOPES[0]}\n")

    entries = walk(service, folder_id, Path("."), set(), drive_id)
    entries.sort(key=lambda e: str(e["rel_dir"] / e["safe_name"]))

    # An empty tree is a FAILURE, never a success. The most common cause is a
    # Shared Drive reached without the all-drives flags, which returns an empty
    # list and HTTP 200 rather than an error. Exiting 0 here would report a
    # successful build over an empty corpus.
    if not entries:
        meta = probe_folder(service, folder_id)
        abort("FATAL: enumerated 0 files. This is never a valid result.\n"
              f"folder probe: {meta}\n"
              "See README, 'If the folder returns nothing or 404s'.",
              account=account, folder_id=folder_id, location=kind,
              drive_id=drive_id, scope=SCOPES[0])

    print(f"{len(entries)} files in the Drive tree\n")

    stats = {"seen": len(entries), "fetched": 0, "exported": 0,
             "skipped": 0, "failed": 0, "failures": []}
    manifest = []

    for e in entries:
        dest = target_path(e, cache)
        rel = dest.relative_to(cache)
        native = e["mimeType"] in EXPORT_MAP

        if args.dry_run:
            print(f"  [dry] {'export' if native else 'get':>6}  {rel}")
            continue
        if not args.force and is_current(e, dest):
            stats["skipped"] += 1
            manifest.append({"path": str(rel), "id": e["id"], "mime": e["mimeType"],
                             "modified": e["modifiedTime"], "state": "current"})
            continue

        ok, note = fetch(service, e, dest)
        if ok:
            stats["fetched"] += 1
            if native:
                stats["exported"] += 1
            print(f"  {note:>10}  {rel}")
            manifest.append({"path": str(rel), "id": e["id"], "mime": e["mimeType"],
                             "modified": e["modifiedTime"], "state": note})
        else:
            stats["failed"] += 1
            stats["failures"].append((str(rel), note))
            print(f"  {'FAILED':>10}  {rel} — {note}", file=sys.stderr)

    if args.dry_run:
        # A dry run is still a run, and its enumeration is the useful half. A
        # scheduled job that silently switched to --dry-run would otherwise be
        # indistinguishable from one that never ran.
        write_log("dry-run", f"enumerated {len(entries)} files, fetched nothing",
                  account=account, folder_id=folder_id, location=kind,
                  drive_id=drive_id, scope=SCOPES[0])
        return 0

    cache.mkdir(parents=True, exist_ok=True)
    # DOT-PREFIXED on purpose. 01_walk_corpus skips any dot-prefixed path
    # segment ("the corpus has no dotfiles"), and this is pass 0's own
    # bookkeeping, not corpus material. Named `_manifest.json` it was discovered
    # as a 76th corpus file the moment a cache existed — and the file-count check
    # would NOT have caught it, because 75 file nodes sits inside expect 74 ± 2.
    # That is the same class of bug as `commands/` and NEXT.md being swept in,
    # except silent.
    (cache / ".manifest.json").write_text(
        json.dumps({"account": account, "folder_id": folder_id,
                    "fetched_at": datetime.now(timezone.utc).isoformat(),
                    "files": manifest}, indent=1),
        encoding="utf-8")

    append_build_log(account, folder_id, stats, cache.relative_to(ROOT),
                     location=kind, drive_id=drive_id)
    print(f"\nseen {stats['seen']} | fetched {stats['fetched']} "
          f"(exported {stats['exported']}) | current {stats['skipped']} "
          f"| failed {stats['failed']}")
    return 1 if stats["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
