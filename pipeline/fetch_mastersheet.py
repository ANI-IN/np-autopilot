"""Fetch the LIVE mastersheet as .xlsx — read-only, outside the repo.

Owner decision (Animesh Kumar, 2026-09-30, origin: hand): the live Google
Sheet the team maintains replaces the corpus copy as the source of every
mastersheet-derived fact. It is a native Sheet, so it is EXPORTED as .xlsx —
the format that keeps cell fills, which is how a withdrawn instructor is
marked (red).

WHERE IT LANDS, AND WHY NOT .drive-cache/. The export carries contact data
(personal emails and Discord links in excluded tabs, contact columns in the
instructor tables). Pass 1 walks every file under .drive-cache/, and the repo
sits under a cloud-synced folder (R22, deferred). So the file goes to
NP_MASTERSHEET_DIR (default ~/.config/np-autopilot/mastersheet/, mode 700),
never inside the repo — refused, as pass 0 refuses a key inside the repo.

Beside it, `<id>.json` records what was fetched (Drive modifiedTime, version,
fetch time, sha256), which the freshness guard compares against Drive.

Scope is pass 0's: service account, drive.readonly, no delegation.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from pipeline.lib import freshness                                    # noqa: E402

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def target_dir() -> Path:
    d = freshness.live_dir().resolve()
    try:
        d.relative_to(REPO)
    except ValueError:
        return d
    sys.exit(f"refusing to write the live mastersheet inside the repo: {d} — it "
             "carries contact data; use a directory outside the repo")


def main() -> int:
    file_id = freshness.source_id()
    service = freshness._drive_service()
    meta = service.files().get(fileId=file_id, supportsAllDrives=True,
                               fields="id,name,mimeType,modifiedTime,version").execute()
    if meta["mimeType"] == "application/vnd.google-apps.spreadsheet":
        data = service.files().export(fileId=file_id, mimeType=XLSX).execute()
    else:
        data = service.files().get_media(fileId=file_id, supportsAllDrives=True).execute()

    d = target_dir()
    d.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(d, 0o700)
    out = d / f"{file_id}.xlsx"
    tmp = out.with_suffix(".part")
    tmp.write_bytes(data)
    os.chmod(tmp, 0o600)
    tmp.replace(out)
    record = {"id": meta["id"], "name": meta["name"], "mime": meta["mimeType"],
              "modified": meta["modifiedTime"], "version": meta.get("version"),
              "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
    side = d / f"{file_id}.json"
    side.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    os.chmod(side, 0o600)
    print(f"  fetched {meta['name']} ({file_id}) — Drive modified {meta['modifiedTime']}, "
          f"version {meta.get('version')}, {len(data):,} bytes, sha256 {record['sha256'][:16]}")
    print(f"  -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
