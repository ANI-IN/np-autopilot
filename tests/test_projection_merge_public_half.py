"""The projection reads BOTH graphs, and the public scope carries no contact.

`docs/CONTACT-DATA.md` §R approved instructor phone, email and LinkedIn into
the graph on one condition: they reach only the sensitive half, which is
gitignored. Until now the projection read `graph.json` alone, so the content
graph's sensitive half could not reach it by construction. Merging the two
removes that accident, and this file is what replaces it with a control.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from pipeline.lib import graphio, taxonomy                            # noqa: E402

EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
LINKEDIN = re.compile(r"linkedin\.com/", re.I)
RESERVED = re.compile(r"@(?:example\.(?:com|net|org)|[\w.-]*\.(?:example|test|"
                      r"invalid|localhost))\b", re.I)

pytestmark = pytest.mark.skipif(
    not (graphio.PUBLIC.exists() and graphio.CONTENT_PUBLIC.exists()),
    reason="both graphs must be built")


@pytest.fixture(scope="module")
def public():
    return graphio.load_merged(include_sensitive=False)


def _contact_type():
    """Derived, never written out — B2."""
    return taxonomy.edge_endpoints(taxonomy.edge_for_role("contact_of"))[1]


def test_the_public_merge_contains_no_contact_node(public):
    bad = [n["id"] for n in public["nodes"] if n["type"] == _contact_type()]
    assert not bad, f"{len(bad)} contact nodes reached the public projection"


def test_the_public_merge_contains_no_node_flagged_sensitive(public):
    bad = [n["id"] for n in public["nodes"]
           if str(n.get("sensitive")).lower() == "true"]
    assert not bad, f"{len(bad)} sensitive nodes reached the public projection"


def test_no_contact_property_rides_on_a_public_node(public):
    scopes = taxonomy.property_scopes()
    sensitive_props = {k for k, v in scopes.items() if v == "sensitive"}
    assert sensitive_props, "no property is classified sensitive; the check is void"
    bad = [n["id"] for n in public["nodes"]
           if sensitive_props & set(n)]
    assert not bad, f"{len(bad)} public nodes carry a sensitive property"


def test_no_address_shaped_string_survives_anywhere_in_the_public_merge(public):
    blob = json.dumps(public)
    emails = [m for m in EMAIL.findall(blob)
              if not RESERVED.search("@" + m.split("@")[-1])]
    assert not emails, f"{len(emails)} email-shaped strings in the public merge"
    assert not LINKEDIN.findall(blob), "a LinkedIn URL is in the public merge"


def test_the_sensitive_half_IS_loaded_when_asked_so_the_check_means_something():
    """Negative control. If include_sensitive=True also produced nothing, the
    assertions above would pass against an empty file and prove nothing."""
    if not graphio.CONTENT_SENSITIVE.exists():
        pytest.skip("no content sensitive half on this machine")
    full = graphio.load_merged(include_sensitive=True)
    contact = [n for n in full["nodes"] if n["type"] == _contact_type()]
    assert contact, (
        "include_sensitive=True loaded no contact node, so the public-half "
        "assertions are vacuous")
    assert full["meta"]["content_sensitive_loaded"] is True


def test_the_default_is_the_safe_one():
    """`load_graph` defaults to include_sensitive=True; this one must not."""
    import inspect
    sig = inspect.signature(graphio.load_merged)
    assert sig.parameters["include_sensitive"].default is False


def test_the_projection_reads_the_merged_graph_not_one_half():
    src = (REPO / "pipeline" / "project_graph.py").read_text(encoding="utf-8")
    assert "load_merged(" in src, (
        "project_graph.py no longer calls load_merged; the content half would "
        "silently stop being projected")
