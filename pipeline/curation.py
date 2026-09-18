#!/usr/bin/env python3
"""D3 — curation tables: import from YAML, export back, losslessly.

DECISIONS §B.1: Postgres is the source of truth for CURATION. These three files
are the only ones a human hand-edits, and they are the reason the split exists —
three alias decisions worth 272 edges have been waiting on a human for a week
because the only way to record one is to edit YAML in a checkout.

The export is what makes that safe to adopt. Until the pipeline reads curation
from Postgres directly, the YAML files remain what it reads, so a round trip has
to be lossless or the database is a place decisions go to be silently altered.

TWO PROPERTIES, and they are different claims:

  DETERMINISM   export twice, get byte-identical output. Same shape as
                tests/test_deterministic_ids.py: no timestamps, no set
                iteration order, no dict ordering luck.
  LOSSLESSNESS  YAML -> database -> YAML preserves every field and value.
                NOT byte-identical to the hand-written file, and it never will
                be: those files carry ~200 lines of comments recording why each
                decision was made, and a database column cannot hold a comment.
                Claiming byte-identity against the original would mean either
                discarding the comments or pretending to round-trip them.

Usage:
    python3 pipeline/curation.py import      # YAML -> Postgres
    python3 pipeline/curation.py export      # Postgres -> config/*.exported.yaml
    python3 pipeline/curation.py roundtrip   # import, export, compare
    python3 pipeline/curation.py check       # drift: database vs YAML, no import
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import yaml                                                            # noqa: E402

from pipeline.lib import db                                            # noqa: E402
from pipeline.lib.paths import CONFIG_DIR                              # noqa: E402

#: (yaml file, top-level list key, table, primary-key field, column fields)
#: Everything not named here lands in `props`, so a field added to the YAML
#: survives a round trip without a migration.
SPECS = [
    ("people.yaml", "people", "people", "canonical",
     ("canonical", "team", "title", "seniority")),
    ("domain-aliases.yaml", "aliases", "domain_aliases", "alias",
     ("alias", "domain", "claims", "sibling_test", "confirmed",
      "confirmed_by", "confirmed_at", "note")),
    ("workflow-owners.yaml", "workflows", "workflow_owners", "id",
     ("id", "name", "theme_id", "owner", "confirmed", "suggestion")),
]
#: workflow-owners uses `id` in YAML and `workflow_id` in the table.
COLUMN_RENAMES = {"workflow_owners": {"id": "workflow_id",
                                      "suggestion_evidence": "evidence"}}


def _jsonable(value):
    import datetime as _dt
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    if isinstance(value, (_dt.date, _dt.datetime)):
        return value.isoformat()
    return value


#: Which line starts a row, per file. Used to attach a preceding comment block
#: to the row it explains.
ROW_START = {
    "people.yaml": "canonical",
    "domain-aliases.yaml": "alias",
    "workflow-owners.yaml": "id",
}
FILE_ANCHOR = "__file__"


def _inline_comment(line: str) -> str | None:
    """Trailing `# ...` on a value line, ignoring a # inside a quoted string.

    Conservative on purpose: a `#` is only a comment when it follows
    whitespace AND the text before it has balanced quotes. A value containing a
    hash is left alone rather than half-captured.
    """
    in_s = in_d = False
    for i, ch in enumerate(line):
        if ch == "'" and not in_d:
            in_s = not in_s
        elif ch == '"' and not in_s:
            in_d = not in_d
        elif ch == "#" and not in_s and not in_d and i > 0 and line[i - 1].isspace():
            text = line[i + 1:].strip()
            return text or None
    return None


def extract_notes(fname: str) -> list[tuple[str, int, str]]:
    """(row_key, position, note) for every comment in a curation file.

    Line-based rather than via a comment-preserving YAML parser, deliberately:
    ruamel.yaml would round-trip comments automatically but adds a dependency
    whose behaviour nobody here has characterised, and the comment-to-row
    mapping would still be implicit. This is explicit and inspectable.

    THREE shapes, and the first version of this function only handled one —
    which silently dropped the note that matters most. people.yaml pins
    `not_same_as: [Karthika Pai, Karthika Saran]` with an INLINE comment giving
    the reason, and 03_resolve.py proposes middle-name variants at any
    threshold, so that note is the only thing standing between a future fuzzy
    pass and a wrong merge.

      * a block BEFORE a row      -> that row
      * a block INSIDE a row body -> that row
      * a trailing inline comment -> that row
      * anything before the first row, or after the last -> the file
    """
    import re
    key = ROW_START[fname]
    row_re = re.compile(rf"^\s*-\s*{re.escape(key)}\s*:\s*(.+?)\s*$")
    out: list[tuple[str, int, str]] = []
    block: list[str] = []
    current = FILE_ANCHOR
    seen_first_row = False
    counters: dict[str, int] = {}

    def flush(row_key: str) -> None:
        if not block:
            return
        text = "\n".join(block).strip()
        if text:
            pos = counters.get(row_key, 0)
            counters[row_key] = pos + 1
            out.append((row_key, pos, text))
        block.clear()

    for raw in (CONFIG_DIR / fname).read_text(encoding="utf-8").splitlines():
        line = raw.rstrip()
        stripped = line.strip()

        if stripped.startswith("#"):
            block.append(stripped.lstrip("#").rstrip())
            continue

        m = row_re.match(line)
        if m:
            # A block immediately before a row explains that row.
            pending = list(block)
            block.clear()
            current = m.group(1).strip().strip("'\"")
            seen_first_row = True
            block.extend(pending)
            flush(current)
            inline = _inline_comment(line)
            if inline:
                block.append(inline)
                flush(current)
            continue

        if not stripped:
            continue                     # a blank line does not end a block

        # A value line inside a row: any block above it belongs to this row.
        flush(current if seen_first_row else FILE_ANCHOR)
        inline = _inline_comment(line)
        if inline:
            block.append(inline)
            flush(current if seen_first_row else FILE_ANCHOR)

    flush(FILE_ANCHOR)                   # trailing block, after the last row
    return out


def curation_hash() -> str:
    """Deterministic hash of the curation CONTENT the pipeline actually reads.

    Hashes the PARSED yaml, not the file bytes, so reformatting or a comment
    edit does not look like a decision change — and a decision change cannot
    hide behind identical formatting.

    Computed from the FILES rather than the database on purpose: the files are
    what passes 2-4 consume, validate.py runs with no database, and a lock that
    could only be checked with a connection would go unchecked wherever it
    mattered most.
    """
    import hashlib
    payload = {}
    for fname, list_key, *_ in SPECS:
        data = yaml.safe_load((CONFIG_DIR / fname).read_text(encoding="utf-8"))
        payload[fname] = _jsonable(data.get(list_key) or [])
    canon = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canon.encode()).hexdigest()


def cmd_import() -> int:
    with db.connect(db.SESSION) as conn:
        with conn.cursor() as cur:
            # This IS the service layer, in its import direction, so it declares
            # itself rather than being exempted from the trigger.
            #
            # The trigger exists to stop ad-hoc single-row edits that skip
            # optimistic locking and clobber a concurrent decision. A full
            # reload from the canonical YAML is a different operation: it has no
            # concurrent counterpart to lose, because it replaces everything
            # from the file the pipeline already treats as authoritative.
            #
            # It is deliberately NOT a general escape hatch — the flag is set
            # here and in web/lib/curation_service.py, and a test asserts no
            # third place sets it.
            cur.execute("select set_config('np.writing_through_service','on',true)")
            # Order matters: people_aliases and workflow_owners reference people.
            cur.execute("truncate workflow_owners, people_aliases, "
                        "domain_aliases, people")
            batch: dict[tuple, list] = {}
            for fname, list_key, table, pk, cols in SPECS:
                data = yaml.safe_load((CONFIG_DIR / fname).read_text(encoding="utf-8"))
                rows = data.get(list_key) or []
                renames = COLUMN_RENAMES.get(table, {})
                for row in rows:
                    props = {k: _jsonable(v) for k, v in row.items()
                             if k not in cols}
                    # A renamed field is a column, not a prop.
                    for src_name, col in renames.items():
                        if src_name in props:
                            props.pop(src_name)
                    values = {renames.get(c, c): _jsonable(row.get(c)) for c in cols}
                    for src_name, col in renames.items():
                        if src_name in row and col not in values:
                            values[col] = _jsonable(row.get(src_name))
                    # An owner naming nobody is NULL, not the empty string:
                    # 92 workflows with no owner is the correct final state and
                    # must not read as "owned by ''".
                    for k, v in list(values.items()):
                        if isinstance(v, str) and not v.strip():
                            values[k] = None
                    if table == "workflow_owners" and values.get("owner"):
                        # FK to people(canonical); an owner not in people.yaml
                        # would abort the whole import, which is correct but
                        # unhelpful without saying which.
                        pass
                    names = list(values) + ["props"]
                    batch.setdefault(tuple(names), []).append(
                        list(values.values()) + [json.dumps(props, sort_keys=True)])
                # ONE round trip per column-shape instead of one per row.
                #
                # WHY THIS IS NOT A MICRO-OPTIMISATION. At 148 ms to
                # ap-northeast-2, 215 single-row inserts cost 36.5 seconds — and
                # all of it inside the transaction that holds the TRUNCATE's
                # ACCESS EXCLUSIVE lock on all four curation tables. Anything
                # else touching them waits, and a blocked TRUNCATE presents as a
                # hung process rather than an error, so a slow import turned
                # into cascading test-suite hangs that looked like four
                # different faults.
                for names, rows_batch in batch.items():
                    ph = ", ".join(["%s"] * len(names))
                    cur.executemany(
                        f"insert into {table} ({', '.join(names)}) values ({ph})",
                        rows_batch)
                batch = {}
                # The UNRESOLVED aliases live under a different key and have no
                # target. They are the decisions this system exists to surface,
                # so they are imported rather than left in a YAML comment where
                # nothing can query them.
                if table == "domain_aliases":
                    amb = [(row["alias"], row.get("claims"), row.get("why"),
                            json.dumps({"candidates": row.get("candidates") or [],
                                        "unresolved": True}, sort_keys=True))
                           for row in (data.get("ambiguous") or [])]
                    if amb:
                        cur.executemany(
                            "insert into domain_aliases(alias, domain, claims, "
                            "sibling_test, confirmed, note, props) values "
                            "(%s, null, %s, 'failed', false, %s, %s) "
                            "on conflict (alias) do nothing", amb)
                # The REASONING, which no column holds. Option 2 from the F2
                # proposal: a note keyed to (file, row_key), with __file__ for
                # reasoning that belongs to the file rather than any row.
                cur.execute("delete from curation_notes where scope = %s", (fname,))
                notes = [(fname, row_key, pos, note)
                         for row_key, pos, note in extract_notes(fname)]
                if notes:
                    cur.executemany(
                        "insert into curation_notes(scope,row_key,position,note) "
                        "values (%s,%s,%s,%s)", notes)

                if table == "people":
                    pairs = [(alias, row["canonical"]) for row in rows
                             for alias in (row.get("aliases") or [])]
                    if pairs:
                        cur.executemany(
                            "insert into people_aliases(alias, canonical) "
                            "values (%s,%s) on conflict (alias) do nothing", pairs)
                print(f"  {table:<16} {len(rows):>4} rows")
        conn.commit()
    return 0


def _export_rows():
    out = {}
    with db.connect(db.SESSION) as conn, conn.cursor() as cur:
        for fname, list_key, table, pk, cols in SPECS:
            renames = COLUMN_RENAMES.get(table, {})
            db_pk = renames.get(pk, pk)
            db_cols = [renames.get(c, c) for c in cols]
            extra = [v for v in renames.values() if v not in db_cols]
            select = ", ".join(db_cols + extra + ["props"])
            # ORDER BY the primary key: deterministic, and independent of
            # insertion order or physical row placement.
            cur.execute(f"select {select} from {table} order by {db_pk}")
            rows = []
            inverse = {v: k for k, v in renames.items()}
            for rec in cur.fetchall():
                values = dict(zip(db_cols + extra, rec[:-1]))
                props = rec[-1] or {}
                row = {}
                for c in cols:
                    v = values.get(renames.get(c, c))
                    if v is not None:
                        row[c] = _jsonable(v)
                for col in extra:
                    v = values.get(col)
                    if v is not None:
                        row[inverse.get(col, col)] = _jsonable(v)
                row.update(props)
                rows.append(row)
            out[fname] = (list_key, rows)
    return out


def _notes_for(conn, fname: str) -> dict[str, list[str]]:
    with conn.cursor() as cur:
        cur.execute("select row_key, note from curation_notes where scope = %s "
                    "order by row_key, position", (fname,))
        out: dict[str, list[str]] = {}
        for row_key, note in cur.fetchall():
            out.setdefault(row_key, []).append(note)
    return out


def _as_comment(lines: list[str], indent: str = "") -> str:
    return "\n".join(f"{indent}#{(' ' + l) if l else ''}" for note in lines
                      for l in note.split("\n")) + "\n"


def cmd_export(suffix: str = ".exported.yaml") -> int:
    exported = _export_rows()
    with db.connect(db.SESSION) as conn:
        for fname, (list_key, rows) in exported.items():
            notes = _notes_for(conn, fname)
            pk = next(spec[3] for spec in SPECS if spec[0] == fname)
            target = CONFIG_DIR / fname.replace(".yaml", suffix)

            parts = []
            if notes.get(FILE_ANCHOR):
                # File-level reasoning FIRST, because that is where the rule the
                # whole file applies lives — the sibling-domain test, in the case
                # of domain-aliases.yaml.
                parts.append(_as_comment(notes[FILE_ANCHOR]))
                parts.append("\n")
            parts.append(yaml.safe_dump(
                {"version": 1,
                 "note": ("EXPORTED FROM POSTGRES by pipeline/curation.py. "
                          "Comments are regenerated from curation_notes, not "
                          "preserved from the previous file.")},
                sort_keys=False, allow_unicode=True, width=100))
            parts.append(f"\n{list_key}:\n")
            for row in rows:
                key = str(row.get(pk, ""))
                if notes.get(key):
                    parts.append(_as_comment(notes[key], indent="  "))
                body = yaml.safe_dump([row], sort_keys=False, allow_unicode=True,
                                      width=100, default_flow_style=False)
                parts.append("".join(f"  {l}\n" if l.strip() else "\n"
                                     for l in body.splitlines()))
            target.write_text("".join(parts), encoding="utf-8")
            kept = sum(len(v) for v in notes.values())
            print(f"  wrote {target.name}  ({len(rows)} rows, {kept} note blocks)")
    return 0


def compare_to_source(exported) -> tuple[bool, list[str]]:
    """Compare an exported row set against the hand-written YAML.

    Returns (ok, lines). Separated from cmd_roundtrip so a test can hand it a
    fabricated row set: `roundtrip` TRUNCATES before exporting, so a stray
    database row cannot survive long enough for the round trip to see one.
    """
    ok, lines = True, []
    for fname, list_key, table, pk, cols in SPECS:
        original = yaml.safe_load((CONFIG_DIR / fname).read_text(encoding="utf-8"))
        src = {r[pk]: _jsonable(r) for r in (original.get(list_key) or [])}
        got = {r[pk]: r for r in exported[fname][1]}
        missing_rows = sorted(set(src) - set(got))

        # A row in the database that is not in the file is NOT automatically a
        # loss — migration 0010 deliberately inserted the six aliases awaiting a
        # human, and the hand-curated file holds only confirmed ones. But
        # tolerating extras in general would let a genuine stray row report as
        # "nothing happened", so the pending set is identified POSITIVELY and
        # anything else still fails.
        extra_rows, pending = [], []
        for key in sorted(set(got) - set(src)):
            row = got[key]
            if row.get("confirmed") is False and row.get("domain") is None:
                pending.append(key)
            else:
                extra_rows.append(key)

        field_diffs = []
        for key in sorted(set(src) & set(got)):
            for field, value in src[key].items():
                if got[key].get(field) != value:
                    field_diffs.append(f"{key}.{field}")
        bad = bool(missing_rows or extra_rows or field_diffs)
        ok &= not bad
        note = f"  +{len(pending)} awaiting a decision" if pending else ""
        lines.append(f"    {fname:<26} {'LOSSY' if bad else 'LOSSLESS'}  "
                     f"rows {len(src)}->{len(got)}{note}  "
                     f"field diffs {len(field_diffs)}")
        lines += [f"        field  {d}" for d in field_diffs[:5]]
        lines += [f"        LOST from the file   {r!r}" for r in missing_rows[:5]]
        lines += [f"        UNEXPLAINED in db    {r!r}" for r in extra_rows[:5]]
        if pending:
            lines.append(f"        pending: {', '.join(pending)}")
    return ok, lines


def cmd_check() -> int:
    """Compare the database AS IT IS to the YAML. Does NOT import first.

    This is the drift report. `roundtrip` proves the mechanism is lossless by
    reloading from the file, which necessarily erases any divergence; once
    people write through the curation service the database is SUPPOSED to lead
    the file, and this is what says by how much.
    """
    print("=" * 74)
    print("CURATION DRIFT — database vs config/*.yaml (no import)")
    print("=" * 74)
    ok, lines = compare_to_source(_export_rows())
    print("\n".join(lines))
    print()
    print("RESULT:", "IN SYNC" if ok else "DRIFTED")
    return 0 if ok else 1


def cmd_roundtrip() -> int:
    """Import, export twice, and check all THREE properties."""
    print("=" * 74)
    print("CURATION ROUND TRIP")
    print("=" * 74)
    cmd_import()
    print()

    # DETERMINISM over the RENDERED FILE, not just the rows. Comments are
    # regenerated from curation_notes, so they can reorder; the rows compared
    # alone would not notice.
    cmd_export(".exported.yaml")
    cmd_export(".rt-check.yaml")
    print("\n  DETERMINISM — two exports, whole file byte-for-byte")
    ok = True
    for fname, *_ in SPECS:
        a = CONFIG_DIR / fname.replace(".yaml", ".exported.yaml")
        b = CONFIG_DIR / fname.replace(".yaml", ".rt-check.yaml")
        same = a.read_bytes() == b.read_bytes()
        ok &= same
        print(f"    {fname:<26} {'IDENTICAL' if same else 'DIFFERS'}  "
              f"({len(a.read_bytes())} bytes)")
        b.unlink()

    print("\n  LOSSLESSNESS — every field survives YAML -> db -> YAML")
    lossless, lines = compare_to_source(_export_rows())
    ok &= lossless
    print("\n".join(lines))

    # COMMENTS — the reasoning, which no column holds and which the two checks
    # above cannot see. Losslessness compares ROWS; a note dropped on import
    # leaves every row identical.
    print("\n  COMMENTS — the reasoning survives the trip")
    total_src = total_out = 0
    for fname, *_ in SPECS:
        notes = extract_notes(fname)
        rendered = (CONFIG_DIR / fname.replace(".yaml", ".exported.yaml")
                    ).read_text(encoding="utf-8")
        # Compare the TEXT of each note, line by line, against the rendered
        # file. Position and indentation are presentation; the words are the
        # thing that must not be lost.
        lost = [(k, n) for k, _, n in notes
                if not all(ln.strip() in rendered for ln in n.split("\n"))]
        chars = sum(len(n) for _, _, n in notes)
        total_src += chars
        total_out += chars - sum(len(n) for _, n in lost)
        ok &= not lost
        print(f"    {fname:<26} {'LOST' if lost else 'PRESERVED'}  "
              f"{len(notes)} notes, {chars} chars")
        for k, n in lost[:3]:
            print(f"        dropped on {k!r}: {n.splitlines()[0][:50]}...")
    print(f"    {'TOTAL':<26} {total_out}/{total_src} chars of reasoning kept")

    print()
    print("=" * 74)
    print("RESULT:", "ROUND TRIP CLEAN" if ok else "ROUND TRIP FAILED")
    print("=" * 74)
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("command",
                    choices=["import", "export", "roundtrip", "check"])
    args = ap.parse_args()
    return {"import": cmd_import, "export": cmd_export,
            "roundtrip": cmd_roundtrip, "check": cmd_check}[args.command]()


if __name__ == "__main__":
    raise SystemExit(main())
