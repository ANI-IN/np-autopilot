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
                    ph = ", ".join(["%s"] * len(names))
                    cur.execute(
                        f"insert into {table} ({', '.join(names)}) values ({ph})",
                        list(values.values()) + [json.dumps(props, sort_keys=True)])
                # The UNRESOLVED aliases live under a different key and have no
                # target. They are the decisions this system exists to surface,
                # so they are imported rather than left in a YAML comment where
                # nothing can query them.
                if table == "domain_aliases":
                    for row in (data.get("ambiguous") or []):
                        cur.execute(
                            "insert into domain_aliases(alias, domain, claims, "
                            "sibling_test, confirmed, note, props) values "
                            "(%s, null, %s, 'failed', false, %s, %s) "
                            "on conflict (alias) do nothing",
                            (row["alias"], row.get("claims"), row.get("why"),
                             json.dumps({"candidates": row.get("candidates") or [],
                                         "unresolved": True}, sort_keys=True)))
                if table == "people":
                    for row in rows:
                        for alias in (row.get("aliases") or []):
                            cur.execute(
                                "insert into people_aliases(alias, canonical) "
                                "values (%s,%s) on conflict (alias) do nothing",
                                (alias, row["canonical"]))
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


def cmd_export(suffix: str = ".exported.yaml") -> int:
    for fname, (list_key, rows) in _export_rows().items():
        target = CONFIG_DIR / fname.replace(".yaml", suffix)
        payload = {
            "version": 1,
            "note": ("EXPORTED FROM POSTGRES by pipeline/curation.py. Not "
                     "byte-identical to the hand-written file: that one carries "
                     "the comments recording why each decision was made, and a "
                     "column cannot hold a comment. Every FIELD round-trips."),
            list_key: rows,
        }
        target.write_text(
            yaml.safe_dump(payload, sort_keys=False, allow_unicode=True,
                           width=100, default_flow_style=False),
            encoding="utf-8")
        print(f"  wrote {target.name}  ({len(rows)} rows)")
    return 0


def cmd_roundtrip() -> int:
    """Import, export twice, and compare both properties."""
    print("=" * 74)
    print("CURATION ROUND TRIP")
    print("=" * 74)
    cmd_import()
    print()
    first = {f: yaml.safe_dump(v, sort_keys=False) for f, v in _export_rows().items()}
    second = {f: yaml.safe_dump(v, sort_keys=False) for f, v in _export_rows().items()}

    print("  DETERMINISM — two exports, byte-for-byte")
    ok = True
    for fname in first:
        same = first[fname] == second[fname]
        ok &= same
        print(f"    {fname:<26} {'IDENTICAL' if same else 'DIFFERS'}")

    print("\n  LOSSLESSNESS — every field survives YAML -> db -> YAML")
    exported = _export_rows()
    for fname, list_key, table, pk, cols in SPECS:
        original = yaml.safe_load((CONFIG_DIR / fname).read_text(encoding="utf-8"))
        src = {r[pk]: _jsonable(r) for r in (original.get(list_key) or [])}
        got = {r[pk]: r for r in exported[fname][1]}
        missing_rows = sorted(set(src) - set(got))
        extra_rows = sorted(set(got) - set(src))
        field_diffs = []
        for key in sorted(set(src) & set(got)):
            for field, value in src[key].items():
                if got[key].get(field) != value:
                    field_diffs.append(f"{key}.{field}")
        status = "LOSSLESS" if not (missing_rows or extra_rows or field_diffs) else "LOSSY"
        ok &= status == "LOSSLESS"
        print(f"    {fname:<26} {status}  "
              f"rows {len(src)}->{len(got)}  field diffs {len(field_diffs)}")
        for d in field_diffs[:5]:
            print(f"        {d}")
        for r in (missing_rows + extra_rows)[:5]:
            print(f"        row {r!r}")
    print()
    print("=" * 74)
    print("RESULT:", "ROUND TRIP CLEAN" if ok else "ROUND TRIP FAILED")
    print("=" * 74)
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["import", "export", "roundtrip"])
    args = ap.parse_args()
    return {"import": cmd_import, "export": cmd_export,
            "roundtrip": cmd_roundtrip}[args.command]()


if __name__ == "__main__":
    raise SystemExit(main())
