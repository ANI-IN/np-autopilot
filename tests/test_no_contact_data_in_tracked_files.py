"""The condition attached to the 2026-09-29 contact-data reversal.

`docs/CONTACT-DATA.md` §R approves ingesting instructor phone, email and
LinkedIn from ONE structured source, on the condition that they reach only the
sensitive half — `knowledge/graph-sensitive.json`, which is gitignored — and
never a tracked file.

WHY THIS FILE EXISTS ALONGSIDE `check_no_payroll_committed.py` RATHER THAN
INSTEAD OF IT. That script is the repo-wide, content-keyed backstop and it
already covers tracked files in general; it is deliberately not extended here,
because a second scanner would be a second source of truth about the same rule
and they would drift — §A.7a, one layer wearing two hats.

What this adds is the thing the backstop cannot see: whether the BUILD OUTPUT
put contact data somewhere tracked. The backstop answers "is there an address
in the repo"; this answers "did the graph put one there", which is the specific
risk the reversal creates and the only new one.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
LINKEDIN = re.compile(r"(?:https?://)?(?:[a-z]{2,3}\.)?linkedin\.com/[\w\-/%.]+",
                      re.IGNORECASE)
PHONE = re.compile(r"(?<![\w.])(?:\+\d{1,3}[\s.\-]?)?\d{3,5}[\s.\-]\d{3,5}"
                   r"(?:[\s.\-]\d{2,5})?(?![\w.])")

#: RFC 2606 / RFC 6761 reserved documentation names, same exemption the content
#: redactor uses. `user@example.com` in a doc is teaching content.
RESERVED = re.compile(r"@(?:example\.(?:com|net|org)|[\w.-]*\.(?:example|test|"
                      r"invalid|localhost))\b", re.IGNORECASE)

#: Build outputs that are TRACKED and therefore reach every clone.
TRACKED_GRAPH_ARTEFACTS = [
    "knowledge/graph.json",
    "knowledge/files.json",
    "knowledge/_graph_data.json",
    "knowledge/content_graph.json",
    # Pass 8's output. A NEW tracked graph artefact is exactly the thing this
    # list exists to catch, and adding it here is not optional: the merged
    # graph carries every instructor node both halves contribute.
    "knowledge/merged_graph.json",
]


def _real_addresses(text: str) -> list[str]:
    return [m for m in EMAIL.findall(text) if not RESERVED.search("@" + m.split("@")[-1])]


@pytest.mark.parametrize("rel", TRACKED_GRAPH_ARTEFACTS)
def test_no_tracked_graph_artefact_carries_contact_data(rel):
    """The reversal's central condition, checked on the files it could reach."""
    p = REPO / rel
    if not p.exists():
        pytest.skip(f"{rel} not built")
    tracked = subprocess.run(["git", "ls-files", "--error-unmatch", rel],
                             cwd=REPO, capture_output=True).returncode == 0
    if not tracked:
        pytest.skip(f"{rel} is not tracked; the condition is about tracked files")
    text = p.read_text(encoding="utf-8", errors="replace")
    assert not _real_addresses(text), f"{rel} contains an email address"
    assert not LINKEDIN.search(text), f"{rel} contains a LinkedIn URL"


def test_the_sensitive_half_is_gitignored():
    """The whole design rests on this one fact, so it is asserted rather than
    assumed — `graphio` documents it and `.gitignore` is what enforces it."""
    r = subprocess.run(["git", "check-ignore", "-q",
                        "knowledge/graph-sensitive.json"], cwd=REPO)
    assert r.returncode == 0, (
        "knowledge/graph-sensitive.json is NOT gitignored. Every contact field "
        "approved by CONTACT-DATA.md §R is written there on the understanding "
        "that it never enters git.")


def test_contact_properties_are_declared_sensitive_in_the_taxonomy():
    """`project_graph.py` refuses a `sensitive` property on a public row, which
    is what forces contact data onto a sensitive node. That enforcement only
    works if the properties are classified — so the classification is the
    thing to assert, not the refusal."""
    from pipeline.lib import taxonomy
    scopes = taxonomy.property_scopes()
    for prop in ("contact_phone", "contact_email", "linkedin_url"):
        assert scopes.get(prop) == "sensitive", (
            f"{prop} is classified {scopes.get(prop)!r}, not 'sensitive'. "
            "A public classification would let it into knowledge/graph.json.")


def test_a_public_instructor_node_never_carries_a_contact_property():
    """Belt and braces at the node level: even if a property were reclassified,
    the build must not attach one to a public row."""
    p = REPO / "knowledge" / "content_graph.json"
    if not p.exists():
        pytest.skip("content graph not built")
    g = json.loads(p.read_text(encoding="utf-8"))
    bad = [n["id"] for n in g["nodes"] if not n.get("sensitive")
           and any(k in n for k in ("contact_phone", "contact_email",
                                    "linkedin_url"))]
    assert not bad, f"{len(bad)} public nodes carry a contact property"
