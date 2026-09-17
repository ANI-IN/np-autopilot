"""The reasoning survives the round trip — and the check that says so can fail.

Three curation files carry ~7,400 characters of comments recording WHY each
decision was made. No column holds them, so the losslessness check cannot see
them: drop every comment and each row still compares equal.

`extract_notes` is therefore a check of exactly the kind this project has got
wrong three times — one that reports success without having looked. So each
test here MUTATES the stored notes and asserts the check turns red. A test that
only ever sees the clean state proves the check runs, not that it detects.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import curation                                          # noqa: E402
from pipeline.lib import db                                            # noqa: E402
from pipeline.lib.paths import CONFIG_DIR                              # noqa: E402

# db.available() rather than a hand-named env var: naming the variable here
# means a rename leaves these tests SKIPPING rather than failing, which is the
# same silence they exist to detect.
needs_db = pytest.mark.skipif(not db.available(),
                              reason="needs the Supabase connection")

#: The specific comment this whole mechanism exists to keep. `03_resolve.py`
#: proposes middle-name variants; two real people share a first name and a
#: surname initial. The note is a guard against a particular merge.
KARTHIKA = "fuzzy pass ever merges them"


# ---------------------------------------------------------------------------
# extraction — offline, no database
# ---------------------------------------------------------------------------

def test_extracts_all_three_comment_shapes():
    """A block before a row, a block inside a row body, a trailing inline."""
    notes = curation.extract_notes("people.yaml")
    assert notes, "no comments extracted from a file that has ~90 lines of them"
    keys = {k for k, _, _ in notes}
    assert curation.FILE_ANCHOR in keys, "file-level reasoning not anchored"
    assert any(k != curation.FILE_ANCHOR for k in keys), "no row-level notes"


def test_the_karthika_guard_is_extracted():
    """v1 of extract_notes dropped it: it only handled blocks BEFORE a row.

    The guard is a trailing inline comment continued on the next line, which is
    how a person actually writes a caveat about one entry.
    """
    notes = curation.extract_notes("people.yaml")
    hit = [(k, n) for k, _, n in notes if KARTHIKA in n]
    assert hit, "the Karthika merge guard was not extracted"
    key, _ = hit[0]
    assert key != curation.FILE_ANCHOR, \
        f"the guard anchored to the file, not to a row — it reads as a general " \
        f"remark rather than a caveat about {key!r}"


def test_the_sibling_domain_rule_is_extracted():
    """domain-aliases.yaml's reasoning is file-level: the rule for the file."""
    notes = curation.extract_notes("domain-aliases.yaml")
    text = "\n".join(n for k, _, n in notes if k == curation.FILE_ANCHOR)
    assert "SIBLING-DOMAIN TEST" in text
    # The three unresolved aliases are named in that block, with their costs.
    for alias in ("ML", "Product Management", "Agentic AI"):
        assert alias in text, f"{alias} missing from the file-level reasoning"


def test_hash_inside_a_quoted_string_is_not_a_comment():
    """`title: "Lead, C#/.NET"` is a value, not a comment introducer."""
    assert curation._inline_comment('  name: "a # b"') is None
    assert curation._inline_comment("  name: 'a # b'") is None
    assert curation._inline_comment("  name: x  # real") == "real"
    assert curation._inline_comment("  name: x") is None


def test_every_comment_line_in_the_sources_is_accounted_for():
    """Aggregate check: no comment line silently falls through the parser."""
    for fname, *_ in curation.SPECS:
        raw = (CONFIG_DIR / fname).read_text(encoding="utf-8")
        in_file = [l.strip().lstrip("#").strip() for l in raw.splitlines()
                   if l.strip().startswith("#")]
        in_file = [l for l in in_file if l]
        captured = "\n".join(n for _, _, n in curation.extract_notes(fname))
        missed = [l for l in in_file if l not in captured]
        assert not missed, f"{fname}: {len(missed)} comment lines dropped: {missed[:3]}"


# ---------------------------------------------------------------------------
# the round trip, and its ability to fail
# ---------------------------------------------------------------------------

