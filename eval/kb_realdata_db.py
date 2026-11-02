#!/usr/bin/env python3
"""The LOCAL real-data copy: a separate database `kb_realdata` in the local
Supabase Postgres (127.0.0.1:54322), next to the demo's `postgres` database and
never touching it. LOCAL ONLY: refuses any non-loopback address. Reads the
dumps in backups/ (gitignored; real internal data) and prints counts only.

    python eval/kb_realdata_db.py create      # (re)create kb_realdata + bootstrap
    python eval/kb_realdata_db.py restore     # production schema, then data (counts checked)
    python eval/kb_realdata_db.py drift       # compare production's schema with migrations 0001-0021
    python eval/kb_realdata_db.py counts      # row count of every public table
    python eval/kb_realdata_db.py admin       # the local admin for the 8766 sign-in
    python eval/kb_realdata_db.py rebuild     # create + restore + migrate up + admin

Bootstrap (what a fresh database lacks compared with a Supabase project):
  - schema `extensions` with pg_trgm, pgcrypto, uuid-ossp (as Supabase installs them);
  - a minimal schema `auth`: auth.users (id, email, encrypted_password, metadata,
    timestamps) and auth.uid() / auth.role() / auth.jwt() / auth.email(), copied
    from the local stack's definitions. Roles (authenticated, anon, ...) and their
    settings are cluster-wide and already exist.
Production's public tables have no foreign key to auth.users, so no placeholder
auth users are needed for the restore; the local admin for 8766 is the only row
eval/kb_realdata_server.py adds there.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BACKUPS = REPO / "backups"
DB = "kb_realdata"
DRIFT_DB = "kb_drift_0021"
CONTAINER = os.environ.get("KB_LOCAL_DB_CONTAINER", "supabase_db_np-autopilot-test")
HOSTPORT = "127.0.0.1:54322"


def dsn(db: str) -> str:
    return f"postgresql://postgres:postgres@{HOSTPORT}/{db}"


def connect(db: str, autocommit=True):
    import psycopg
    d = dsn(db)
    if "127.0.0.1" not in d and "localhost" not in d:
        sys.exit("REFUSED: local only")
    return psycopg.connect(d, autocommit=autocommit)


BOOTSTRAP = r"""
create schema if not exists extensions;
create extension if not exists pg_trgm with schema extensions;
create extension if not exists pgcrypto with schema extensions;
create extension if not exists "uuid-ossp" with schema extensions;
grant usage on schema extensions to anon, authenticated, service_role;

create schema if not exists auth;
create table if not exists auth.users (
    id                 uuid primary key,
    email              text,
    encrypted_password text,
    aud                text default 'authenticated',
    role               text default 'authenticated',
    raw_app_meta_data  jsonb default '{}'::jsonb,
    raw_user_meta_data jsonb default '{}'::jsonb,
    email_confirmed_at timestamptz,
    created_at         timestamptz default now(),
    updated_at         timestamptz default now()
);
create or replace function auth.uid() returns uuid language sql stable as $$
  select coalesce(nullif(current_setting('request.jwt.claim.sub', true), ''),
                  (nullif(current_setting('request.jwt.claims', true), '')::jsonb ->> 'sub'))::uuid $$;
create or replace function auth.role() returns text language sql stable as $$
  select coalesce(nullif(current_setting('request.jwt.claim.role', true), ''),
                  (nullif(current_setting('request.jwt.claims', true), '')::jsonb ->> 'role'))::text $$;
create or replace function auth.jwt() returns jsonb language sql stable as $$
  select coalesce(nullif(current_setting('request.jwt.claim', true), ''),
                  nullif(current_setting('request.jwt.claims', true), ''))::jsonb $$;
create or replace function auth.email() returns text language sql stable as $$
  select coalesce(nullif(current_setting('request.jwt.claim.email', true), ''),
                  (nullif(current_setting('request.jwt.claims', true), '')::jsonb ->> 'email'))::text $$;
grant usage on schema auth to anon, authenticated, service_role;
grant execute on function auth.uid(), auth.role(), auth.jwt(), auth.email() to anon, authenticated, service_role;

