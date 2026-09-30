"""Search never lists a held-back topic (owner review 2026-09-30).

Slide titles that are a person's name or bio ("Introduction – Konstantinos
Pappas") are marked `not_a_topic` by the merge (module_merge.classify_topics).
They must not appear under Topics in search results; they stay in the graph
and their own panel says "Held back".
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(REPO), str(REPO / "web")]

from lib import data                                                    # noqa: E402


class _Cur:
    def __init__(self, seen):
        self.seen, self.description = seen, [("id",), ("type",), ("label",)]

    def execute(self, sql, args=None):
        self.seen.append(sql)

    def fetchall(self):
        return []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _Conn:
    def __init__(self):
        self.seen = []

    def cursor(self):
        return _Cur(self.seen)


def test_the_search_query_excludes_held_back_topics():
    conn = _Conn()
    data.search(conn, "Konstantinos")
    sql = conn.seen[-1]
    assert "not_a_topic" in sql and "is null" in sql, sql


def test_the_topic_panel_says_it_is_held_back():
    page = (REPO / "public" / "index.html").read_text(encoding="utf-8")
    assert "Held back: " in page and "content_topic: p => p.not_a_topic" in page
