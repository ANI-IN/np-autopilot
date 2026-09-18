"""public/stats.json must agree with the database, and must be generated.

The reference implementation published hand-written counts that were ~70% wrong
and stayed wrong. `gen_index.py` exists because of that; this is the same guard
for the landing page, which is the surface where a stale number is least likely
to be noticed — everybody sees it and nobody re-reads it.

DRIFT, not shape. Asserting stats.json "has a nodes key" would pass on a file
that was right in March. These tests compare it against the live projection.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from pipeline.lib import db                                           # noqa: E402

STATS = REPO / "public" / "stats.json"

pytestmark = pytest.mark.skipif(
    not db.available(),
    reason="no SUPABASE_DB_URL_SESSION / psycopg — database tests skipped")


def test_stats_json_exists_and_is_servable():
    """It lives under the Vercel output directory, so the landing page can
    fetch it with no API call and no session."""
    assert STATS.exists(), (
        "public/stats.json is missing — run pipeline/gen_landing_stats.py. The "
        "landing page degrades without it, but the counts simply vanish, and a "
        "page that silently stops saying how fresh it is looks fresh.")
    json.loads(STATS.read_text(encoding="utf-8"))


def test_stats_json_matches_the_projection():
    """DRIFT CHECK. Regenerates from the database and compares."""
    sys.path.insert(0, str(REPO / "pipeline"))
    from pipeline.gen_landing_stats import collect

    with db.connect(db.SESSION) as conn:
        fresh = collect(conn)
    on_disk = json.loads(STATS.read_text(encoding="utf-8"))

    drifted = {k: (on_disk.get(k), v) for k, v in fresh.items()
               if k != "_comment" and on_disk.get(k) != v}
    assert not drifted, (
        "public/stats.json disagrees with the projection — the landing page is "
        "publishing stale numbers. Run pipeline/gen_landing_stats.py.\n"
        + "\n".join(f"  {k}: on disk {a!r}, database {b!r}"
                    for k, (a, b) in sorted(drifted.items())))


def test_the_landing_page_describes_the_projection_not_the_pipeline_graph():
    """The two-graphs trap, asserted rather than hoped for.

    5,048 nodes / 36,677 edges is the PIPELINE graph. The explorer serves the
    projection. Three published figures have already been wrong by carrying one
    into a statement about the other (STATE.md §1), and the landing page is
    exactly where that would happen next.
    """
    stats = json.loads(STATS.read_text(encoding="utf-8"))
    assert stats["scope"] == "public"
    assert stats["nodes"] < 5048, (
        f"stats.json reports {stats['nodes']} nodes — that is the pipeline "
        "graph, which the explorer does not serve")
    with db.connect(db.SESSION) as conn, conn.cursor() as cur:
        cur.execute("select count(*) from nodes")
        assert stats["nodes"] == cur.fetchone()[0]


def test_no_count_on_the_landing_page_is_hand_written():
    """Every number the page shows must come from stats.json.

    A digit typed into index.html is the failure this whole file exists to
    prevent, and it would look completely fine in review.
    """
    import re
    html = (REPO / "public" / "index.html").read_text(encoding="utf-8")
    box = html[html.index('<div id="gate">'):html.index('</div></div>', html.index('<div id="gate">'))]
    # Strip the placeholders the script fills from stats.json.
    prose = re.sub(r'id="st-[a-z]+"[^>]*>[^<]*<', ">/<", box)
    stray = [m for m in re.findall(r"\b\d[\d,]{2,}\b", prose)]
    assert not stray, (
        f"hand-written counts in the landing markup: {stray}. Every number "
        "there must come from public/stats.json, which is generated.")