-- Supabase's default privileges for objects `postgres` creates in public
-- (copied from the local stack): tables and sequences to service_role,
-- functions to everyone. Anything more comes from the migrations' own grants.
alter default privileges for role postgres in schema public grant all on tables to service_role;
alter default privileges for role postgres in schema public grant all on sequences to service_role;
alter default privileges for role postgres in schema public grant execute on functions to anon, authenticated, service_role;
"""

SUPABASE_PUBLIC = """
grant usage on schema public to anon, authenticated, service_role;
alter default privileges for role postgres in schema public grant all on tables to service_role;
alter default privileges for role postgres in schema public grant all on sequences to service_role;
alter default privileges for role postgres in schema public grant execute on functions to anon, authenticated, service_role;
"""


def create(db: str = DB) -> None:
    with connect("postgres") as c:
        c.execute(f'drop database if exists "{db}" with (force)')
        c.execute(f'create database "{db}"')
    with connect(db) as c:
        c.execute(BOOTSTRAP)
        c.execute("grant usage on schema public to anon, authenticated, service_role")
    print(f"created {db} and bootstrapped extensions + auth")


def psql_file(db: str, path: Path, pre: str = "", post: str = "") -> None:
    """Run a SQL file inside the local db container (its psql), ON_ERROR_STOP."""
    data = (pre + "\n").encode() + path.read_bytes() + ("\n" + post + "\n").encode()
    p = subprocess.run(["docker", "exec", "-i", CONTAINER, "psql", "-q", "-U", "postgres", "-d", db,
                        "-v", "ON_ERROR_STOP=1", "-X"], input=data, capture_output=True)
    # An error's DETAIL/CONTEXT can quote a failing row (real data): withheld.
    err = "\n".join("  [detail withheld: may quote row values]" if re.search(r"DETAIL|CONTEXT|Failing row|Key \(|COPY ", l) else l
                    for l in p.stderr.decode("utf-8", "replace").splitlines())
    if p.returncode != 0:
        # schema/data errors name objects, not values; still show only the first lines
        sys.exit(f"psql failed on {path.name} (exit {p.returncode}):\n" + "\n".join(err.splitlines()[:8]))
    noise = [l for l in err.splitlines() if l.strip() and "NOTICE" not in l]
    if noise:
        print("\n".join(noise[:8]))


EXPECTED = {"node_sources": 39414, "edges": 12189, "nodes": 8496, "node_layout": 3707, "files": 1524,
            "profiles": 7, "people": 20}


def dumped_counts() -> dict[str, int]:
    d = (BACKUPS / "prod_data.sql").read_text(encoding="utf-8")
    out = {}
    for m in re.finditer(r'^COPY public\.("?\w+"?) \([^)]*\) FROM stdin;\n(.*?)^\\\.\n', d, re.M | re.S):
        out[m.group(1).strip('"')] = m.group(2).count("\n")
    return out


def counts(db: str = DB) -> dict[str, int]:
    with connect(db) as c:
        tabs = [r[0] for r in c.execute("select tablename from pg_tables where schemaname = 'public' order by 1")]
        return {t: c.execute(f'select count(*) from public."{t}"').fetchone()[0] for t in tabs}


def build_reference() -> None:
    """Migrations 0001-0021 in a scratch database: the drift baseline, and the
    source of the grants the restored schema lacks (dumped --no-privileges)."""
    create(DRIFT_DB)
    env = dict(os.environ, SUPABASE_DB_URL_SESSION=dsn(DRIFT_DB))
    p = subprocess.run([sys.executable, str(REPO / "pipeline" / "migrate.py"), "up", "--to", "0021"],
                       env=env, capture_output=True, text=True)
    if p.returncode:
        sys.exit("migrate 0001-0021 into the reference database failed:\n" + (p.stdout + p.stderr)[-1200:])
    print("reference database: " + (p.stdout.strip().splitlines() or ["?"])[-1].strip())


def copy_grants() -> int:
    """Give every public table in kb_realdata exactly the privileges the
    migrations grant (read from the reference database)."""
    roles = ("anon", "authenticated", "service_role")
    with connect(DRIFT_DB) as r:
        grants = r.execute("""select table_name, grantee, string_agg(privilege_type, ', ')
                              from information_schema.table_privileges where table_schema = 'public'
                              and grantee = any(%s) group by 1, 2""", (list(roles),)).fetchall()
    n = 0
    with connect(DB) as c:
        tabs = {t for (t,) in c.execute("select tablename from pg_tables where schemaname = 'public'")}
        for t in tabs:
            c.execute(f'revoke all on public."{t}" from anon, authenticated, service_role')
        for t, who, privs in grants:
            if t in tabs:
                c.execute(f'grant {privs} on public."{t}" to {who}')
                n += 1
        c.execute("grant usage, select on all sequences in schema public to service_role")
    return n


def restore() -> None:
    schema, data = BACKUPS / "prod_schema.sql", BACKUPS / "prod_data.sql"
    if not schema.exists() or not data.exists():
        sys.exit("backups/prod_schema.sql and backups/prod_data.sql are needed (Step 0)")
    build_reference()
    # The dump creates schema public itself (pg_dump 15+ includes it).
    psql_file(DB, schema, pre="drop schema if exists public cascade;", post=SUPABASE_PUBLIC)
    print(f"schema restored; grants copied from migrations 0001-0021: {copy_grants()} table/role grants")
    # Faithful load: user triggers off during COPY (the service-only guards would
    # refuse rows, and derive_shared_account would recompute profiles before
    # shared_accounts is loaded), then back on. Foreign keys stay enforced.
    with connect(DB) as c:
        tabs = [r[0] for r in c.execute("select tablename from pg_tables where schemaname = 'public'")]
    off = "\n".join(f'alter table public."{t}" disable trigger user;' for t in tabs)
    on = "\n".join(f'alter table public."{t}" enable trigger user;' for t in tabs)
    psql_file(DB, data, pre=off, post=on)
    with connect(DB) as c:
        c.execute("analyze")
        disabled = c.execute("""select count(*) from pg_trigger t join pg_class c on c.oid = t.tgrelid
                                join pg_namespace n on n.oid = c.relnamespace
                                where n.nspname = 'public' and not t.tgisinternal and t.tgenabled = 'D'""").fetchone()[0]
    want, got = dumped_counts(), counts(DB)
    bad = {t: (want.get(t), got.get(t)) for t in set(want) | set(got) if want.get(t) != got.get(t)}
    bad |= {t: (n, got.get(t)) for t, n in EXPECTED.items() if got.get(t) != n}
    print(f"data restored; {len(got)} tables; user triggers left disabled: {disabled}")
    for t in sorted(got):
        print(f"  {t:<24}{got[t]:>8}" + ("" if t not in bad else "   MISMATCH vs dump " + str(bad[t])))
    if bad or disabled:
        sys.exit("RESTORE CHECK FAILED")
    print("RESTORE CHECK: every table's count equals the dump (and production's)")


# --------------------------------------------------------------------------- drift
CATALOG = {
    "columns": """select c.relname, a.attname, format_type(a.atttypid, a.atttypmod),
                         a.attnotnull, pg_get_expr(d.adbin, d.adrelid)
                  from pg_attribute a join pg_class c on c.oid = a.attrelid join pg_namespace n on n.oid = c.relnamespace
                  left join pg_attrdef d on d.adrelid = a.attrelid and d.adnum = a.attnum
                  where n.nspname = 'public' and c.relkind in ('r','p') and a.attnum > 0 and not a.attisdropped""",
    "constraints": """select c.relname, k.conname, pg_get_constraintdef(k.oid) from pg_constraint k
                      join pg_class c on c.oid = k.conrelid join pg_namespace n on n.oid = c.relnamespace
                      where n.nspname = 'public'""",
    "indexes": """select tablename, indexname, indexdef from pg_indexes where schemaname = 'public'""",
    "functions": """select p.proname, pg_get_function_identity_arguments(p.oid), md5(pg_get_functiondef(p.oid))
                    from pg_proc p join pg_namespace n on n.oid = p.pronamespace where n.nspname = 'public'""",
    "triggers": """select c.relname, t.tgname, pg_get_triggerdef(t.oid) from pg_trigger t join pg_class c on c.oid = t.tgrelid
                   join pg_namespace n on n.oid = c.relnamespace where n.nspname = 'public' and not t.tgisinternal""",
    "policies": """select tablename, policyname, cmd, roles::text, qual, with_check from pg_policies where schemaname = 'public'""",
    "rls": """select relname, relrowsecurity, relforcerowsecurity from pg_class c join pg_namespace n on n.oid = c.relnamespace
              where n.nspname = 'public' and relkind in ('r','p')""",
}


def snapshot(db: str) -> dict[str, set]:
    with connect(db) as c:
        return {k: {tuple(map(str, r)) for r in c.execute(q).fetchall()} for k, q in CATALOG.items()}


def drift() -> None:
    """Compare production's public schema (kb_realdata, BEFORE 0022+) with
    migrations 0001-0021 (the reference database `restore` built)."""
    with connect("postgres") as c:
        if not c.execute("select 1 from pg_database where datname = %s", (DRIFT_DB,)).fetchone():
            build_reference()
    prod, mig = snapshot(DB), snapshot(DRIFT_DB)
    total = 0
    for k in CATALOG:
        only_prod, only_mig = sorted(prod[k] - mig[k]), sorted(mig[k] - prod[k])
        if only_prod or only_mig:
            print(f"\n[{k}]")
            for r in only_prod:
                print("  production only:", " | ".join(x[:140] for x in r))
            for r in only_mig:
                print("  migrations only:", " | ".join(x[:140] for x in r))
            total += len(only_prod) + len(only_mig)
    print(f"\nDRIFT: {total} difference(s)")


# --------------------------------------------------------------------------- local admin
import uuid as _uuid                                                     # noqa: E402

ADMIN_EMAIL = "realdata-admin@interviewkickstart.com"
ADMIN_ID = str(_uuid.uuid5(_uuid.NAMESPACE_URL, "np-kb-realdata/admin"))
#: Local only, like the demo's: the 8766 server binds 127.0.0.1 and refuses a
#: non-loopback database. Override with KB_REALDATA_PASSWORD.
ADMIN_PASSWORD = os.environ.get("KB_REALDATA_PASSWORD", "ik-realdata-local")


def admin() -> str:
    """The one sign-in account of the real-data copy: a local auth.users row
    (bcrypt, pgcrypto), a profile, and the KB admin role. No real person's
    account is created or needed."""
    with connect(DB) as c:
        c.execute("""insert into auth.users (id, email, encrypted_password, email_confirmed_at)
                     values (%s, %s, extensions.crypt(%s, extensions.gen_salt('bf')), now())
                     on conflict (id) do update set encrypted_password = excluded.encrypted_password""",
                  (ADMIN_ID, ADMIN_EMAIL, ADMIN_PASSWORD))
        c.execute("""insert into public.profiles (user_id, email, email_domain, role)
                     values (%s, %s, 'interviewkickstart.com', 'member') on conflict (user_id) do nothing""",
                  (ADMIN_ID, ADMIN_EMAIL))
        c.execute("""insert into kb.memberships (user_id, role) values (%s, 'admin')
                     on conflict (user_id) do update set role = 'admin', archived_at = null, status = 'active'""", (ADMIN_ID,))
    print(f"local admin ready: {ADMIN_EMAIL} (KB admin; site role member)")
    return ADMIN_ID


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    sys.path.insert(0, str(REPO))
    if cmd == "create":
        create()
    elif cmd == "restore":
        restore()
    elif cmd == "drift":
        drift()
    elif cmd == "admin":
        admin()
    elif cmd == "rebuild":
        # The whole rehearsal from the dumps: database, production schema + data,
        # KB migrations 0022+ on top, the local admin. (The import is separate:
        # pipeline/kb_import_projection.py preview/apply.)
        create()
        restore()
        p = subprocess.run([sys.executable, str(REPO / "pipeline" / "migrate.py"), "up"],
                           env=dict(os.environ, SUPABASE_DB_URL_SESSION=dsn(DB)), capture_output=True, text=True)
        print("migrations: " + (p.stdout.strip().splitlines() or ["?"])[-1].strip())
        if p.returncode:
            sys.exit((p.stdout + p.stderr)[-1500:])
        admin()
    elif cmd == "drop-reference":
        with connect("postgres") as c:
            c.execute(f'drop database if exists "{DRIFT_DB}" with (force)')
    elif cmd == "counts":
        for t, n in counts().items():
            print(f"  {t:<24}{n:>8}")
    else:
        sys.exit(__doc__)
