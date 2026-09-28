#!/usr/bin/env python3
"""Pass 6 — crawl the row-B curriculum content for the four approved domains.

SEPARATE FROM PASS 0, and deliberately. Pass 0 fetches the 75-file NP corpus
into `.drive-cache/` and pass 1 hashes a manifest where a CHANGED file is a hard
fail. This crawl writes into its own subdirectory of that cache and keeps its own
manifest, so a curriculum deck moving in Drive can never trip the corpus
integrity check — two corpora with two contracts, not one with an exception.

WHAT IT REFUSES TO DO, each with a test and a mutation record:

  scope        only the registry's declared row B, and only the four approved
               domain folders. NEVER "the account can read it" — row C is
               shared `anyone`, so for C that proxy's answer is the public
               internet (REGISTRY-INVENTORY §12).
  D1           people are never extracted from deck content, or (deferred)
               from a deck filename.
  D3           shortcuts are recorded and never followed.
  D4           a file owner is reduced to its domain before it is stored.
  D5 / D6      declared skips, by name, counted and reported per rule.
  media        video, audio, images and archives are recorded and never
               downloaded — 15.55 GiB of the 16.67 GiB measured in scope.
  learner      assignment-review material is metadata only.
  redaction    applied to the text BEFORE it reaches disk, at threshold one.

The rules live in `lib/content_scope.py` and `lib/redact.py` so that this file
cannot quietly acquire a second copy of one.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import sys
import time
from collections import Counter
from pathlib import Path
from typing import NamedTuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.lib import approval                                      # noqa: E402
from pipeline.lib import content_scope as scope                        # noqa: E402
from pipeline.lib import extract_text as ex                            # noqa: E402
from pipeline.lib import redact as rd                                  # noqa: E402
from pipeline.lib.paths import REPO_ROOT, build_log                    # noqa: E402

#: Its OWN subdirectory of the cache. Never the corpus folders.
CACHE_SUBDIR = "content-rowB"

FOLDER = "application/vnd.google-apps.folder"
SHORTCUT = "application/vnd.google-apps.shortcut"

#: Native Google types export straight to text. A Slides deck exports to plain
#: text at 0.8% of its .pptx size — measured on 10 files, 16.9 KB against
#: 2,218 KB — and text export SUCCEEDED on a deck whose .pptx export failed.
TEXT_EXPORT = {
    "application/vnd.google-apps.document": "text/plain",
    "application/vnd.google-apps.presentation": "text/plain",
    "application/vnd.google-apps.spreadsheet": "text/csv",
}

FIELDS = ("nextPageToken, files(id, name, mimeType, modifiedTime, size, "
          "owners(emailAddress), shortcutDetails(targetId, targetMimeType))")

#: ~10 requests/second. count_registry sustained 1.9/s without trouble.
RATE_LIMIT_SECONDS = 0.1


class CrawlResult(NamedTuple):
    cache_dir: Path
    manifest: dict
    skips: Counter
    stats: Counter
    shortcuts: list


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class _Limiter:
    """One call per `interval`, and retry-with-backoff that understands 403.

    THE 403 MATTERS AND IS NOT COSMETIC. Google Drive signals throttling with
    **HTTP 403 and reason `rateLimitExceeded`/`userRateLimitExceeded`**, not
    429. `count_registry.py` retries only on 429/500/502/503, so on
    2026-09-29 it recorded two folders as permanent `folder-listing` failures
    that a second reader listed successfully minutes later — and its summary
    reported them as un-opened folders rather than as throttling.

    A permission 403 must still be fatal, so the two are told apart by reason
    rather than by status. Collapsing them in either direction is the bug.
    """

    RATE_REASONS = {"ratelimitexceeded", "userratelimitexceeded",
                    "sharingratelimitexceeded", "backenderror"}

    def __init__(self, interval: float = RATE_LIMIT_SECONDS, attempts: int = 5):
        self.interval, self.attempts = interval, attempts
        self._last = 0.0
        self.retries = 0

    def _is_rate_limit(self, exc) -> bool:
        status = getattr(getattr(exc, "resp", None), "status", 0)
        if status in (429, 500, 502, 503):
            return True
        if status != 403:
            return False
        blob = str(getattr(exc, "content", b"") or "") + str(exc)
        return any(r in blob.lower().replace("_", "") for r in self.RATE_REASONS)

    def __call__(self, fn):
        for attempt in range(self.attempts):
            gap = self.interval - (time.time() - self._last)
            if gap > 0:
                time.sleep(gap)
            self._last = time.time()
            try:
                return fn()
            except Exception as exc:                               # noqa: BLE001
                if attempt == self.attempts - 1 or not self._is_rate_limit(exc):
                    raise
                self.retries += 1
                time.sleep(1.5 * (attempt + 1))
        raise RuntimeError("unreachable")


def _list_all(service, limiter, folder_id: str) -> list[dict]:
    """Every child, or raise. Never a partial page — a partial listing reported
    as a total is how `count_registry.py`'s own docstring says a crawl lies."""
    out, token = [], None
    while True:
        resp = limiter(lambda: service.files().list(
            q=f"'{folder_id}' in parents and trashed = false",
            fields=FIELDS, pageSize=1000, pageToken=token,
            supportsAllDrives=True, includeItemsFromAllDrives=True,
        ).execute())
        out.extend(resp.get("files", []))
        token = resp.get("nextPageToken")
        if not token:
            return out


