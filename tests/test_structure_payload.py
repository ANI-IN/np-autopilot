"""B3 — the columnar /api/structure payload, lazy panels, ETag and compression.

Encoder and decoder are held together by ONE fixture: eval/fixtures/
structure-columnar.json is pack_structure() applied to the synthetic rows
below, asserted current here, and decoded by the page's own decodeStructure()
in eval/drive_dom.mjs. Change either side and one of the two goes red.

    python3 tests/test_structure_payload.py --write     # regenerate the fixture
"""
from __future__ import annotations

import base64
import json
import math
import re
import struct
import sys
import uuid
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(REPO), str(REPO / "web"), str(REPO / "api")]

from pipeline.lib import db, taxonomy                                 # noqa: E402
from lib import data                                                  # noqa: E402

FIXTURE = REPO / "eval" / "fixtures" / "structure-columnar.json"
HTML = (REPO / "public" / "index.html").read_text(encoding="utf-8")

REL_SESSION = taxonomy.edge_for_role("module_session")
REL_WEEK = taxonomy.edge_for_role("module_week")
T_MODULE, T_SESSION = taxonomy.edge_endpoints(REL_SESSION)
T_WEEK = taxonomy.edge_endpoints(REL_WEEK)[1]


def synthetic():
    """No real person, file or link. Two edges share (source, rel, target) on
    purpose — one per attached file — because that is the shape the client
    used to collapse."""
    nodes = [
        ("mod_synthetic", T_MODULE, "Synthetic Module", None,
         {"domain_slug": "synthetic", "sequence": 1,
          "uplevel_link": "https://example.invalid/uplevel"}, -30.0, 40.0),
        ("ses_synthetic", T_SESSION, "Class", "Class ",
         {"session_kind": "class", "status": "current"}, 5.5, -7.25),
        ("wk_synthetic", T_WEEK, "Week 9", None, {"number": 9}, None, None),
    ]
    edges = [
        (101, REL_SESSION, "mod_synthetic", "ses_synthetic",
         {"attached_file": "synthetic-a.pptx",
          "attached_drive_url": "https://example.invalid/a", "session_kind": "class",
          "tier": "mastersheet"}),
        (102, REL_SESSION, "mod_synthetic", "ses_synthetic",
         {"attached_file": "synthetic-b.pptx",
          "attached_drive_url": "https://example.invalid/b", "session_kind": "class",
          "tier": "mastersheet"}),
        (103, REL_WEEK, "mod_synthetic", "wk_synthetic",
         {"provenance": {"sheet": "synthetic"}}),
    ]
    return nodes, edges


def _packed():
    return json.loads(json.dumps(data.pack_structure(*synthetic())))


# --- the encoder --------------------------------------------------------------

def test_the_committed_fixture_is_what_the_encoder_produces():
    assert FIXTURE.exists(), "run: python3 tests/test_structure_payload.py --write"
    got = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert got == _packed(), ("pack_structure() changed; regenerate the fixture "
                              "(and bump STRUCTURE_FORMAT if the shape changed)")


def test_edges_sharing_endpoints_are_all_kept_with_their_ids():
    p = _packed()
    ev = struct.unpack(f"<{3 * p['m']}H", base64.b64decode(p["e"]))
    eid = struct.unpack(f"<{p['m']}I", base64.b64decode(p["eid"]))
    assert p["m"] == 3 and eid == (101, 102, 103)
    assert ev[0:3] == ev[3:6], "the two same-triple edges must both be present"


def test_coordinates_round_trip_and_a_missing_layout_is_nan():
    p = _packed()
    xy = struct.unpack(f"<{2 * p['n']}f", base64.b64decode(p["xy"]))
    assert xy[0:4] == (-30.0, 40.0, 5.5, -7.25)
    assert math.isnan(xy[4]) and math.isnan(xy[5])


def test_panel_only_props_are_left_out_and_the_rest_are_carried_whole():
    p = _packed()
    assert "uplevel_link" not in p["np"]["0"] and p["np"]["0"]["sequence"] == 1
    assert p["np"]["1"] == {"status": "current"}          # session_kind held back
    assert p["ep"]["0"] == {"tier": "mastersheet"}        # attached_* held back
    assert "2" not in p["ep"], "provenance is panel data"
    assert p["raw"] == {"1": "Class "}, "label_raw only where it differs"


