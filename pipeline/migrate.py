#!/usr/bin/env python3
"""D3 — migration runner. Numbered SQL files with an explicit down for each.

WHY THIS AND NOT ALEMBIC / SQITCH / THE SUPABASE CLI, in three lines:

  1. There is no ORM here. Alembic's value is autogenerating diffs from
     SQLAlchemy models, and we have none — it would be a dependency whose main
     feature we never use, producing migrations nobody reviewed.
  2. Every down migration is hand-written and reviewable, which is the point:
     this project's rule is that a threshold may rank or warn but must not
     silently exclude, and the same instinct says a rollback must be a file
     someone read, not a guess a tool made.
  3. The Supabase CLI would work, but it links the repo to a hosted project and
     owns the migration table. Plain SQL over psycopg keeps the database
     reachable by the same connection string everything else uses, and keeps
     `docs/DEPLOYMENT.md` to "set one env var".

Usage:
    python3 pipeline/migrate.py status
    python3 pipeline/migrate.py up            # apply all pending
    python3 pipeline/migrate.py up --to 0002
    python3 pipeline/migrate.py down          # roll back the newest applied
    python3 pipeline/migrate.py down --to 0001

Connects through SUPABASE_DB_URL_SESSION — the SESSION pooler, deliberately.
DDL under the transaction pooler cannot rely on session state, and migrations
are the one workload that is neither serverless nor latency-sensitive.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.lib.paths import REPO_ROOT                              # noqa: E402

MIGRATIONS = REPO_ROOT / "db" / "migrations"
TRACKING = "np_schema_migrations"


def _connect():
    try:
        import psycopg
    except ImportError:
        sys.exit("psycopg is not installed — pip install -r requirements.txt")
    url = os.environ.get("SUPABASE_DB_URL_SESSION")
    if not url:
        sys.exit(
            "SUPABASE_DB_URL_SESSION is not set.\n"
            "  set -a && . ~/.config/np-autopilot/env && set +a\n"
            "Never the direct db.<ref>.supabase.co:5432 connection: it is "
            "IPv6-only on this project, so it works on a laptop and fails on "
            "Vercel — the worst possible failure distribution."
        )
    return psycopg.connect(url, connect_timeout=30)


def discover() -> list[tuple[str, Path, Path]]:
    """(version, up_path, down_path) sorted by version. Every up needs a down."""
    ups = sorted(MIGRATIONS.glob("*.up.sql"))
    out = []
    for up in ups:
        m = re.match(r"^(\d{4})_", up.name)
        if not m:
            sys.exit(f"migration {up.name} does not start with a 4-digit version")
        down = up.with_name(up.name.replace(".up.sql", ".down.sql"))
        if not down.exists():
            sys.exit(
                f"{up.name} has no matching .down.sql. Every migration ships its "
                "rollback — an irreversible migration is a decision, and it has "
                "to be written down as one."
            )
        out.append((m.group(1), up, down))
    return out


def checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def ensure_tracking(cur) -> None:
    """Bootstrap. Not itself a migration — nothing could record it."""
    cur.execute(f"""
        create table if not exists {TRACKING} (
            version     text primary key,
            name        text not null,
            checksum    text not null,
            applied_at  timestamptz not null default now()
        )
    """)
    # The tracking table holds no application data, but it is still a table in a
    # database where RLS-on-every-table is the rule, so it gets the same
    # treatment rather than an exception nobody remembers making.
    cur.execute(f"alter table {TRACKING} enable row level security")


def applied(cur) -> dict[str, str]:
    cur.execute(f"select version, checksum from {TRACKING} order by version")
    return dict(cur.fetchall())


def cmd_status(conn) -> int:
    with conn.cursor() as cur:
        ensure_tracking(cur)
        conn.commit()
        done = applied(cur)
    print(f"{'ver':<6} {'state':<10} {'checksum':<18} name")
    drift = 0
    for version, up, _ in discover():
        cs = checksum(up)
        if version in done:
            state = "applied" if done[version] == cs else "CHANGED"
            drift += state == "CHANGED"
        else:
            state = "pending"
        print(f"{version:<6} {state:<10} {cs:<18} {up.name}")
    if drift:
        print(f"\n  {drift} applied migration(s) edited since they ran. The "
              "database no longer matches the file. Write a new migration "
              "instead of editing history.")
    return 1 if drift else 0


def _run_sql(conn, path: Path) -> None:
    sql = path.read_text(encoding="utf-8")
    if not sql.strip() or all(l.strip().startswith("--") or not l.strip()
                              for l in sql.splitlines()):
        return                                   # an empty migration is valid
    with conn.cursor() as cur:
        cur.execute(sql)


def cmd_up(conn, to: str | None) -> int:
    with conn.cursor() as cur:
        ensure_tracking(cur)
    conn.commit()
    with conn.cursor() as cur:
        done = applied(cur)
    ran = 0
    for version, up, _ in discover():
        if version in done:
            continue
        if to and version > to:
            break
        print(f"  up   {version}  {up.name}")
        try:
            _run_sql(conn, up)
            with conn.cursor() as cur:
                cur.execute(
                    f"insert into {TRACKING}(version,name,checksum) values (%s,%s,%s)",
                    (version, up.name, checksum(up)))
            conn.commit()
        except Exception as exc:
            conn.rollback()
            print(f"  FAILED {version}: {type(exc).__name__}: {exc}")
            print("  rolled back; nothing from this migration was applied")
            return 1
        ran += 1
    print(f"  {ran} migration(s) applied" if ran else "  nothing pending")
    return 0


def cmd_down(conn, to: str | None) -> int:
    with conn.cursor() as cur:
        ensure_tracking(cur)
    conn.commit()
    with conn.cursor() as cur:
        done = applied(cur)
    ran = 0
    for version, _, down in reversed(discover()):
        if version not in done:
            continue
        if to and version <= to:
            break
        print(f"  down {version}  {down.name}")
        try:
            _run_sql(conn, down)
            with conn.cursor() as cur:
                cur.execute(f"delete from {TRACKING} where version = %s", (version,))
            conn.commit()
        except Exception as exc:
            conn.rollback()
            print(f"  FAILED {version}: {type(exc).__name__}: {exc}")
            return 1
        ran += 1
        if to is None:
            break                                # default: one step
    print(f"  {ran} migration(s) rolled back" if ran else "  nothing to roll back")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["status", "up", "down"])
    ap.add_argument("--to", default=None, help="stop at this version (inclusive for up)")
    args = ap.parse_args()
    with _connect() as conn:
        if args.command == "status":
            return cmd_status(conn)
        if args.command == "up":
            return cmd_up(conn, args.to)
        return cmd_down(conn, args.to)


if __name__ == "__main__":
    raise SystemExit(main())