def _roundtrip() -> tuple[int, str]:
    r = subprocess.run([sys.executable, "pipeline/curation.py", "roundtrip"],
                       cwd=ROOT, capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


@needs_db
def test_roundtrip_is_clean_to_start_with():
    code, out = _roundtrip()
    assert "ROUND TRIP CLEAN" in out, out
    assert code == 0
    assert "7363/7363" in out or "chars of reasoning kept" in out


def _service(cur):
    """The trigger refuses any curation write that does not announce itself."""
    cur.execute("select set_config('np.writing_through_service','on',true)")


def _export_text(fname: str) -> str:
    curation.cmd_export(".rt-check.yaml")
    return (CONFIG_DIR / fname.replace(".yaml", ".rt-check.yaml")
            ).read_text(encoding="utf-8")


def _clean_rt_check():
    for fname, *_ in curation.SPECS:
        (CONFIG_DIR / fname.replace(".yaml", ".rt-check.yaml")).unlink(missing_ok=True)


@needs_db
def test_a_deleted_note_turns_the_check_red():
    """THE ANTI-VACUITY TEST. Remove one note; the export must lose it.

    Without this, 'PRESERVED' proves only that the function returned. Export is
    called directly rather than via `roundtrip`, because roundtrip re-imports
    from the YAML first and would quietly undo the deletion — a test that
    repairs its own mutation before checking proves nothing.
    """
    with db.connect(db.SESSION) as conn, conn.cursor() as cur:
        cur.execute("select id, scope, row_key, position, note from curation_notes "
                    "where note like %s", (f"%{KARTHIKA}%",))
        row = cur.fetchone()
        assert row, "the guard is not in the database; import did not run"
        _, scope, row_key, pos, text = row
        note_id = row[0]

        assert KARTHIKA in _export_text("people.yaml"), \
            "the guard is not in the export even BEFORE deleting it"

        _service(cur)
        cur.execute("delete from curation_notes where id = %s", (note_id,))
        conn.commit()
        try:
            assert KARTHIKA not in _export_text("people.yaml"), \
                "deleting the note changed nothing in the export — the export " \
                "is not reading curation_notes at all"
        finally:
            _service(cur)
            # `id` is GENERATED ALWAYS, so the row comes back with a new one.
            # The id is a surrogate; (scope, row_key, position) is the identity
            # that the export orders by and that the check compares.
            cur.execute("insert into curation_notes(scope,row_key,position,note)"
                        " values (%s,%s,%s,%s)", (scope, row_key, pos, text))
            conn.commit()
            _clean_rt_check()

    assert KARTHIKA in _export_text("people.yaml"), "teardown did not restore"
    _clean_rt_check()


@needs_db
def test_a_corrupted_note_turns_the_check_red():
    """Not just absence — a note whose WORDS changed must fail too.

    Deletion and corruption are different failures. An import that mangles text
    while keeping the row count would pass a check that only counts.
    """
    bland = "a bland remark that says nothing"
    with db.connect(db.SESSION) as conn, conn.cursor() as cur:
        cur.execute("select id, note from curation_notes where note like %s",
                    (f"%{KARTHIKA}%",))
        note_id, text = cur.fetchone()
        _service(cur)
        cur.execute("update curation_notes set note = %s where id = %s",
                    (bland, note_id))
        conn.commit()
        try:
            rendered = _export_text("people.yaml")
            assert KARTHIKA not in rendered, "corruption did not reach the export"
            assert bland in rendered, "the corrupted text was not rendered either"
        finally:
            _service(cur)
            cur.execute("update curation_notes set note = %s where id = %s",
                        (text, note_id))
            conn.commit()
            _clean_rt_check()


@needs_db
def test_a_stray_database_row_is_not_excused_as_pending():
    """The pending-alias exemption must not swallow a genuine extra row.

    Six unresolved aliases legitimately exist in the database and not in the
    file. The check exempts them by NAMING the shape (unconfirmed, no domain).
    A confirmed row not in the file is a different thing and must fail.

    Fed to `compare_to_source` directly. Going through `roundtrip` would prove
    nothing: it truncates and reloads from the YAML first, so the stray row is
    gone before the comparison runs — the check would have reported CLEAN
    because the mutation had been undone, not because it was absent.
    """
    exported = curation._export_rows()
    ok, lines = curation.compare_to_source(exported)
    assert ok, "the database drifted before the test started:\n" + "\n".join(lines)

    list_key, rows = exported["domain-aliases.yaml"]
    rows.append({"alias": "ZZ-SYNTHETIC-STRAY", "domain": "Machine Learning",
                 "confirmed": True, "claims": 0})
    ok, lines = curation.compare_to_source(exported)
    out = "\n".join(lines)
    assert not ok, "a confirmed row absent from the file was accepted:\n" + out
    assert "UNEXPLAINED in db" in out and "ZZ-SYNTHETIC-STRAY" in out, out
    # and the six real ones were NOT swept up in the failure
    assert "+6 awaiting a decision" in out, out


@needs_db
def test_a_row_lost_from_the_database_is_detected():
    """The opposite direction, which is the one that actually loses work."""
    exported = curation._export_rows()
    list_key, rows = exported["people.yaml"]
    dropped = rows.pop()
    ok, lines = curation.compare_to_source(exported)
    out = "\n".join(lines)
    assert not ok, "a row that vanished from the database was accepted:\n" + out
    assert "LOST from the file" in out and dropped["canonical"] in out, out


@needs_db
def test_a_changed_field_is_detected():
    """And a field whose value quietly changed."""
    exported = curation._export_rows()
    rows = exported["people.yaml"][1]
    rows[0] = dict(rows[0], team="ZZ-SYNTHETIC")
    ok, lines = curation.compare_to_source(exported)
    out = "\n".join(lines)
    assert not ok and "field  " in out, out


@needs_db
def test_the_pending_aliases_are_still_exempt():
    """The other half of the same boundary: the six real ones must NOT fail.

    Asserted separately so that a change tightening the exemption out of
    existence shows up as a failure here rather than as a green run.
    """
    code, out = _roundtrip()
    assert "+6 awaiting a decision" in out, out
    assert "ROUND TRIP CLEAN" in out


@needs_db
def test_exported_file_is_valid_yaml_with_the_comments_in_it():
    """Comments must not break the file they are rendered into."""
    curation.cmd_export(".rt-check.yaml")
    try:
        for fname, list_key, _, pk, _ in curation.SPECS:
            path = CONFIG_DIR / fname.replace(".yaml", ".rt-check.yaml")
            doc = yaml.safe_load(path.read_text(encoding="utf-8"))
            assert doc["version"] == 1
            assert doc[list_key], f"{fname}: no rows survived rendering"
            assert all(pk in r for r in doc[list_key])
    finally:
        for fname, *_ in curation.SPECS:
            (CONFIG_DIR / fname.replace(".yaml", ".rt-check.yaml")).unlink(missing_ok=True)