def _safe_name(path: str, file_id: str = "") -> str:
    """A cache filename that cannot escape the cache directory, and cannot
    collide with another path's.

    THE TRUNCATION WAS A BUG AND IT WAS SILENT. This returned the first 180
    characters of the sanitised path. In the first real crawl that collapsed 61
    files onto 15 names — 46 exports overwritten, including 14 distinct
    foundational-content files in one SD2 folder whose paths differ only in
    their last component, far past character 180. The manifest recorded each
    row's own sha256 while the file on disk held the last writer's text, so the
    manifest was wrong and resume was wrong with it, and nothing errored:
    the failure produced output.

    THE SUFFIX HASHES THE FILE ID, NOT THE PATH. Hashing the path fixed the
    truncation collisions and left a second class behind: Drive permits two
    files with the SAME NAME in the SAME FOLDER, so two distinct files share
    one path and collide however much of that path you hash. That cost 2 more
    exports in the second crawl, in SD1's JavaScript module. A path is not an
    identity in Drive; the file id is.

    `..` is collapsed as well — it could not traverse once separators were
    gone, but a name that still reads as a traversal is one refactor away from
    being one.
    """
    clean = re.sub(r"[^A-Za-z0-9_.-]+", "_", path.strip("/"))
    clean = clean.replace("..", "_")
    digest = hashlib.sha256((file_id or path).encode("utf-8")).hexdigest()[:12]
    return f"{clean[:150]}_{digest}"


