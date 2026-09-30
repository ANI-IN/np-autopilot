"""The function map may cite ONLY files the upload will include.

    python3 db/window/check_function_map.py /tmp/np-deploy-<sha>

`vercel deploy --prebuilt` uploads the project honouring .vercelignore; a
function whose file map cites an excluded path fails on Vercel's side, after
the upload, with ENOENT (2026-09-30, window step 4 — R23). Checked locally,
before any deploy:

  - every map entry exists in the artifact;
  - no map entry is excluded by the artifact's .vercelignore (git's matcher);
  - the pulled production env file is neither on disk nor in the map;
  - NO FILE THE UPLOAD CARRIES holds the local review stub or an identity
    bypass (owner requirement 2026-09-30): the stub lives only in
    eval/local_server.py, which .vercelignore excludes, and this proves it
    stayed there.

Exit 0 only when all four hold.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

VC_CONFIG = Path(".vercel/output/functions/python.func/.vc-config.json")
ENV_FILE = ".vercel/.env.production.local"
#: What only the LOCAL review stub (eval/local_server.py) contains: its marker,
#: its placeholder config, and replacing the identity check. None of these may
#: reach an uploaded file.
STUB_PATTERNS = (
    re.compile(r"NP-LOCAL-PREVIEW-STUB"),
    re.compile(r"local-harness"),
    re.compile(r"\bguard\.identify\s*=(?!=)"),
    re.compile(r"LOCAL PREVIEW, not production"),
)
#: the build's own Python runtime is third-party code, not ours
_SKIP_DIRS = (".vercel/python/", ".git/")


def uploaded_files(artifact: Path) -> list[str]:
    """Every file `vercel deploy --prebuilt` would upload: all of them, minus
    what .vercelignore excludes (git's matcher, as Vercel applies it)."""
    ignore = artifact / ".vercelignore"
    files = sorted(str(p.relative_to(artifact)) for p in artifact.rglob("*")
                   if p.is_file() and not any(str(p.relative_to(artifact)).startswith(d)
                                              for d in _SKIP_DIRS))
    if not ignore.exists():
        return files
    gone = set(excluded_by(ignore, files))
    return [f for f in files if f not in gone]


def stub_hits(artifact: Path, files: list[str] | None = None) -> list[str]:
    """Uploaded files that carry the local stub or an identity bypass."""
    hits = []
    for rel in (files if files is not None else uploaded_files(artifact)):
        p = artifact / rel
        try:
            if p.stat().st_size > 8_000_000:
                continue
            text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue                                   # binary: not code we wrote
        for rx in STUB_PATTERNS:
            if rx.search(text):
                hits.append(f"{rel} ({rx.pattern})")
                break
    return hits


def excluded_by(ignore_file: Path, paths: list[str]) -> list[str]:
    """The subset of `paths` that .vercelignore excludes, by git's own rules."""
    if not paths:
        return []
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["git", "init", "-q", tmp], check=True)
        # `check-ignore` takes excludes from the repo, so install the file there.
        (Path(tmp) / ".git" / "info" / "exclude").write_text(
            ignore_file.read_text(encoding="utf-8"), encoding="utf-8")
        r = subprocess.run(["git", "-C", tmp, "check-ignore", "--no-index", "--stdin"],
                           input="\n".join(paths) + "\n", text=True, capture_output=True)
        if r.returncode not in (0, 1):
            raise SystemExit(f"git check-ignore failed: {r.stderr.strip()}")
        return [ln for ln in r.stdout.splitlines() if ln]


def check(artifact: Path) -> list[str]:
    problems = []
    cfg = artifact / VC_CONFIG
    if not cfg.exists():
        return [f"no function config at {VC_CONFIG} — was the artifact built?"]
    fmap = json.loads(cfg.read_text(encoding="utf-8"))["filePathMap"]
    missing = [k for k, v in fmap.items() if not (artifact / v).exists()]
    if missing:
        problems.append(f"{len(missing)} map entries do not exist in the artifact, "
                        f"e.g. {missing[:5]}")
    ignore = artifact / ".vercelignore"
    if not ignore.exists():
        problems.append("no .vercelignore in the artifact — cannot check the upload set")
    else:
        # The VALUE is the source file the upload must carry (Vercel resolved
        # `/vercel/path0/<value>` and failed). The key is only where it lands
        # inside the function, so checking keys proves nothing about upload.
        bad = excluded_by(ignore, sorted(set(fmap.values())))
        if bad:
            problems.append(f"{len(bad)} source files the function needs are EXCLUDED "
                            f"from the upload by .vercelignore, e.g. {bad[:5]}")
    if (artifact / ENV_FILE).exists() or ENV_FILE in fmap:
        problems.append(f"{ENV_FILE} is present — it holds production secrets")
    hits = stub_hits(artifact)
    if hits:
        problems.append(f"{len(hits)} uploaded files carry the LOCAL review stub or an "
                        f"identity bypass, e.g. {hits[:5]}")
    return problems


def main(argv) -> int:
    artifact = Path(argv[1]).resolve()
    problems = check(artifact)
    fmap = {}
    cfg = artifact / VC_CONFIG
    if cfg.exists():
        fmap = json.loads(cfg.read_text(encoding="utf-8"))["filePathMap"]
    if problems:
        print(f"FUNCTION MAP CHECK FAILED for {artifact}:")
        for p in problems:
            print(f"  - {p}")
        return 1
    print(f"function map OK: {len(fmap)} entries, all present, none excluded by "
          f".vercelignore, no env file; no local stub in "
          f"{len(uploaded_files(artifact))} uploaded files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
