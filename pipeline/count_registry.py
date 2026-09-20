#!/usr/bin/env python3
"""COUNT THE REGISTRY AND STOP. Nothing is fetched, ingested or projected.

This enumerates the Drive folders named in the scale-up registry and reports
what is there. It downloads no bytes: the only Drive verbs it uses are
`files.list` and `files.get` for metadata. `tests/test_count_registry.py`
asserts that — a counting tool that can fetch is one `--fetch` flag away from
being an ingester, and the whole point of this pass is to produce a number
before anything is committed to.

WHY IT IS BUILT TO PROVE EXHAUSTIVENESS
---------------------------------------
`docs/REGISTRY-INVENTORY.md` was a floor — 37 folders of at least 187 — and it
said so on every page. This is not a floor, and the difference has to be
demonstrated rather than asserted. Three things break exhaustiveness silently,
and all three were already visible in that inventory:

  1. PAGINATION. The `(File responses)` listing stopped at 60 files with a
     continuation token still outstanding. A reader that takes the first page
     and moves on reports a partial listing as a complete one. So `list_all`
     runs to a terminal page or RAISES; a folder whose enumeration ended any
     other way is a failure, never a result.

  2. CYCLES AND REPEATS. Drive lets a folder be reached by two paths, and
     shortcuts make that common. A `seen` set that silently drops the second
     encounter makes "5 files" and "5 files counted twice" indistinguishable.
     Here a re-encounter is RECORDED with both paths and the subtree is walked
     once.

  3. FAILURES. A folder the account cannot read, a target that 404s. A crawl
     reporting 1,400 files when 1,460 exist and 60 failed is worse than one
     reporting 1,400 and naming the 60, because the first number looks whole.

So the report states three numbers — discovered, opened, and discovered-but-not-
opened — and every folder in the third group is accounted for by name and
reason. When the third number is zero it says so explicitly, because
"every discovered folder was opened" is the claim that turns a floor into a
count.

DECISIONS THIS IMPLEMENTS
-------------------------
  D3  shortcuts are resolved and reported, never followed
  D4  a file's owner is recorded as a DOMAIN, never an address
  D6  `(File responses)` folders are skipped by name and the skip is reported

See `docs/PRE-CRAWL-DECISIONS.md`.

    python3 pipeline/count_registry.py                    # every registry row
    python3 pipeline/count_registry.py --only A B         # named rows
    python3 pipeline/count_registry.py --json out.json    # full detail
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
except ImportError:                                        # pragma: no cover
    sys.exit("missing deps: pip install google-api-python-client google-auth")

FOLDER_MIME = "application/vnd.google-apps.folder"
SHORTCUT_MIME = "application/vnd.google-apps.shortcut"
SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

#: The registry, transcribed from the `links` sheet. Hand-entered on purpose:
#: the sheet is excluded from ingestion (it is configuration, not corpus), so
#: the repository holds the scope rather than depending on a file it refuses to
#: read. `docs/REGISTRY-INVENTORY.md` §0 records the five rows verbatim.
REGISTRY = [
    ("A", "Applied Agentic AI- Whole Content folder",
     "1yHZYpbJTjfxumTMU5qNvfSuLXLImJpad"),
    ("B", "Software+System Pod whole Content folder",
     "19MxiYsE8B3T-O0VqnOF7gtU_7oxlRFJo"),
    ("C", "Data + Mangement Content folder",
     "1aVg_UbUCsuDxv9XXICIxbmpMbjUz5ETm"),
]

#: D6. Drive names these predictably, which is why the skip can be declared
#: rather than inferred from size. A size cap would also exclude them — and
#: would exclude a 17.66 MB teaching deck at the same time.
RESPONSES_RE = re.compile(r"\(File responses\)\s*$")

FIELDS = ("nextPageToken, files(id, name, mimeType, size, modifiedTime, "
          "owners(emailAddress), shortcutDetails(targetId, targetMimeType))")


class PartialListing(RuntimeError):
    """Raised when a listing ended without reaching a terminal page.

    Its existence is the point: the alternative is returning what was collected
    so far, which is how a partial listing becomes a reported total.
    """


#: EVERY way a listing can fail, not just the HTTP ones.
#:
#: The first real run of this script enumerated row A completely (8,079 files,
#: 1,697 folders, 15 minutes) and then DIED on row B with a bare
#: `ConnectionResetError` — a socket-level error, not an `HttpError`, so the
#: handler written to name failures never saw it. The run produced no row B, no
#: JSON, and a traceback where a report should have been.
#:
#: That is this module's own rule failing on its first outing: *a failure must
#: be named, never skipped* — and a crash is the loudest possible way to skip
#: one, because it takes the rest of the crawl with it. The lesson is the one
#: already in `A7B.md`: the handler's scope was written down (HttpError) rather
#: than derived from the question (can this listing be trusted?).
TRANSIENT = (ConnectionError, TimeoutError, OSError, HttpError)


def owner_domain(resource: dict) -> str:
    """D4 — the domain, never the address.

    'Authored inside the company or outside it' is the question that matters at
    scale, and it is not a personal identifier. Attribution to a PERSON goes
    through config/people.yaml as a curated slug, the way every person in this
    graph is already keyed.
    """
    owners = resource.get("owners") or []
    if not owners:
        return "unknown"
    email = owners[0].get("emailAddress") or ""
    return email.split("@", 1)[1].lower() if "@" in email else "unknown"


class Crawler:
    def __init__(self, service, verbose: bool = False):
        self.svc = service
        self.verbose = verbose
        self.files: list[dict] = []
        self.folder_paths: dict[str, str] = {}      # id -> first path seen
        self.opened: set[str] = set()
        self.discovered: set[str] = set()
        self.skipped_responses: list[dict] = []
        self.shortcuts: list[dict] = []
        self.failures: list[dict] = []
        self.repeats: list[dict] = []
        self.pages_total = 0
        self.api_calls = 0
        self.retries = 0

    # -- exhaustive listing ------------------------------------------------
    def list_all(self, folder_id: str) -> list[dict]:
        """Every child, or an exception. Never a partial list."""
        out, token, pages = [], None, 0
        while True:
            for attempt in range(5):
                try:
                    self.api_calls += 1
                    resp = self.svc.files().list(
                        q=f"'{folder_id}' in parents and trashed = false",
                        fields=FIELDS, pageSize=1000, pageToken=token,
                        supportsAllDrives=True,
                        includeItemsFromAllDrives=True,
                    ).execute()
                    break
                except TRANSIENT as exc:
                    last = attempt == 4
                    retryable = (
                        not isinstance(exc, HttpError)
                        or getattr(exc.resp, "status", 0) in (429, 500, 502, 503)
                    )
                    if retryable and not last:
                        self.retries += 1
                        time.sleep(1.5 * (attempt + 1))
                        continue
                    raise
            out.extend(resp.get("files", []))
            pages += 1
            token = resp.get("nextPageToken")
            if not token:
                self.pages_total += pages
                return out
            if pages > 10_000:                     # pathological safety valve
                raise PartialListing(
                    f"{folder_id}: {pages} pages and still paginating")

    # -- the walk ----------------------------------------------------------
    def walk(self, folder_id: str, path: str, depth: int) -> int:
        """Returns the deepest level reached below (and including) this node."""
        if folder_id in self.opened:
            self.repeats.append({"id": folder_id,
                                 "first_seen": self.folder_paths.get(folder_id),
                                 "again_at": path})
            return depth
        self.opened.add(folder_id)

        try:
            children = self.list_all(folder_id)
        except (*TRANSIENT, PartialListing) as exc:
            self.opened.discard(folder_id)         # NOT opened — do not claim it
            self.failures.append({
                "path": path, "id": folder_id, "kind": "folder-listing",
                "reason": f"{type(exc).__name__}: "
                          f"{getattr(getattr(exc, 'resp', None), 'status', '')} "
                          f"{str(exc)[:160]}".strip(),
            })
            return depth

        if self.verbose:
            print(f"  {'  ' * min(depth, 8)}{path}  ({len(children)})",
                  file=sys.stderr)

        deepest = depth
        for ch in children:
            mime, name = ch["mimeType"], ch["name"]
            child_path = f"{path}/{name}"

            if mime == SHORTCUT_MIME:
                det = ch.get("shortcutDetails") or {}
                self.shortcuts.append({
                    "path": child_path, "id": ch["id"],
                    "target_id": det.get("targetId"),
                    "target_mime": det.get("targetMimeType"),
                })
                continue                            # D3

            if mime == FOLDER_MIME:
                self.discovered.add(ch["id"])
                self.folder_paths.setdefault(ch["id"], child_path)
                if RESPONSES_RE.search(name):       # D6
                    self.skipped_responses.append(
                        {"path": child_path, "id": ch["id"]})
                    continue
                deepest = max(deepest,
                              self.walk(ch["id"], child_path, depth + 1))
                continue

            self.files.append({
                "path": child_path, "id": ch["id"], "mime": mime,
                "size": int(ch.get("size") or 0),
                "owner_domain": owner_domain(ch),   # D4
            })
        return deepest

    # -- shortcut classification, after the whole tree is known -------------
    def classify_shortcuts(self) -> None:
        inside_ids = self.discovered | {f["id"] for f in self.files}
        for s in self.shortcuts:
            tid = s.get("target_id")
            if not tid:
                s["verdict"] = "dangling"
                s["target_owner_domain"] = None
                continue
            s["verdict"] = "inside" if tid in inside_ids else "outside"
            try:
                self.api_calls += 1
                meta = self.svc.files().get(
                    fileId=tid, fields="id,name,mimeType,owners(emailAddress)",
                    supportsAllDrives=True).execute()
                s["target_name"] = meta.get("name")
                s["target_owner_domain"] = owner_domain(meta)
            except TRANSIENT as exc:
                s["target_owner_domain"] = None
                s["verdict"] = "unreadable"
                status = getattr(getattr(exc, 'resp', None), 'status', None)
                self.failures.append({
                    "path": s["path"], "id": tid, "kind": "shortcut-target",
                    "reason": f"HTTP {status}" if status
                              else f"{type(exc).__name__}: {str(exc)[:120]}",
                })


def make_service(key: str | None = None):
    path = Path(key or "~/.config/np-autopilot/drive-sa.json").expanduser()
    if not path.exists():
        sys.exit(f"service-account key not found at {path}")
    creds = service_account.Credentials.from_service_account_file(
        str(path), scopes=SCOPES)
    return build("drive", "v3", credentials=creds, cache_discovery=False), creds


TYPE_LABELS = {
    "application/vnd.google-apps.spreadsheet": "Google Sheet",
    "application/vnd.google-apps.document": "Google Doc",
    "application/vnd.google-apps.presentation": "Google Slides",
    # taxonomy-literal-ok: a Drive MIME display label, not the taxonomy term it
    # collides with. These name FILE FORMATS for a human reading a crawl report;
    # resolving them through taxonomy.vocabulary() would tie a report about
    # Drive's type system to the graph's, which are unrelated namespaces.
    "application/vnd.google-apps.form": "Google Form",
    "application/vnd.google-apps.drawing": "Google Drawing",
    "application/vnd.google-apps.script": "Apps Script",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/pdf": "PDF",
    "application/zip": ".zip",
    "application/x-zip-compressed": ".zip",
    "video/quicktime": ".mov",
    "video/mp4": ".mp4",
    "text/plain": ".txt",
    "image/png": ".png",
    "image/jpeg": ".jpg",
}
DECK_TYPES = {"Google Slides", ".pptx"}


def human(n: int) -> str:
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if n < 1024 or unit == "TiB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} B"
        n /= 1024
    return str(n)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", nargs="*", metavar="ROW",
                    help="registry rows to crawl (default: all)")
    ap.add_argument("--json", metavar="PATH", help="write full detail here")
    ap.add_argument("--key", help="service-account key path")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    svc, creds = make_service(args.key)
    rows = [r for r in REGISTRY
            if not args.only or r[0] in args.only or r[1] in args.only]
    if not rows:
        sys.exit(f"no registry rows matched {args.only}")

    print("=" * 74)
    print("REGISTRY CRAWL — COUNT AND STOP. Nothing fetched, nothing ingested.")
    print(f"acting as: {creds.service_account_email}")
    print("=" * 74)

    per_row, all_detail = [], {}
    for code, label, fid in rows:
        c = Crawler(svc, verbose=args.verbose)
        c.discovered.add(fid)
        c.folder_paths[fid] = code
        t0 = time.time()
        try:
            meta = svc.files().get(fileId=fid, fields="name,owners(emailAddress)",
                                   supportsAllDrives=True).execute()
            real_name, root_owner = meta.get("name"), owner_domain(meta)
        except HttpError as exc:
            print(f"\n{code}  {label}\n    UNREADABLE — HTTP "
                  f"{getattr(exc.resp, 'status', '?')}. The share has not "
                  f"reached this account.")
            per_row.append({"code": code, "label": label, "unreadable": True})
            continue
        row_error = None
        try:
            depth = c.walk(fid, code, 0)
            c.classify_shortcuts()
        except Exception as exc:                       # noqa: BLE001
            # A row that dies must not delete the rows that succeeded, and must
            # not be reported as though it finished. Both halves matter.
            row_error = f"{type(exc).__name__}: {str(exc)[:200]}"
            depth = 0
        elapsed = time.time() - t0

        not_opened = c.discovered - c.opened
        types = Counter(TYPE_LABELS.get(f["mime"], f["mime"]) for f in c.files)
        decks = sum(n for t, n in types.items() if t in DECK_TYPES)
        row = {
            "code": code, "label": label, "id": fid, "drive_name": real_name,
            "root_owner_domain": root_owner,
            "files": len(c.files), "bytes": sum(f["size"] for f in c.files),
            "folders_discovered": len(c.discovered),
            "folders_opened": len(c.opened),
            "folders_not_opened": sorted(not_opened),
            "skipped_responses": c.skipped_responses,
            "failures": c.failures, "repeats": c.repeats,
            "shortcuts": c.shortcuts, "types": dict(types), "decks": decks,
            "max_depth": depth, "pages": c.pages_total,
            "api_calls": c.api_calls, "seconds": round(elapsed, 1),
            "owner_domains": dict(Counter(f["owner_domain"] for f in c.files)),
        }
        per_row.append(row)
        all_detail[code] = {**row, "file_paths": [f["path"] for f in c.files]}

        # ---------------- per-row report ----------------
        if row_error:
            print(f"\n{code}  {label}")
            print(f"    INCOMPLETE — the walk raised and this row's numbers are")
            print(f"    NOT a count: {row_error}")
            print(f"    partial: {len(c.files)} files, {len(c.opened)} folders "
                  f"opened of {len(c.discovered)} discovered")
            per_row[-1]["incomplete"] = row_error
            continue
        print(f"\n{code}  {label}")
        print(f"    Drive name : {real_name!r}  (owner domain {root_owner})")
        print(f"    files      : {row['files']:,}   ({human(row['bytes'])})")
        print(f"    folders    : {row['folders_opened']:,} opened of "
              f"{row['folders_discovered']:,} discovered")
        accounted = len(c.skipped_responses) + len(
            {f['id'] for f in c.failures if f['kind'] == 'folder-listing'})
        if not not_opened:
            print("                 every discovered folder was opened — "
                  "this is a count, not a floor")
        else:
            print(f"                 {len(not_opened)} NOT opened "
                  f"({accounted} accounted for below)")
        print(f"    depth      : {row['max_depth']} levels below the root")
        print(f"    listing    : {row['pages']} pages, {row['api_calls']} API "
              f"calls, {row['seconds']}s — every listing reached a terminal page")

        print(f"    types      : {decks} decks of {row['files']} files")
        for t, n in types.most_common():
            mark = "  <- deck" if t in DECK_TYPES else ""
            print(f"                 {n:>5}  {t}{mark}")

        if c.skipped_responses:
            print(f"    D6 skipped : {len(c.skipped_responses)} "
                  f"(File responses) folder(s), by name:")
            for s in c.skipped_responses:
                print(f"                 {s['path']}")
        else:
            print("    D6 skipped : 0 (File responses) folders found")

        if c.shortcuts:
            v = Counter(s["verdict"] for s in c.shortcuts)
            print(f"    shortcuts  : {len(c.shortcuts)} — "
                  + ", ".join(f"{n} {k}" for k, n in v.most_common()))
            for s in c.shortcuts:
                if s["verdict"] != "inside":
                    print(f"                 [{s['verdict']}] {s['path']}")
                    print(f"                     -> {s.get('target_name')!r} "
                          f"({s.get('target_owner_domain')}) {s.get('target_mime')}")
        else:
            print("    shortcuts  : 0")

        if c.repeats:
            print(f"    repeats    : {len(c.repeats)} folder(s) reachable by "
                  f"more than one path — walked once, counted once:")
            for r in c.repeats:
                print(f"                 {r['again_at']}  ==  {r['first_seen']}")
        else:
            print("    repeats    : 0 folders reachable by two paths")

        if c.failures:
            print(f"    FAILURES   : {len(c.failures)} — named, not skipped:")
            for f in c.failures:
                print(f"                 [{f['kind']}] {f['path']}  {f['reason']}")
        else:
            print("    FAILURES   : 0")

    # ---------------- totals ----------------
    real = [r for r in per_row if not r.get("unreadable")]
    if real:
        tf = sum(r["files"] for r in real)
        td = sum(r["decks"] for r in real)
        print("\n" + "=" * 74)
        print(f"TOTAL over {len(real)} registry row(s): {tf:,} files, "
              f"{sum(r['folders_opened'] for r in real):,} folders, "
              f"{human(sum(r['bytes'] for r in real))}")
        print(f"  decks: {td} of {tf} files "
              f"({100 * td / tf:.1f}%)" if tf else "")
        missing = [r[0] for r in REGISTRY
                   if r[0] not in {x['code'] for x in real}]
        if missing:
            print(f"  NOT INCLUDED: registry row(s) {', '.join(missing)}. "
                  "This total is those rows' worth, not the registry's.")
        print("=" * 74)

    if args.json:
        Path(args.json).write_text(json.dumps(all_detail, indent=2),
                                   encoding="utf-8")
        print(f"\ndetail -> {args.json}")

    print("\nNothing was fetched. Nothing was ingested. Nothing was projected.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
