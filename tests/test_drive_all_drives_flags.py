"""B1 — every Drive API call must carry the all-drives flags.

A Shared Drive folder listed without `supportsAllDrives` and
`includeItemsFromAllDrives` returns an empty file list with HTTP 200. No error,
no warning — just a successful-looking build over nothing. That is the worst
failure shape available in this pass, and it cannot be caught by the usual
"did it throw?" reflex.

So this is a static check over the source: it needs no credentials, no network
and no Drive folder, which means it runs in CI and on a machine that has never
seen the key. A runtime check would only fire on a machine that can already
reach Drive, which is exactly where the bug is least likely to be noticed.

`files.export` is deliberately exempt: the Drive v3 export endpoint takes only
fileId and mimeType, and passing supportsAllDrives to it is an error.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

FETCH = REPO / "pipeline" / "00_fetch_drive.py"

#: Drive v3 methods that accept the shared-drive flags, and which they need.
NEEDS = {
    "list": {"supportsAllDrives", "includeItemsFromAllDrives"},
    "get": {"supportsAllDrives"},
    "get_media": {"supportsAllDrives"},
}
#: files.export takes fileId and mimeType only. Passing the flags is an error.
EXEMPT = {"export_media", "export"}


def _files_calls(tree: ast.AST):
    """Yield (method_name, node) for every `service.files().<method>(...)` call."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        inner = node.func.value
        if not (isinstance(inner, ast.Call) and isinstance(inner.func, ast.Attribute)
                and inner.func.attr == "files"):
            continue
        yield node.func.attr, node


def _supplied_keys(node: ast.Call) -> set[str]:
    """Keyword names on the call, including those spread from a dict literal.

    list_folder builds its parameters in a dict and passes `**params`, so a
    keyword-only scan would see nothing and pass vacuously.
    """
    keys = {kw.arg for kw in node.keywords if kw.arg}
    for kw in node.keywords:
        if kw.arg is None and isinstance(kw.value, ast.Name):
            keys |= _dict_keys_assigned_to(node, kw.value.id)
    return keys


def _dict_keys_assigned_to(call: ast.Call, name: str) -> set[str]:
    """Keys of any dict(...) / {...} assigned or updated onto `name` in this file."""
    tree = ast.parse(FETCH.read_text(encoding="utf-8"))
    keys: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == name:
                    if isinstance(node.value, ast.Call) and getattr(
                            node.value.func, "id", None) == "dict":
                        keys |= {kw.arg for kw in node.value.keywords if kw.arg}
                    elif isinstance(node.value, ast.Dict):
                        keys |= {k.value for k in node.value.keys
                                 if isinstance(k, ast.Constant)}
        # params.update(corpora=..., driveId=...)
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "update"
                and getattr(node.func.value, "id", None) == name):
            keys |= {kw.arg for kw in node.keywords if kw.arg}
    return keys


def test_every_drive_call_carries_the_required_flags():
    tree = ast.parse(FETCH.read_text(encoding="utf-8"))
    checked, problems = 0, []
    for method, node in _files_calls(tree):
        if method in EXEMPT:
            continue
        required = NEEDS.get(method)
        assert required is not None, (
            f"unrecognised Drive method files().{method}() at line {node.lineno}. "
            "Add it to NEEDS with the flags it requires, or to EXEMPT with why."
        )
        checked += 1
        missing = required - _supplied_keys(node)
        if missing:
            problems.append(f"line {node.lineno}: files().{method}() missing {sorted(missing)}")
    assert not problems, (
        "a Shared Drive returns an empty list with HTTP 200 when these are "
        "absent:\n  " + "\n  ".join(problems)
    )
    assert checked >= 3, f"expected to check at least 3 Drive calls, saw {checked}"


def test_flags_are_passed_as_true_not_merely_present():
    tree = ast.parse(FETCH.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.keyword) or node.arg not in {
                "supportsAllDrives", "includeItemsFromAllDrives"}:
            continue
        assert isinstance(node.value, ast.Constant) and node.value.value is True, (
            f"{node.arg} at line {node.value.lineno} is not the literal True"
        )


def test_export_is_exempt_and_stays_that_way():
    """Guards against someone 'fixing' the exemption and breaking every export."""
    tree = ast.parse(FETCH.read_text(encoding="utf-8"))
    for method, node in _files_calls(tree):
        if method in EXEMPT:
            supplied = _supplied_keys(node)
            assert "supportsAllDrives" not in supplied, (
                f"files().{method}() at line {node.lineno} passes supportsAllDrives; "
                "the Drive v3 export endpoint rejects it"
            )


def test_shared_drive_is_determined_before_listing():
    """The kind must be known before the first walk, not inferred from failure."""
    src = FETCH.read_text(encoding="utf-8")
    assert "def drive_kind(" in src
    main_body = src.split("def main(", 1)[1]
    assert main_body.index("drive_kind(") < main_body.index("walk(service"), (
        "main() walks the tree before establishing whether this is a Shared Drive"
    )


def test_no_domain_wide_delegation():
    """Access comes from the folder share, which is revocable in one click."""
    src = FETCH.read_text(encoding="utf-8")
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Attribute) and node.attr == "with_subject":
            raise AssertionError(
                f"with_subject() at line {node.lineno} — domain-wide delegation "
                "lets this key impersonate any user in the workspace"
            )


def test_scope_is_readonly_and_singular():
    tree = ast.parse(FETCH.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "SCOPES" for t in node.targets):
            scopes = [e.value for e in node.value.elts]
            assert scopes == ["https://www.googleapis.com/auth/drive.readonly"], scopes
            return
    raise AssertionError("SCOPES not found")


def test_key_is_never_read_from_inside_the_repo():
    """An ignore rule stops a commit, not a copy into a build context."""
    src = FETCH.read_text(encoding="utf-8")
    assert "refusing to read a service-account key from inside the repo" in src
    assert "relative_to(ROOT)" in src.split("def key_path(", 1)[1].split("def ", 1)[0]
