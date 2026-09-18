"""A field added to a curation YAML must reach the database.

`pipeline/curation.py` promises it at the top: *"Everything not named here lands
in `props`, so a field added to the YAML survives a round trip without a
migration."* That was true for resolved rows and FALSE for the ambiguous ones,
whose import built `props` as a literal `{candidates, unresolved}` and dropped
everything else.

WHY NOTHING CAUGHT IT. `curation.py roundtrip` reports LOSSLESS by comparing
`domain-aliases.exported.yaml` with `domain-aliases.rt-check.yaml` — two files
both derived from the DATABASE. A field the import never stored is absent from
both sides, so the check agrees with itself about a field neither of them has.
DECISIONS §A.7b rule 2: a guard must not take its evidence from the thing it is
checking.

So these read the SOURCE YAML — evidence from outside the loop — and assert the
database holds what it declares.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from pipeline.lib import db                                           # noqa: E402

SOURCE = REPO / "config" / "domain-aliases.yaml"

pytestmark = pytest.mark.skipif(
    not db.available(),
    reason="no SUPABASE_DB_URL_SESSION / psycopg — database tests skipped")

#: Fields the ambiguous import maps to real columns rather than to props.
COLUMNS = {"alias", "claims", "why", "candidates"}


def _ambiguous_source() -> list[dict]:
    rows = yaml.safe_load(SOURCE.read_text(encoding="utf-8")).get("ambiguous") or []
    assert rows, "no ambiguous aliases in the source YAML — has the key moved?"
    return rows


def test_every_declared_field_on_an_unresolved_alias_reaches_the_database():
    source = _ambiguous_source()
    with db.connect(db.SESSION) as conn, conn.cursor() as cur:
        cur.execute("select alias, props from domain_aliases "
                    "where props ->> 'unresolved' = 'true'")
        stored = {a: (p or {}) for a, p in cur.fetchall()}

    missing = []
    for row in source:
        props = stored.get(row["alias"])
        assert props is not None, f"{row['alias']} is not in the database at all"
        for field, value in row.items():
            if field in COLUMNS:
                continue
            if field not in props:
                missing.append(f"{row['alias']}.{field} (declared, not stored)")
            elif props[field] != value:
                missing.append(
                    f"{row['alias']}.{field}: YAML {value!r}, database {props[field]!r}")

    assert not missing, (
        "fields declared in config/domain-aliases.yaml never reached the "
        "database:\n  " + "\n  ".join(missing) + "\n\n"
        "curation.py's own round-trip check cannot see this: it compares two "
        "database-derived files with each other.")


def test_the_agentic_ai_alias_is_marked_unanswerable_from_this_data():
    """Not a decision waiting on someone — a question the corpus cannot answer.

    Its four candidates differ only by audience (EM, SWE, TPM/Pm, an India
    bootcamp) and nothing in the instructor's row records an audience, so
    corroboration is 0 of 64: absent, not weak. The surface must say so rather
    than present it as pending, and that judgement lives in the data so the UI
    renders a recorded fact instead of asserting one in JavaScript.
    """
    row = next((r for r in _ambiguous_source() if r["alias"] == "Agentic AI"), None)
    assert row is not None, "the Agentic AI alias is gone from the source"
    assert row.get("answerable_from_data") is False, (
        "Agentic AI is no longer marked unanswerable. If that is deliberate, "
        "the surface will start presenting it as a decision awaiting a person — "
        "which it is not, until something records audience.")

    with db.connect(db.SESSION) as conn, conn.cursor() as cur:
        cur.execute("select props from domain_aliases where alias = 'Agentic AI'")
        props = cur.fetchone()[0] or {}
    assert props.get("answerable_from_data") is False, \
        "the flag is in the YAML but never reached the database"
