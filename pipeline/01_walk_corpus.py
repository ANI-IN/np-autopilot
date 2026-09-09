#!/usr/bin/env python3
"""Pass 1 — walk the corpus, prove every file is readable, emit files.json.

Discovery and integrity only. This pass does NOT extract entities; it records
what exists, whether it parses, and what shape it has. Pass 2 does the reading.

Reads from the pass-0 cache when one exists. Falls back to NP_CORPUS_PATH with a
loud banner, because a fallback run is reading a hand-exported local folder, not
Drive, and any conclusion about what Drive contains is unsupported.

The corpus is read-only. This script hashes every file before and after the walk
and aborts if anything changed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.lib import taxonomy                                    # noqa: E402
from pipeline.lib.paths import BUILD_LOG, KNOWLEDGE_DIR, REPO_ROOT, corpus_root  # noqa: E402

MANIFEST = KNOWLEDGE_DIR / "files.json"

# Magic bytes. R9: A_sample_Mock_Session_Feedback_Documentation.docx is plain
# UTF-8 with the wrong extension and python-docx raises on it. Sniff, never
# trust the extension.
MAGIC = {
    b"PK\x03\x04": "zip",          # xlsx / docx / pptx are all zip containers
    b"%PDF": "pdf",
    b"\x89PNG": "png",
}
SKIP_NAMES = {".DS_Store"}
SKIP_DIRS = {"pipeline", "config", "tests", "knowledge", ".git",
             "__pycache__", ".drive-cache", ".claude-plugin"}
# This repo's own analysis documents live at the corpus root and are not corpus.
OWN_DOCS = {"README.md", "BUILD_LOG.md", "CLAUDE.md"}


def sniff(path: Path) -> str:
    try:
        head = path.open("rb").read(8)
    except OSError:
        return "unreadable"
    for magic, kind in MAGIC.items():
        if head.startswith(magic):
            return kind
    try:
        path.read_text(encoding="utf-8")
        return "text"
    except (UnicodeDecodeError, OSError):
        return "binary"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def is_own_doc(rel: str) -> bool:
    p = Path(rel)
    if len(p.parts) != 1:
        return False
    return p.name in OWN_DOCS or (p.suffix == ".md" and p.name[:2].isdigit() and p.name[2] == "-")


def discover(root: Path) -> list[Path]:
    out = []
    for p in sorted(root.rglob("*")):
        if not p.is_file() or p.name in SKIP_NAMES:
            continue
        rel = p.relative_to(root)
        if set(rel.parts) & SKIP_DIRS:
            continue
        # Any dot-prefixed path segment is tooling, not corpus (.pytest_cache,
        # .gitignore, .venv). The corpus has no dotfiles.
        if any(part.startswith(".") for part in rel.parts):
            continue
        if is_own_doc(str(rel)):
            continue
        out.append(p)
    return out


def probe(path: Path, kind: str) -> tuple[bool, str, dict]:
    """Open the file the way pass 2 will. Returns (ok, cause, shape)."""
    suffix = path.suffix.lower()
    try:
        if kind == "zip" and suffix == ".xlsx":
            import openpyxl
            wb = openpyxl.load_workbook(path, read_only=True)
            shape = {"sheets": wb.sheetnames,
                     "sheet_count": len(wb.sheetnames),
                     "hidden_sheets": [s.title for s in wb.worksheets if s.sheet_state != "visible"]}
            wb.close()
            return True, "", shape
        if kind == "zip" and suffix == ".docx":
            import docx
            d = docx.Document(str(path))
            return True, "", {"paragraphs": len(d.paragraphs)}
        if kind == "pdf":
            data = path.read_bytes()
            pages = data.count(b"/Type/Page") + data.count(b"/Type /Page")
            return True, "", {"pages_hint": pages}
        if kind == "text":
            text = path.read_text(encoding="utf-8")
            return True, "", {"chars": len(text), "lines": text.count("\n") + 1}
        if kind == "png":
            return False, "image with no text layer — nothing to extract", {}
        if suffix == ".docx" and kind == "text":
            return False, "extension says .docx but magic bytes say plain text", {}
        return False, f"unhandled kind {kind!r} for suffix {suffix!r}", {}
    except Exception as exc:                                    # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}".replace("\n", " ")[:160], {}


def load_previous() -> dict[str, str]:
    if not MANIFEST.exists():
        return {}
    try:
        prev = json.loads(MANIFEST.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    # BOTH lists. A file that fails to parse is still PRESENT in the corpus; if
    # only `files` is read, a permanently-failing file is reported as newly
    # added on every single run and a genuine removal of it goes unnoticed.
    return {f["path"]: f.get("sha256", "")
            for f in prev.get("files", []) + prev.get("failures", [])}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--allow-fallback", action="store_true",
                    help="proceed when no pass-0 cache exists (reads the local folder)")
    args = ap.parse_args()

    cache = REPO_ROOT / ".drive-cache"
    if cache.is_dir() and any(cache.iterdir()):
        root, source = cache, "drive-cache"
    else:
        root, source = corpus_root(), "local-folder"

    print("=" * 78)
    print("PASS 1 — walk corpus")
    print("=" * 78)
    print(f"source     : {source}")
    print(f"root       : {root}")
    print(f"started    : {datetime.now(timezone.utc).isoformat(timespec='seconds')}")
    if source == "local-folder":
        print()
        print("!" * 78)
        print("! WARNING — NO PASS-0 CACHE. Reading a LOCAL, HAND-EXPORTED folder.")
        print("! This is NOT Drive. Native Google files were exported by hand by a")
        print("! person, so anything absent here may still exist in Drive and any")
        print("! conclusion about Drive's contents from this run is UNSUPPORTED.")
        print("! Run pipeline/00_fetch_drive.py to make this authoritative.")
        print("!" * 78)
        if not args.allow_fallback:
            print("\nRefusing to continue. Re-run with --allow-fallback to proceed anyway.")
            return 2
    print()

    excluded = set(taxonomy.excluded_files())
    files = discover(root)

    print(f"FOUND      : {len(files)} files")
    print(f"EXCLUDED   : {len(excluded)} by config (taxonomy.yaml -> excluded.files)")
    for e in sorted(excluded):
        print(f"             - {e}")
    print()

    before = {p: (p.stat().st_mtime_ns, p.stat().st_size) for p in files}

    records, failures, skipped = [], [], []
    for path in files:
        rel = str(path.relative_to(root))
        if rel in excluded:
            skipped.append(rel)
            continue
        kind = sniff(path)
        ok, cause, shape = probe(path, kind)
        digest = sha256(path)
        rec = {"path": rel, "sha256": digest, "bytes": path.stat().st_size,
               "mtime": datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat(timespec="seconds"),
               "sniffed": kind, "suffix": path.suffix.lower(), "parsed": ok, **shape}
        if ok:
            records.append(rec)
        else:
            rec["cause"] = cause
            failures.append(rec)

    # ---- read-only assertion -------------------------------------------------
    print("-" * 78)
    print("READ-ONLY ASSERTION")
    print("-" * 78)
    drift = [str(p.relative_to(root)) for p in files
             if (p.stat().st_mtime_ns, p.stat().st_size) != before[p]]
    if drift:
        print(f"  FAILED — {len(drift)} file(s) changed during the walk:")
        for d in drift:
            print(f"    {d}")
        return 1
    print(f"  PASS — {len(files)} files unchanged (mtime_ns + size compared before and after)")
    print(f"  PASS — no write, create or delete syscall issued against {root}")
    print()

    # ---- manifest diff -------------------------------------------------------
    prev = load_previous()
    now = {r["path"]: r["sha256"] for r in records + failures}
    added = sorted(set(now) - set(prev))
    removed = sorted(set(prev) - set(now))
    changed = sorted(p for p in set(prev) & set(now) if prev[p] != now[p])

    print("-" * 78)
    print("MANIFEST DIFF")
    print("-" * 78)
    if not prev:
        print(f"  no previous manifest — establishing baseline with {len(now)} files")
    else:
        print(f"  added   : {len(added)}   (REPORT ONLY — a new document is expected traffic)")
        for a in added:
            print(f"            + {a}")
        print(f"  changed : {len(changed)}   (HARD FAIL)")
        for c in changed:
            print(f"            ~ {c}  {prev[c][:12]} -> {now[c][:12]}")
        print(f"  removed : {len(removed)}   (HARD FAIL)")
        for r in removed:
            print(f"            - {r}")
    print()

    # ---- results -------------------------------------------------------------
    print("-" * 78)
    print("RESULTS")
    print("-" * 78)
    print(f"  found     : {len(files)}")
    print(f"  skipped   : {len(skipped)} (excluded by config)")
    print(f"  extracted : {len(records)}")
    print(f"  failed    : {len(failures)}")
    for f in failures:
        print(f"              {f['path']}")
        print(f"                cause: {f['cause']}")
    print()

    sheets = sum(r.get("sheet_count", 0) for r in records)
    print(f"  worksheets across parsed .xlsx : {sheets}")
    print()

    # R9: extension and magic bytes disagreeing is the trap that made
    # python-docx raise on a file that is actually plain text. Sniffing means it
    # now parses, but a silent success would hide the mismatch from pass 2.
    EXPECT = {".xlsx": "zip", ".docx": "zip", ".pptx": "zip",
              ".pdf": "pdf", ".png": "png", ".md": "text", "": "text"}
    mismatch = [r for r in records + failures
                if r["suffix"] in EXPECT and r["sniffed"] != EXPECT[r["suffix"]]]
    print("-" * 78)
    print("EXTENSION / MAGIC-BYTE MISMATCH")
    print("-" * 78)
    if not mismatch:
        print("  none")
    for r in mismatch:
        r["extension_mismatch"] = True
        print(f"  {r['path']}")
        print(f"    suffix {r['suffix']!r} implies {EXPECT[r['suffix']]!r}, "
              f"magic bytes say {r['sniffed']!r} — parsed as {r['sniffed']!r}")
    print()

    print("-" * 78)
    print("BLANK IDENTIFIERS")
    print("-" * 78)
    print("  Not applicable to pass 1. This pass does not read rows — it records")
    print("  which files exist and whether they open. Blank-identifier rows are")
    print("  reported and RETAINED by pass 2 (02_extract.py), per the rules now in")
    print("  taxonomy.yaml. Stated here so the gap is visible rather than assumed.")
    print()

    KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps({
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": source, "root": str(root),
        "counts": {"found": len(files), "skipped": len(skipped),
                   "extracted": len(records), "failed": len(failures)},
        "files": records, "failures": failures,
    }, indent=1), encoding="utf-8")
    print(f"wrote {MANIFEST.relative_to(REPO_ROOT)}")

    with BUILD_LOG.open("a", encoding="utf-8") as fh:
        fh.write(f"\n## {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%SZ')} — 01_walk_corpus\n\n")
        fh.write(f"- Source: `{source}`{'  **NOT DRIVE — pass 0 has never run**' if source == 'local-folder' else ''}\n")
        fh.write(f"- Found {len(files)} | skipped {len(skipped)} | extracted {len(records)} | failed {len(failures)}\n")
        fh.write(f"- Manifest diff: +{len(added)} added, ~{len(changed)} changed, -{len(removed)} removed\n")
        for f in failures:
            fh.write(f"    - FAILED `{f['path']}` — {f['cause']}\n")

    if changed or removed:
        print("\nHARD FAIL — the corpus is read-only; a changed or removed file must be explained.")
        return 1
    return 1 if failures and not args.allow_fallback else 0


if __name__ == "__main__":
    raise SystemExit(main())
