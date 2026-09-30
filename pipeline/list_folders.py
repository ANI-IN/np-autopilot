"""List the row-B FOLDERS — metadata only (owner requirement, B4 (i), 2026-09-30).

Pass 6 recorded every file's id but no folder's, so a module or a session had
no Drive folder link and the UI said "pass 6 records file ids, not folder ids".
This walks the SAME tree under the SAME scope as pass 6 — registry row B, the
four D2a-approved domain folders at depth 0, content_scope.classify_folder's
skip rules below — and asks Drive for FOLDERS ONLY:

    q = "'<parent>' in parents and mimeType = '<folder>' and trashed = false"

No file is listed, exported or downloaded; no media is touched. Output, beside
pass 6's manifest (pass 1 does not read this directory):

    .drive-cache/content-rowB/folders.json
        {folder_id: {"name", "path", "parent"}}

Scope is pass 0's service account, drive.readonly, no delegation.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import time
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from pipeline.lib import approval                                      # noqa: E402
from pipeline.lib import content_scope as scope                        # noqa: E402
from pipeline.lib.paths import REPO_ROOT, build_log                    # noqa: E402

FOLDER = "application/vnd.google-apps.folder"
OUT = REPO_ROOT / ".drive-cache" / "content-rowB" / "folders.json"


def _load(name: str, file: str):
    spec = importlib.util.spec_from_file_location(name, REPO / "pipeline" / file)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def list_folders(service, limiter, folder_id: str) -> list[dict]:
    """Every child FOLDER of one folder. Folders only, by the query itself."""
    out, token = [], None
    while True:
        resp = limiter(lambda: service.files().list(
            q=f"'{folder_id}' in parents and mimeType = '{FOLDER}' and trashed = false",
            fields="nextPageToken, files(id, name)", pageSize=1000, pageToken=token,
            supportsAllDrives=True, includeItemsFromAllDrives=True).execute())
        out.extend(resp.get("files", []))
        token = resp.get("nextPageToken")
        if not token:
            return out


def walk(service, limiter, root_id: str, approved: list) -> tuple[dict, Counter]:
    folders: dict = {}
    stats: Counter = Counter()

    def visit(fid: str, path: str, depth: int) -> None:
        stats["listed"] += 1
        for f in list_folders(service, limiter, fid):
            name, child = f["name"], f"{path}/{f['name']}"
            if depth == 0 and name not in approved:
                stats["out-of-scope-domain"] += 1
                continue
            d = scope.classify_folder(child, name)
            if d.action == "skip":
                stats[f"skip:{d.rule}"] += 1
                continue
            folders[f["id"]] = {"name": name, "path": child, "parent": fid}
            visit(f["id"], child, depth + 1)

    visit(root_id, "", 0)
    return folders, stats


def main() -> int:
    p0 = _load("np_fetch_drive", "00_fetch_drive.py")
    p6 = _load("np_crawl_content", "06_crawl_content.py")
    service, account = p0.authenticate(p0.load_config())
    if not scope.in_scope(scope.ROW_B_ID):
        sys.exit("row B is not in SCOPE_ROOTS — scope comes from the registry")
    ok = approval.require_d2a()
    started = time.time()
    folders, stats = walk(service, p6._Limiter(), scope.ROW_B_ID, ok.domains)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(folders, indent=1, sort_keys=True), encoding="utf-8")
    print(f"  folders recorded: {len(folders)}  (listed {stats['listed']} parents; "
          f"skipped {sum(v for k, v in stats.items() if k != 'listed')})")
    print(f"  -> {OUT.relative_to(REPO_ROOT)}")
    with build_log().open("a", encoding="utf-8") as fh:
        fh.write(f"\n## {time.strftime('%Y-%m-%d %H:%M:%SZ', time.gmtime())} — list_folders\n\n"
                 f"- Account: `{account}`\n- Folders: {len(folders)} (metadata only)\n"
                 f"- Skips: {dict((k, v) for k, v in stats.items() if k != 'listed')}\n"
                 f"- Seconds: {time.time() - started:.0f}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
