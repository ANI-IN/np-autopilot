#!/usr/bin/env python3
"""B10 — refresh v1. Run the pipeline, validate, report the delta, then STOP.

Never commits. Prints a delta and waits for a human. The version bump is
automatic AND enforced: refresh bumps plugin.json, and validate.py hard-fails if
graph.json content changed while the version did not. Automatic-and-trusted is
how the reference implementation shipped a graph nobody could receive.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.lib.paths import KNOWLEDGE_DIR, REPO_ROOT                # noqa: E402

PLUGIN = REPO_ROOT / ".claude-plugin" / "plugin.json"
GRAPH = KNOWLEDGE_DIR / "graph.json"
LOCK = KNOWLEDGE_DIR / ".version-lock.json"

PASSES = [
    ("01_walk_corpus.py", ["--allow-fallback"]),
    ("02_extract.py", []),
    ("03_resolve.py", []),
    ("04_build_graph.py", []),
    ("gen_index.py", []),
    ("05_render_html.py", []),
]


def content_hash(path: Path = GRAPH) -> str:
    """Hash of nodes+edges ONLY. Excludes meta, which carries a timestamp — so
    an unchanged corpus produces an identical hash on every run."""
    g = json.loads(path.read_text(encoding="utf-8"))
    payload = json.dumps({"nodes": g["nodes"], "edges": g["edges"]},
                         sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def read_version() -> str:
    return json.loads(PLUGIN.read_text(encoding="utf-8"))["version"]


def read_lock() -> dict | None:
    if not LOCK.exists():
        return None
    try:
        return json.loads(LOCK.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def needs_bump(lock: dict | None, after_hash: str) -> bool:
    """Compare the rebuilt graph against the LAST RELEASED hash, not the tree.

    This used to compare against the working-tree graph.json captured at the top
    of the run. pipeline/README documents re-running a single pass as normal, so
    anyone who did that and then ran refresh had already written the change into
    the tree — refresh saw new-vs-new, reported IDENTICAL, skipped the bump, and
    then rewrote the lock with the new hash, which disarmed validate's
    enforcement too. A content change shipped under an unchanged version, which
    is the exact failure the version lock exists to prevent.

    The lock is the only record of what was last released, so it is the only
    honest baseline.
    """
    if lock is None or not lock.get("content_hash"):
        return True
    return after_hash != lock["content_hash"]


def bump(version: str) -> str:
    major, minor, patch = (int(x) for x in version.split("."))
    return f"{major}.{minor}.{patch + 1}"


def snapshot():
    if not GRAPH.exists():
        return None
    g = json.loads(GRAPH.read_text(encoding="utf-8"))
    return {"hash": content_hash(), "nodes": g["meta"]["nodes"],
            "edges": g["meta"]["edges"],
            "node_counts": dict(g["meta"].get("node_counts", {})),
            "edge_counts": dict(g["meta"].get("edge_counts", {}))}


def run_pass(script, args):
    r = subprocess.run([sys.executable, f"pipeline/{script}", *args],
                       cwd=REPO_ROOT, capture_output=True, text=True)
    return r.returncode, r.stdout, r.stderr


def diff_line(before, after, lock=None):
    """Count delta against the WORKING TREE. The bump decision uses the lock.

    The two baselines can disagree — that is the hand-run case — so each line
    names which one it is talking about. "IDENTICAL" printed next to a version
    bump is otherwise a straight contradiction on the face of the report.
    """
    if before is None:
        return ["  no previous graph — this is the baseline"]
    out = []
    if before["hash"] == after["hash"]:
        released = (lock or {}).get("content_hash")
        out.append("  IDENTICAL to the working tree at the start of this run")
        if released and released != after["hash"]:
            out.append(f"  CHANGED vs the last RELEASED graph "
                       f"({released[:16]} -> {after['hash'][:16]}) — this is what "
                       "the bump responds to")
        return out
    out.append(f"  nodes {before['nodes']} -> {after['nodes']}"
               f"  ({after['nodes']-before['nodes']:+d})")
    out.append(f"  edges {before['edges']} -> {after['edges']}"
               f"  ({after['edges']-before['edges']:+d})")
    for k in sorted(set(before["node_counts"]) | set(after["node_counts"])):
        b, a = before["node_counts"].get(k, 0), after["node_counts"].get(k, 0)
        if a != b:
            out.append(f"    node {k:<12} {b:>6} -> {a:<6} ({a-b:+d})")
    for k in sorted(set(before["edge_counts"]) | set(after["edge_counts"])):
        b, a = before["edge_counts"].get(k, 0), after["edge_counts"].get(k, 0)
        if a != b:
            out.append(f"    edge {k:<20} {b:>6} -> {a:<6} ({a-b:+d})")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-bump", action="store_true",
                    help="skip the version bump (for a dry second run)")
    args = ap.parse_args()

    print("=" * 78)
    print("REFRESH v1")
    print("=" * 78)
    before = snapshot()
    ver_before = read_version()
    print(f"  plugin version : {ver_before}")
    print(f"  graph hash     : {(before or {}).get('hash', '(none)')[:16]}  (working tree)")
    print(f"  released hash  : {(read_lock() or {}).get('content_hash', '(none)')[:16]}  (version lock)")
    print()

    for script, extra in PASSES:
        code, out, err = run_pass(script, extra)
        status = "ok" if code == 0 else f"FAILED ({code})"
        print(f"  {script:<22} {status}")
        if code != 0:
            print(err[-1500:] or out[-1500:])
            return 1

    after = snapshot()
    lock = read_lock()
    changed = needs_bump(lock, after["hash"])
    # The tree-vs-lock disagreement is the manual-pass case. Say so out loud
    # rather than letting it look like a no-op run.
    if before is not None and lock and before["hash"] != lock.get("content_hash"):
        print("  NOTE — the working tree already differed from the version lock "
              "before this run\n"
              "         (a pass was run by hand). The bump decision uses the "
              "LOCK, not the tree.")

    print()
    print("-" * 78)
    print("DELTA")
    print("-" * 78)
    for line in diff_line(before, after, lock):
        print(line)
    print()

    new_version = ver_before
    if changed and not args.no_bump:
        new_version = bump(ver_before)
        p = json.loads(PLUGIN.read_text(encoding="utf-8"))
        p["version"] = new_version
        PLUGIN.write_text(json.dumps(p, indent=2) + "\n", encoding="utf-8")
        print(f"  version bumped {ver_before} -> {new_version}")
    elif changed:
        print("  version NOT bumped (--no-bump) — validate will hard-fail")
    else:
        print(f"  version unchanged at {ver_before} (graph did not change)")

    # Writing the lock is what RELEASES a content hash: validate.py compares the
    # graph against it, so recording a hash the version does not cover disarms
    # the check. --no-bump exists for a dry second run and used to write the lock
    # anyway, immediately after printing "validate will hard-fail" — which it
    # then would not. Skip the write in exactly that case.
    if changed and args.no_bump:
        print("  version lock NOT updated — --no-bump leaves the released hash "
              "alone, so validate.py still sees the mismatch it warned about")
    else:
        LOCK.write_text(json.dumps(
            {"content_hash": after["hash"], "plugin_version": new_version,
             "written_at": datetime.now(timezone.utc).isoformat(timespec="seconds")},
            indent=1), encoding="utf-8")

    code, out, err = run_pass("validate.py", [])
    tail = [l for l in out.splitlines() if l.startswith("RESULT") or "validate:" in l]
    print()
    print("-" * 78)
    print("VALIDATE")
    print("-" * 78)
    for l in tail:
        print("  " + l.strip())
    if code != 0:
        print("\nREFRESH ABORTED — validation failed. Nothing to commit.")
        return 1

    print()
    print("=" * 78)
    print("STOPPED FOR CONFIRMATION — nothing has been committed.")
    print("=" * 78)
    print("  Review the delta above, then commit yourself:")
    print("    git add -A && git commit")
    print(f"  Version is now {new_version} in .claude-plugin/plugin.json.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
