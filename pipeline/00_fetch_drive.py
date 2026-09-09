#!/usr/bin/env python3
"""Pass 0 — fetch the corpus from Google Drive into a local cache.

Replaces the Drive-desktop-sync assumption in brief section 1.4. Native Google
files (Sheets/Docs/Slides) sync to disk as tiny URL stubs that no parser can
read; this pass exports them to real .xlsx/.docx/.pptx via the Drive export
endpoint, so every tab of every Sheet survives into the cache.

Separation of passes is deliberate (same rule as B4): this script only fetches.
01_walk_corpus.py reads the cache from disk and never calls the network, so
parsing can be re-run without re-downloading. Do not fuse them.

Auth: user OAuth, scope drive.readonly. The pipeline must never hold write
access to Drive. See README "Google Drive access" for why the consent screen
must be user type Internal.

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

try:
    import yaml
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    from googleapiclient.http import MediaIoBaseDownload
except ImportError as exc:                                    # pragma: no cover
    sys.exit(
        f"missing dependency: {exc.name}\n"
        "  pip install google-api-python-client google-auth-oauthlib pyyaml"
    )

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config" / "drive.yaml"
BUILD_LOG = ROOT / "BUILD_LOG.md"

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
        sys.exit(
            f"missing {CONFIG.relative_to(ROOT)}\n"
            f"  cp {CONFIG.relative_to(ROOT)}.example {CONFIG.relative_to(ROOT)}\n"
            "  then set folder_id — never hardcode it in this script."
        )
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8")) or {}
    if not cfg.get("folder_id"):
        sys.exit(f"{CONFIG.name}: folder_id is required")
    cfg.setdefault("cache_dir", ".drive-cache")
    cfg.setdefault("credentials_file", "config/credentials.json")
    cfg.setdefault("token_file", "config/token.json")
    return cfg


def authenticate(cfg: dict):
    """User OAuth. Returns (service, account_email).

    B10 v2 note: the nightly job should use a SERVICE ACCOUNT with the folder
    shared to its address, not this flow — a headless job cannot complete a
    browser consent. Nothing below blocks that: swap this function for
    google.oauth2.service_account.Credentials.from_service_account_file(...)
    and the rest of the script is unchanged, because everything downstream
    takes `service` and an account label.
    """
    token_path = ROOT / cfg["token_file"]
    creds_path = ROOT / cfg["credentials_file"]
    creds = None

    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except Exception as exc:
            print(f"  token refresh failed ({exc}); re-authenticating", file=sys.stderr)
            creds = None

    if not creds or not creds.valid:
        if not creds_path.exists():
            sys.exit(
                f"missing {creds_path.relative_to(ROOT)}\n"
                "See README, 'Google Drive access'. The OAuth consent screen must be\n"
                "user type INTERNAL. External + Testing issues a refresh token that\n"
                "expires after 7 days and the pipeline then dies with invalid_grant."
            )
        flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
        creds = flow.run_local_server(port=0)
        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(creds.to_json(), encoding="utf-8")
        token_path.chmod(0o600)

    service = build("drive", "v3", credentials=creds, cache_discovery=False)
    try:
        about = service.about().get(fields="user(emailAddress)").execute()
        account = about["user"]["emailAddress"]
    except HttpError:
        account = "unknown"
    return service, account


def list_folder(service, folder_id: str):
    """Yield non-trashed children of one folder."""
    page = None
    while True:
        resp = service.files().list(
            q=f"'{folder_id}' in parents and trashed = false",
            fields=FIELDS,
            pageSize=1000,
            pageToken=page,
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        ).execute()
        for f in resp.get("files", []):
            yield f
        page = resp.get("nextPageToken")
        if not page:
            return


def walk(service, folder_id: str, prefix: Path, seen: set) -> list:
    """Recursively enumerate the folder tree. Returns a flat list of entries."""
    if folder_id in seen:                       # Drive allows folder cycles
        print(f"  ! cycle at {prefix}, skipping", file=sys.stderr)
        return []
    seen.add(folder_id)

    out = []
    for f in list_folder(service, folder_id):
        name = f["name"].replace("/", "_")
        mime = f["mimeType"]

        if mime == SHORTCUT_MIME:
            details = f.get("shortcutDetails") or {}
            target, tmime = details.get("targetId"), details.get("targetMimeType")
            if not target:
                continue
            if tmime == FOLDER_MIME:
                out += walk(service, target, prefix / name, seen)
                continue
            f = {**f, "id": target, "mimeType": tmime}
            mime = tmime

        if mime == FOLDER_MIME:
            out += walk(service, f["id"], prefix / name, seen)
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


def append_build_log(account: str, folder_id: str, stats: dict, cache: Path) -> None:
    """Every build records who ran it and against which folder.

    Different people have different Drive visibility. A corpus delta explained
    by "someone else ran it" must be visible here rather than mysterious.
    """
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
    line = (
        f"\n## {ts} — 00_fetch_drive\n\n"
        f"- Authenticated account: `{account}`\n"
        f"- Drive folder id: `{folder_id}`\n"
        f"- Scope: `{SCOPES[0]}`\n"
        f"- Cache: `{cache}`\n"
        f"- Files seen: {stats['seen']} | fetched: {stats['fetched']} "
        f"| exported: {stats['exported']} | skipped current: {stats['skipped']} "
        f"| failed: {stats['failed']}\n"
    )
    if stats["failures"]:
        line += "- Failures:\n"
        for name, why in stats["failures"]:
            line += f"    - `{name}` — {why}\n"
    if not BUILD_LOG.exists():
        BUILD_LOG.write_text("# BUILD_LOG\n", encoding="utf-8")
    with BUILD_LOG.open("a", encoding="utf-8") as fh:
        fh.write(line)


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

    print(f"account : {account}")
    print(f"folder  : {folder_id}")
    print(f"cache   : {cache.relative_to(ROOT)}")
    print(f"scope   : {SCOPES[0]}\n")

    entries = walk(service, folder_id, Path("."), set())
    entries.sort(key=lambda e: str(e["rel_dir"] / e["safe_name"]))

    # An empty tree is a FAILURE, never a success. The most common cause is a
    # Shared Drive reached without the all-drives flags, which returns an empty
    # list and HTTP 200 rather than an error. Exiting 0 here would report a
    # successful build over an empty corpus.
    if not entries:
        meta = probe_folder(service, folder_id)
        sys.exit(
            "\nFATAL: enumerated 0 files.\n"
            f"  folder id   : {folder_id}\n"
            f"  folder probe: {meta}\n"
            f"  account     : {account}\n"
            "This is never a valid result. See README, 'If the folder returns "
            "nothing or 404s'."
        )

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
        return 0

    cache.mkdir(parents=True, exist_ok=True)
    (cache / "_manifest.json").write_text(
        json.dumps({"account": account, "folder_id": folder_id,
                    "fetched_at": datetime.now(timezone.utc).isoformat(),
                    "files": manifest}, indent=1),
        encoding="utf-8")

    append_build_log(account, folder_id, stats, cache.relative_to(ROOT))
    print(f"\nseen {stats['seen']} | fetched {stats['fetched']} "
          f"(exported {stats['exported']}) | current {stats['skipped']} "
          f"| failed {stats['failed']}")
    return 1 if stats["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