def crawl(service, root_id: str, cache_root: Path, *, approved_domains: list,
          report: bool = False,
          interval: float = RATE_LIMIT_SECONDS) -> CrawlResult:
    """`approved_domains` is REQUIRED and comes from D2a's approval block.

    Not defaulted, and not read from `content_scope` here, so there is no path
    into this function that has not stated its approved scope — the same
    property `api/index.py` has for the route guard: a caller cannot bring its
    own front door.
    """
    if not approved_domains:
        raise ValueError(
            "approved_domains is empty. The approved scope comes from D2a's "
            "approval block in docs/PRE-CRAWL-DECISIONS.md, via "
            "pipeline/lib/approval.require_d2a().")
    cache_root = Path(cache_root)
    cache_dir = cache_root / CACHE_SUBDIR
    cache_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = cache_dir / "manifest.json"
    previous = (json.loads(manifest_path.read_text(encoding="utf-8"))
                if manifest_path.exists() else {})

    limiter = _Limiter(interval)
    manifest: dict = {}
    skips: Counter = Counter()
    stats: Counter = Counter()
    shortcuts: list = []

    def walk(folder_id: str, path: str, depth: int) -> None:
        stats["folders_opened"] += 1
        for e in _list_all(service, limiter, folder_id):
            name, mime = e["name"], e["mimeType"]
            child = f"{path}/{name}"

            if mime == SHORTCUT:                                   # D3
                sd = e.get("shortcutDetails") or {}
                shortcuts.append({"path": child,
                                  "target_mime": sd.get("targetMimeType")})
                skips["D3-shortcut"] += 1
                continue

            if mime == FOLDER:
                # Level 1 is the domain partition: only the four approved.
                if depth == 0 and name not in approved_domains:
                    skips["out-of-scope-domain"] += 1
                    continue
                d = scope.classify_folder(child, name)
                if d.action == "skip":
                    skips[d.rule] += 1
                    continue
                walk(e["id"], child, depth + 1)
                continue

            decision = scope.classify_file(child, name, mime)
            stats["files_seen"] += 1
            row = {
                "path": child,
                "name": name,
                "mime": mime,
                "modifiedTime": e.get("modifiedTime"),
                "size": int(e["size"]) if e.get("size") else None,
                # D4: the domain, never the address. Reduced here, at the only
                # point the address is in memory at all.
                "owner_domain": scope.owner_domain(
                    (e.get("owners") or [{}])[0].get("emailAddress")),
                "action": decision.action,
                "rule": decision.rule,
                "may_extract_people": scope.may_extract_people(mime),
            }

            if decision.action != "export":
                skips[decision.rule] += 1
                row["sha256"] = None
                row["sha256_of"] = None
                manifest[e["id"]] = row
                continue

            prior = previous.get(e["id"])
            if (prior and prior.get("modifiedTime") == row["modifiedTime"]
                    and prior.get("text_path")
                    and (cache_dir / prior["text_path"]).exists()):
                stats["unchanged"] += 1
                manifest[e["id"]] = {**prior, **row,
                                     "text_path": prior["text_path"],
                                     "sha256": prior.get("sha256"),
                                     "sha256_of": prior.get("sha256_of"),
                                     "redacted": prior.get("redacted", {})}
                continue

            body, meta = _fetch_text(service, limiter, e["id"], mime, name)
            if body is None:
                # NOT an error, and not silent. A file with no extractor is
                # recorded with the reason, because "no text" and "text we
                # failed to read" must not look the same downstream.
                stats["no_text"] += 1
                row["action"] = "metadata_only"
                row["rule"] = "no-text-extractor"
                row["reason"] = meta.get("reason")
                row["sha256"] = None
                row["sha256_of"] = None
                skips["no-text-extractor"] += 1
                manifest[e["id"]] = row
                continue

            # REDACTION BEFORE DISK. There is no code path that writes `body`.
            text, counts = rd.redact(body)
            row.update({k: v for k, v in meta.items() if k != "reason"})
            rel = f"text/{_safe_name(child, e['id'])}.txt"
            dest = cache_dir / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(text, encoding="utf-8")

            row["text_path"] = rel
            row["redacted"] = counts
            row["sha256"] = _sha256(text.encode("utf-8"))
            # Named, because a sha256 that is not of the source bytes and does
            # not say so is a hash pretending to be an integrity check.
            row["sha256_of"] = "redacted-text"
            stats["exported"] += 1
            if counts:
                stats["files_with_redactions"] += 1
            manifest[e["id"]] = row

    walk(root_id, "", 0)

    manifest_path.write_text(json.dumps(manifest, indent=1, sort_keys=True),
                             encoding="utf-8")

    bad = [k for k, v in manifest.items() if not scope.provenance_is_clean(v)]
    if bad:                                                        # D4, derived
        raise RuntimeError(
            f"{len(bad)} manifest rows contain '@'. No provenance field may "
            "carry an address; the owner is stored as a domain.")

    if report:
        _report(cache_dir, manifest, skips, stats, shortcuts, limiter)
    return CrawlResult(cache_dir, manifest, skips, stats, shortcuts)