def test_too_many_nodes_for_the_format_fails_loudly():
    nodes = [(f"n{i:06d}", T_MODULE, "x", None, {}, 0.0, 0.0) for i in range(0x10000)]
    with pytest.raises(RuntimeError, match="Uint16"):
        data.pack_structure(nodes, [])


# --- the classification: panel-only means READ ONLY BY THE PANEL ---------------

PANEL_FUNCTIONS = {"TYPE_FACTS", "moduleChain", "relDetail", "topicLinks",
                   "crossVal", "reviewFlag", "mergedNote", "raws",
                   "renderProvenance"}
READ = re.compile(r"(?:\b(?:p|props)\.|\.p\.|\.p\|\|\{\}\)\.)([a-z_][a-z0-9_]*)")


def _reads_by_function():
    out, fn = {}, None
    in_script = False
    for line in HTML.splitlines():
        if "<script" in line:
            in_script = True
        if not in_script:
            continue
        m = re.match(r"\s*(?:async\s+)?function\s+([A-Za-z_$][\w$]*)|"
                     r"\s*(?:const|let)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:\{|\(|function)", line)
        if m:
            fn = m.group(1) or m.group(2)
        code = line.split("//", 1)[0]
        for k in READ.findall(code):
            out.setdefault(k, set()).add(fn)
    return out


@pytest.mark.parametrize("key", sorted(data.PANEL_ONLY_NODE_PROPS | data.PANEL_ONLY_EDGE_PROPS))
def test_a_panel_only_prop_is_read_only_by_the_panel(key):
    """If a view (matrix, timeline, filters, the canvas) starts reading one of
    these, it would find it missing from the bulk payload and say nothing —
    so this fails first. Move the key out of PANEL_ONLY_*, or fetch detail."""
    outside = sorted(f or "?" for f in _reads_by_function().get(key, set())
                     if f not in PANEL_FUNCTIONS)
    assert not outside, f"{key!r} is read outside the panel, in {outside}"


def test_the_scan_sees_the_views_it_guards():
    """Non-vacuity: the scan must find the bulk reads that views really make."""
    reads = _reads_by_function()
    assert "renderMatrix" in reads.get("tier", set())
    assert "modulesFor" in reads.get("sequence", set())
    assert "moduleChain" in reads.get("attached_file", set())


DROP = re.compile(r"//\s*adapt-drop:\s*(\w+)\s*[—-]\s*(\S.*)")


def test_the_decoder_reads_every_key_the_encoder_sends():
    start = HTML.index("function decodeStructure(")
    end = HTML.index("// ---- B3: LAZY PANELS")
    body = HTML[start:end] + HTML[HTML.index("async function loadStructure("):
                                  HTML.index("async function loadOverview(")]
    drops = {m.group(1) for m in DROP.finditer(body)}
    missing = [k for k in _packed() if f"o.{k}" not in body
               and f"out.{k}" not in body and k not in drops]
    assert not missing, (f"decodeStructure/loadStructure never read {missing}; "
                         "read them or declare `// adapt-drop: <key> — <why>`")


# --- the router: conditional GET, private caching, compression ----------------

def test_etag_matching():
    import index
    assert index._etag_matches('"a"', '"a"')
    assert index._etag_matches('"x", W/"a"', '"a"')
    assert index._etag_matches("*", '"a"')
    assert not index._etag_matches('"b"', '"a"')
    assert not index._etag_matches(None, '"a"')


def test_compression_honours_accept_encoding():
    import brotli
    import gzip
    import index
    raw = json.dumps(_packed()).encode()
    body, enc = index._compress(raw, "gzip, deflate, br")
    assert enc == "br" and brotli.decompress(body) == raw
    body, enc = index._compress(raw, "gzip")
    assert enc == "gzip" and gzip.decompress(body) == raw
    assert index._compress(raw, "identity") == (raw, None)
    assert index._compress(raw, "") == (raw, None)


def test_only_structure_opts_into_caching():
    """Every other read stays `private, no-store` — the default did not move.
    Compression is separate from caching: /api/node compresses, never caches."""
    import index
    for name in index.READ_NAMES:
        index.endpoint_for(f"/api/{name}")
        opts = index.endpoint_options(name)
        if name == "structure":
            assert opts["cache"] == "private, max-age=300, must-revalidate"
            assert opts["etag"] and opts["compress"]
        else:
            assert not opts.get("cache") and not opts.get("etag"), \
                f"/api/{name} opted into caching: {opts}"
            assert set(opts) <= {"compress"}, opts


