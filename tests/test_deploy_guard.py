"""D8 — the local demo login (eval/kb_demo_server.py, /local-login) can never ship.

Production serves `public/` as static files and `api/**` as the Python function
(vercel.json). The demo sign-in lives only in eval/. These tests fail if any
path by which eval/ could reach a deployment opens up:

  - .vercelignore stops excluding eval/ or tests/ from the upload;
  - the function's excludeFiles stops excluding them from the bundle;
  - anything under public/ (the static output directory) carries the demo
    page, its script, or a link to /local-login;
  - any shipped Python (api/, web/, pipeline/lib/) imports from eval/ or
    mentions the demo route;
  - vercel.json grows a rewrite/route that points at eval/ or /local-login;
  - a prebuilt output (.vercel/output, if present) contains any of it.

No network, no database: runs in CI.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEMO_MARKERS = ("local-login", "kb_demo_server", "kb_demo_seed", "kb_local_stack", "ik-demo-local")


def _ignore_lines() -> list[str]:
    return [ln.strip() for ln in (REPO / ".vercelignore").read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.lstrip().startswith("#")]


def test_vercelignore_excludes_eval_and_tests_and_never_reincludes_them():
    lines = _ignore_lines()
    for d in ("eval/", "tests/"):
        assert d in lines, f".vercelignore must exclude {d}"
        assert not any(ln.startswith("!") and ln[1:].lstrip("/").startswith(d.rstrip("/")) for ln in lines), \
            f".vercelignore re-includes something under {d}"


def test_function_bundle_excludes_eval_and_tests():
    cfg = json.loads((REPO / "vercel.json").read_text(encoding="utf-8"))
    excl = cfg["functions"]["api/**"]["excludeFiles"]
    names = set(re.findall(r"[{,]([^,{}]+)", excl))
    assert {"eval", "tests"} <= names, excl
    assert cfg.get("outputDirectory") == "public", "static output must stay public/ (eval/ is outside it)"


def test_no_route_or_rewrite_reaches_the_demo():
    raw = (REPO / "vercel.json").read_text(encoding="utf-8")
    for key in ("rewrites", "routes", "redirects"):
        for rule in json.loads(raw).get(key, []):
            text = json.dumps(rule)
            assert "eval" not in text and "local-login" not in text, rule


def test_static_output_has_no_demo_page_or_link():
    hits = []
    for p in (REPO / "public").rglob("*"):
        if p.is_file() and p.suffix in (".html", ".js", ".css", ".json", ".md"):
            text = p.read_text(encoding="utf-8", errors="replace")
            hits += [f"{p.relative_to(REPO)}: {m}" for m in DEMO_MARKERS if m in text]
    assert not hits, hits


def test_shipped_python_never_imports_or_names_the_demo():
    hits = []
    for root in ("api", "web", "pipeline/lib"):
        for p in (REPO / root).rglob("*.py"):
            text = p.read_text(encoding="utf-8", errors="replace")
            if re.search(r"^\s*(from|import)\s+eval\b|['\"]eval/", text, re.M):
                hits.append(f"{p.relative_to(REPO)}: imports eval/")
            hits += [f"{p.relative_to(REPO)}: {m}" for m in DEMO_MARKERS if m in text]
    assert not hits, hits


def test_prebuilt_output_if_present_has_no_demo():
    out = REPO / ".vercel" / "output"
    if not out.exists():
        return                                  # nothing prebuilt in this checkout
    bad = [str(p.relative_to(REPO)) for p in out.rglob("*")
           if p.is_file() and ("eval" in p.parts or any(m in p.name for m in DEMO_MARKERS))]
    assert not bad, bad


def test_the_in_app_guide_ships():
    """public/kb/guide.md is fetched by the KB page; `*.md` is otherwise excluded."""
    lines = _ignore_lines()
    assert "*.md" in lines and "!public/kb/guide.md" in lines
    assert lines.index("!public/kb/guide.md") > lines.index("*.md")      # later rules win
    assert (REPO / "public" / "kb" / "guide.md").is_file()
