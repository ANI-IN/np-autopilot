#!/usr/bin/env python3
"""Prove a database backup restores: restore it into a scratch database on the LOCAL stack and compare
every table's row count with the dump's.

    python scripts/verify_backup_restore.py backups/dev_backup_<UTC>.sql [--scratch kb_restore_check] [--keep]

The run-C safety sequence (owner decision 2026-11-07) starts with a restore-TESTED backup: a backup is
trusted only after this passes. Local only (the Supabase stack's database container); never DEV or
production. The dump is fed to psql inside the local database container, so nothing leaves the machine.
Prints table counts only. Exit 0 = every table with data in the dump has the same number of rows after
restoring; 1 = a mismatch or a missing table.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

import psycopg

LOCAL = "postgresql://postgres:postgres@127.0.0.1:54322/{db}"
CONTAINER = "supabase_db_np-autopilot-test"


def dump_counts(path: Path) -> dict[str, int]:
    out, cur, n = {}, None, 0
    with path.open(encoding="utf-8", errors="replace") as f:
        for line in f:
            if cur is None:
                m = re.match(r"^COPY ([\w.\"]+) \(.*\) FROM stdin;$", line.rstrip("\n"))
                if m:
                    cur, n = m.group(1).replace('"', ""), 0
                continue
            if line.rstrip("\n") == "\\.":
                out[cur] = n
                cur = None
                continue
            n += 1
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("dump")
    ap.add_argument("--scratch", default="kb_restore_check")
    ap.add_argument("--keep", action="store_true", help="keep the scratch database afterwards")
    a = ap.parse_args()
    dump = Path(a.dump).resolve()
    if not re.fullmatch(r"[a-z_][a-z0-9_]{2,40}", a.scratch) or a.scratch in ("postgres", "kb_realdata"):
        sys.exit("pick a scratch database name (not postgres / kb_realdata)")
    expect = dump_counts(dump)
    print(f"dump: {len(expect)} tables with data, {sum(expect.values())} rows")
    with psycopg.connect(LOCAL.format(db="postgres"), autocommit=True) as c:
        c.execute(f'drop database if exists "{a.scratch}" with (force)')
        c.execute(f'create database "{a.scratch}"')
    with psycopg.connect(LOCAL.format(db=a.scratch), autocommit=True) as c:
        # what a Supabase database has before any project schema: the schemas the dump's objects refer to
        for s in ("extensions", "auth"):
            c.execute(f"create schema if not exists {s}")
        c.execute("create extension if not exists pg_trgm with schema extensions")
        c.execute("create extension if not exists pgcrypto with schema extensions")
        c.execute("create extension if not exists \"uuid-ossp\" with schema extensions")
        c.execute("create or replace function auth.uid() returns uuid language sql stable as $$ select null::uuid $$")
        c.execute("create or replace function auth.jwt() returns jsonb language sql stable as $$ select '{}'::jsonb $$")
        c.execute("create or replace function auth.role() returns text language sql stable as $$ select null::text $$")
    with dump.open("rb") as f:
        p = subprocess.run(["docker", "exec", "-i", CONTAINER, "psql", "-U", "postgres", "-d", a.scratch, "-q",
                            "-v", "ON_ERROR_STOP=0"], stdin=f, capture_output=True)
    errors = [l for l in p.stderr.decode("utf-8", "replace").splitlines() if "ERROR" in l]
    print(f"restore: psql exit {p.returncode}, {len(errors)} statement error(s)")
    for e in sorted(set(re.sub(r"^.*ERROR:\s*", "", x)[:120] for x in errors))[:15]:
        print("  error:", e)
    bad = 0
    with psycopg.connect(LOCAL.format(db=a.scratch)) as c:
        for t, n in sorted(expect.items()):
            try:
                got = c.execute(f"select count(*) from {t}").fetchone()[0]
            except psycopg.Error:
                c.rollback()
                got = None
            ok = got == n
            bad += not ok
            if not ok:
                print(f"  MISMATCH {t}: dump {n}, restored {got}")
    print(f"tables compared: {len(expect)}, identical: {len(expect) - bad}, rows: {sum(expect.values())}")
    if not a.keep:
        with psycopg.connect(LOCAL.format(db="postgres"), autocommit=True) as c:
            c.execute(f'drop database if exists "{a.scratch}" with (force)')
        print("scratch database dropped")
    print("RESTORE VERIFIED" if bad == 0 else "RESTORE NOT VERIFIED")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