# --- against the local database ------------------------------------------------

needs_db = pytest.mark.skipif(not db.available(), reason="no database configured")
MEMBER = str(uuid.UUID("00000000-0000-4000-8000-0000000b3001"))
ADMIN = str(uuid.UUID("00000000-0000-4000-8000-0000000b3002"))


@pytest.fixture
def two_roles():
    with db.connect(db.SESSION) as c, c.cursor() as cur:
        for uid, role in ((MEMBER, "member"), (ADMIN, "admin")):
            cur.execute("insert into profiles(user_id,email,email_domain,role) "
                        "values (%s,%s,'interviewkickstart.com',%s) "
                        "on conflict (user_id) do update set role=excluded.role",
                        (uid, f"b3-{role}-synthetic@interviewkickstart.com", role))
    yield
    with db.connect(db.SESSION) as c, c.cursor() as cur:
        cur.execute("delete from profiles where user_id = any(%s)",
                    ([MEMBER, ADMIN],))


def _structure_and_etag(subject):
    with data.request_connection(subject) as conn:
        return data.structure(conn), data.structure_etag(conn)


@needs_db
def test_the_payload_is_complete_laid_out_and_small(two_roles):
    p, _ = _structure_and_etag(MEMBER)
    with db.connect(db.SESSION) as c, c.cursor() as cur:
        cur.execute("select count(*) from nodes where type = any(%s)",
                    (sorted(data.STRUCTURE_TYPES),))
        assert p["n"] == cur.fetchone()[0], "a structure node went missing"
        cur.execute("select count(*) from node_layout")
        laid = cur.fetchone()[0]
    assert laid == p["n"], "every structure node should carry a coordinate"
    xy = struct.unpack(f"<{2 * p['n']}f", base64.b64decode(p["xy"]))
    assert all(math.isfinite(v) for v in xy)
    import brotli
    import index
    size = len(brotli.compress(json.dumps(p, separators=(",", ":")).encode(),
                               quality=index.BROTLI_QUALITY))     # what is SERVED
    assert size <= 150 * 1024, f"{size} B brotli, over the 150 KB target"


@needs_db
def test_every_structure_edge_survives_including_same_triple_ones(two_roles):
    p, _ = _structure_and_etag(MEMBER)
    with db.connect(db.SESSION) as c, c.cursor() as cur:
        cur.execute("""select count(*) from edges where rel <> %s
                       and source_id in (select id from nodes where type = any(%s))
                       and target_id in (select id from nodes where type = any(%s))""",
                    (taxonomy.edge_for_role("provenance"),
                     sorted(data.STRUCTURE_TYPES), sorted(data.STRUCTURE_TYPES)))
        want = cur.fetchone()[0]
    eid = struct.unpack(f"<{p['m']}I", base64.b64decode(p["eid"]))
    assert p["m"] == want and len(set(eid)) == want


@needs_db
def test_the_etag_is_stable_and_follows_the_role(two_roles):
    _, a1 = _structure_and_etag(MEMBER)
    _, a2 = _structure_and_etag(MEMBER)
    _, b = _structure_and_etag(ADMIN)
    assert a1 and a1 == a2, "the validator must be stable across requests"
    assert a1 != b, "a member and an admin must never share a cached payload"


@needs_db
def test_no_projection_visible_means_no_validator():
    with data.request_connection(None) as conn:
        assert data.structure_etag(conn) is None


@needs_db
def test_detail_brings_back_every_panel_only_prop(two_roles):
    with db.connect(db.SESSION) as c, c.cursor() as cur:
        cur.execute("""select source_id, count(*) from edges
                       where props ? 'attached_file' group by 1
                       order by 2 desc limit 1""")
        mod, attached = cur.fetchone()
    with data.request_connection(MEMBER) as conn:
        d = data.node_detail(conn, mod)
    got = [e for e in d["edges"] if "attached_file" in (e["props"] or {})]
    assert len(got) == attached, "detail must carry EVERY attached-file edge"
    assert all(e["id"] for e in got)


if __name__ == "__main__" and "--write" in sys.argv:
    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE.write_text(json.dumps(_packed(), indent=1, sort_keys=True) + "\n",
                       encoding="utf-8")
    print(f"wrote {FIXTURE.relative_to(REPO)}")
