"""Nothing the API sends may be lost in the client's adaptation layer.

`adaptEdge` dropped every edge property since the client was written — basis
(1,155 values), inferred (351), class_dates (1,499), rank (2,239) — and nothing
failed. The panel rendered, the edges drew, and the data never reached the
browser. It also extracted `props.b`, which no edge has ever carried: `b` is the
OFFLINE build's compact key for basis, and the adapter was ported against that
shape rather than the API's.

That is the failure this file exists to make impossible: a silent loss at a
boundary where both sides are individually correct.

DERIVED, NOT LISTED. The expected keys come from calling the real data layer
against the real database, so a field added upstream appears here automatically.
A hand-written list of "fields the client should have" would be another
allow-default list — a new field simply would not be on it.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "web"))

from pipeline.lib import db                                           # noqa: E402

pytestmark = pytest.mark.skipif(
    not db.available(),
    reason="no SUPABASE_DB_URL_SESSION / psycopg — database tests skipped")

from lib import data                                                  # noqa: E402

HTML = REPO / "public" / "index.html"

#: A key the adapter deliberately does not carry needs a marker beside it:
#:     // adapt-drop: depth — server-side traversal bookkeeping
#: Deliberately awkward. A drop should cost a sentence.
DROP = re.compile(r"//\s*adapt-drop:\s*(\w+)\s*[—-]\s*(\S.*)")


def _fn_body(name: str) -> str:
    src = HTML.read_text(encoding="utf-8")
    start = src.index(f"function {name}(")
    depth, i, started = 0, start, False
    while i < len(src):
        if src[i] == "{":
            depth += 1; started = True
        elif src[i] == "}":
            depth -= 1
            if started and depth == 0:
                return src[start:i + 1]
        i += 1
    raise AssertionError(f"could not find the body of {name}")


def _declared_drops(body: str) -> dict[str, str]:
    return {m.group(1): m.group(2) for m in DROP.finditer(body)}


def _api_keys():
    """The REAL response shapes, from the real data layer."""
    with data.request_connection(None) as conn, conn.cursor() as cur:
        cur.execute("set local role postgres")          # read past RLS for shape only
        cur.execute("select id from nodes where type = 'domain' limit 1")
        nid = cur.fetchone()[0]
        nb = data.neighbourhood(conn, nid, depth=2)
        node = data.node(conn, nid)
    edge_keys = set().union(*(set(e) for e in nb["edges"])) if nb["edges"] else set()
    nb_node_keys = set().union(*(set(n) for n in nb["nodes"])) if nb["nodes"] else set()
    return nb_node_keys | set(node), edge_keys


def test_the_edge_adapter_carries_every_key_the_api_sends():
    body = _fn_body("adaptEdge")
    _, edge_keys = _api_keys()
    assert edge_keys, "the API returned no edges — this test would be vacuous"

    drops = _declared_drops(body)
    missing = [k for k in sorted(edge_keys)
               if k not in body and k not in drops]
    assert not missing, (
        f"adaptEdge never mentions {missing}, and they are not declared dropped. "
        "Add them, or add `// adapt-drop: <key> — <why>` beside the adapter.")


def test_the_node_adapter_carries_every_key_the_api_sends():
    body = _fn_body("adaptNode")
    node_keys, _ = _api_keys()
    drops = _declared_drops(body)
    missing = [k for k in sorted(node_keys)
               if k not in body and k not in drops]
    assert not missing, (
        f"adaptNode never mentions {missing}, and they are not declared dropped.")


def test_props_are_carried_whole_not_cherry_picked():
    """THE SHAPE OF THE BUG, not an instance of it.

    Naming each property individually is what lost twelve of them: a property
    added upstream is silently absent downstream and nothing errors, because the
    adapter did exactly what it was told. Carrying the container means a new
    property arrives without anyone editing the client.
    """
    for name in ("adaptNode", "adaptEdge"):
        body = _fn_body(name)
        assert re.search(r"\bp\s*:\s*(r\.props\s*\|\|\s*\{\}|p\b)", body), (
            f"{name} does not carry `props` whole. Picking named fields out of "
            "it is exactly how basis, inferred, class_dates and rank were lost.")


def test_the_dead_offline_key_is_gone():
    """`props.b` never existed in an API response.

    It is the offline build's compact key for basis. Measured: 0 edges carry a
    `b` prop, 3,929 carry props. An adapter reading a field from the wrong
    serialisation returns undefined forever and never complains.
    """
    body = _fn_body("adaptEdge")
    assert not re.search(r"\)\s*\.\s*b\b|\bprops\s*\|\|\s*\{\}\s*\)\s*\.\s*b\b", body), \
        "adaptEdge still reads props.b, which no API response has ever carried"

    with data.request_connection(None) as conn, conn.cursor() as cur:
        cur.execute("set local role postgres")
        cur.execute("select count(*) from edges where props ? 'b'")
        assert cur.fetchone()[0] == 0, (
            "an edge now carries a `b` prop — if that is deliberate the adapter "
            "should read it by its real name, not by the offline shorthand")