def _fetch_text(service, limiter, file_id: str, mime: str,
                name: str) -> tuple[str | None, dict]:
    """(text, meta) or (None, {"reason": ...}).

    A native Google file exports AS text and needs no parsing. Anything else is
    downloaded and handed to `lib/extract_text.py`, which returns None rather
    than decoded noise — the defect this replaced wrote zip bytes into a .txt.
    Media never reaches here; classify_file held it back.
    """
    try:
        if mime in TEXT_EXPORT:
            data = limiter(lambda: service.files().export(
                fileId=file_id, mimeType=TEXT_EXPORT[mime]).execute())
            return data.decode("utf-8", "replace"), {}
        from googleapiclient.http import MediaIoBaseDownload
        buf = io.BytesIO()
        req = service.files().get_media(fileId=file_id, supportsAllDrives=True)
        dl = MediaIoBaseDownload(buf, req)
        done = False
        while not done:
            _, done = limiter(lambda: dl.next_chunk())
        return ex.extract(buf.getvalue(), mime, name)
    except Exception as exc:                                       # noqa: BLE001
        return None, {"reason": f"{type(exc).__name__} fetching {mime}"}


def _report(cache_dir, manifest, skips, stats, shortcuts, limiter) -> None:
    """COUNT, DO NOT ENUMERATE — CLAUDE.md §5. One line per category."""
    print("=" * 74)
    print("PASS 6 — row B content crawl. Four approved domains.")
    print("=" * 74)
    print(f"  cache          : {cache_dir}")
    print(f"  folders opened : {stats['folders_opened']}")
    print(f"  files seen     : {stats['files_seen']}")
    print(f"  exported       : {stats['exported']}   unchanged: {stats['unchanged']}")
    print(f"  redacted in    : {stats['files_with_redactions']} files")
    print(f"  no text        : {stats['no_text']} (recorded with a reason)")
    print(f"  rate retries   : {limiter.retries}")
    if skips:
        print("  skipped by rule: " + ", ".join(
            f"{n}x {rule}" for rule, n in sorted(skips.items())))
    if shortcuts:
        print(f"  shortcuts      : {len(shortcuts)} recorded, 0 followed (D3)")
    print("  people from decks: NEVER (D1). Instructors are a later phase.")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", default=str(REPO_ROOT / ".drive-cache"))
    ap.add_argument("--interval", type=float, default=RATE_LIMIT_SECONDS)
    args = ap.parse_args()

    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "np_fetch_drive", REPO_ROOT / "pipeline" / "00_fetch_drive.py")
    p0 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(p0)

    cfg = p0.load_config()
    service, account = p0.authenticate(cfg)

    if not scope.in_scope(scope.ROW_B_ID):
        sys.exit("row B is not in SCOPE_ROOTS — scope comes from the registry")

    # THE FIRST THING THIS PASS DOES. A blank block refuses the crawl and names
    # the file, the way project_graph.py --scope full names
    # docs/INGEST-SCOPE-REVERSAL.md.
    try:
        ok = approval.require_d2a()
    except approval.NotApproved as exc:
        sys.exit(f"REFUSING TO CRAWL.\n\n{exc}")
    print(f"D2a approved by {ok.approved_by} on {ok.date} — "
          f"{len(ok.domains)} domain(s) in scope")

    started = time.time()
    result = crawl(service, scope.ROW_B_ID, Path(args.cache),
                   approved_domains=ok.domains,
                   report=True, interval=args.interval)
    log = build_log()
    with log.open("a", encoding="utf-8") as fh:
        fh.write(f"\n## {time.strftime('%Y-%m-%d %H:%M:%SZ', time.gmtime())} "
                 f"— 06_crawl_content\n\n"
                 f"- Account: `{account}`\n"
                 f"- Files: {result.stats['files_seen']}, "
                 f"exported {result.stats['exported']}\n"
                 f"- Skips: {dict(result.skips)}\n"
                 f"- Seconds: {time.time() - started:.0f}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
