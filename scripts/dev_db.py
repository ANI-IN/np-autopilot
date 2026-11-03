#!/usr/bin/env python3
"""The DEV Supabase database (run 5, Part 6). Never production.

Reads DEV_SUPABASE_DB_URL and DEV_SUPABASE_URL (environment, or the repo's
.env). Refuses unless the database's project ref differs from production's
and agrees with DEV_SUPABASE_URL. Never prints the URL, a host, a password or
an IP: every message is scrubbed. Counts and ids only.

    python scripts/dev_db.py check              # the refs (equal / not production), server version
    python scripts/dev_db.py status             # migrations applied, row counts, RLS on every kb table
    python scripts/dev_db.py backup             # pg_dump (public + kb) -> backups/dev_backup_<UTC>.sql
    python scripts/dev_db.py migrate            # pipeline/migrate.py up (0001 -> latest)
    python scripts/dev_db.py rollback-test      # down to 0029, then up again (run 5's migrations; empty kb state only)
    python scripts/dev_db.py load-old-tables    # the projection tables from backups/prod_data.sql (no user tables)
    python scripts/dev_db.py import             # first import as the operator (no admin yet), then the legacy step
    python scripts/dev_db.py sync               # one sync run (operator)
    python scripts/dev_db.py verify             # counts vs kb_realdata (:8766), RLS, migrations, last sync
    python scripts/dev_db.py legacy-plan        # run 6 R3: what the permanent legacy deletion would remove
    python scripts/dev_db.py legacy-delete      # run 6 R3: export to backups/, then delete (owner-approved)
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlparse

REPO = Path(__file__).resolve().parent.parent
BACKUPS = REPO / "backups"
sys.path[:0] = [str(REPO), str(REPO / "web")]
from pipeline.lib import db                                             # noqa: E402

LOCAL_REALDATA = "postgresql://postgres:postgres@127.0.0.1:54322/kb_realdata"
#: The old tables NP Autopilot reads (the projection). User and account tables
#: (profiles, shared_accounts, auth_hook_refusals, curation_audit) and the
#: migration ledger are NOT copied.
OLD_TABLES = ("node_types", "edge_rels", "nodes", "edges", "files", "node_layout", "node_sources", "people",
              "people_aliases", "domain_aliases", "workflow_owners", "curation_notes", "projection_meta")


def _env() -> dict:
    vals = {k: os.environ.get(k, "") for k in ("DEV_SUPABASE_DB_URL", "DEV_SUPABASE_URL")}
    envf = REPO / ".env"
    if not all(vals.values()) and envf.exists():
        for line in envf.read_text(encoding="utf-8").splitlines():
            k, _, v = line.partition("=")
            if k.strip() in vals and not vals[k.strip()]:
                vals[k.strip()] = v.strip().strip('"').strip("'")
    if not all(vals.values()):
        sys.exit("DEV_SUPABASE_DB_URL and DEV_SUPABASE_URL are needed (environment or .env)")
    return vals


def _ref_of_db(url: str) -> str:
    p = urlparse(url)
    user, host = unquote(p.username or ""), (p.hostname or "").lower()
    if user.startswith("postgres.") and host.endswith(".pooler.supabase.com"):
        return user.split(".", 1)[1]
    m = re.match(r"^db\.([a-z0-9]{20})\.supabase\.co$", host)
    return m.group(1) if m else ""


def _ref_of_api(url: str) -> str:
    m = re.match(r"^([a-z0-9]{20})\.supabase\.co$", (urlparse(url).hostname or "").lower())
    return m.group(1) if m else ""


ENV = _env()
DEV = ENV["DEV_SUPABASE_DB_URL"]
_SECRETS = [x for x in {DEV, unquote(urlparse(DEV).password or ""), urlparse(DEV).hostname or "", unquote(urlparse(DEV).username or ""),
                        _ref_of_db(DEV), ENV["DEV_SUPABASE_URL"], urlparse(ENV["DEV_SUPABASE_URL"]).hostname or ""} if x and len(x) > 3]


def scrub(text: str) -> str:
    for s in sorted(_SECRETS, key=len, reverse=True):
        text = text.replace(s, "<dev>")
    text = re.sub(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", "<ip>", text)
    text = re.sub(r"\b[0-9A-Fa-f]{0,4}(?::[0-9A-Fa-f]{0,4}){2,7}\b",
                  lambda m: "<ip>" if "::" in m.group(0) or m.group(0).count(":") >= 4 else m.group(0), text)
    text = re.sub(r"[A-Za-z0-9.-]+\.supabase\.(?:com|co)\b", "<host>", text)
    return text


def guard() -> str:
    ref, api = _ref_of_db(DEV), _ref_of_api(ENV["DEV_SUPABASE_URL"])
    if not ref or not api:
        sys.exit("cannot read the dev project ref from DEV_SUPABASE_DB_URL / DEV_SUPABASE_URL")
    if db.PROD_PROJECT_REF in (ref, api) or db.PROD_PROJECT_REF in DEV:
        sys.exit("REFUSED: that is the production project")
    if ref != api:
        sys.exit("REFUSED: DEV_SUPABASE_DB_URL and DEV_SUPABASE_URL name different projects")
    return ref


def connect(**kw):
    import psycopg
    guard()
    try:
        return psycopg.connect(DEV, connect_timeout=30, prepare_threshold=None, **kw)
    except Exception as exc:                                           # noqa: BLE001
        sys.exit("cannot connect to the dev database: " + scrub(f"{type(exc).__name__}: {exc}").splitlines()[0])


def run_child(args: list[str], extra_env: dict | None = None) -> int:
    """A repo command against dev, its output scrubbed."""
    guard()
    env = dict(os.environ, SUPABASE_DB_URL_SESSION=DEV, **(extra_env or {}))
    p = subprocess.run([sys.executable, *args], cwd=REPO, env=env, capture_output=True, text=True)
    for line in (p.stdout + p.stderr).splitlines():
        if line.lstrip().startswith(("DETAIL:", "CONTEXT:")):      # may quote row values
            continue
        print("  " + scrub(line))
    return p.returncode


# ---------------------------------------------------------------- commands
def cmd_check() -> int:
    guard()
    with connect() as c:
        v = c.execute("select current_setting('server_version_num')::int / 10000").fetchone()[0]
    print(f"dev ref agrees with DEV_SUPABASE_URL: yes; production: no; Postgres {v}")
    return 0


def _counts(c, kb_exists: bool) -> dict:
    q = lambda sql: c.execute(sql).fetchone()[0]                         # noqa: E731
    out = {}
    for t in ("nodes", "edges", "node_sources", "people"):
        out["public." + t] = q(f"select count(*) from public.{t}") if q(f"select to_regclass('public.{t}') is not null") else None
    if kb_exists:
        out.update({"kb.nodes live": q("select count(*) from kb.nodes where archived_at is null"),
                    "kb.nodes current": q("select count(*) from kb.nodes where archived_at is null and not is_legacy")
                    if q("select exists (select 1 from information_schema.columns where table_schema='kb' and table_name='nodes' and column_name='is_legacy')") else None,
                    "kb.edges live": q("select count(*) from kb.edges where archived_at is null"),
                    "kb.resources": q("select count(*) from kb.resources"),
                    "kb.node_resources live": q("select count(*) from kb.node_resources where archived_at is null")})
    return out


def cmd_status() -> int:
    with connect() as c:
        mig = [r[0] for r in c.execute("select version from public.np_schema_migrations order by 1").fetchall()] \
            if c.execute("select to_regclass('public.np_schema_migrations') is not null").fetchone()[0] else []
        kb = bool(c.execute("select to_regnamespace('kb') is not null").fetchone()[0])
        rls = c.execute("""select c.relname, c.relrowsecurity from pg_class c join pg_namespace n on n.oid = c.relnamespace
                           where n.nspname = 'kb' and c.relkind = 'r' order by 1""").fetchall() if kb else []
        print("migrations applied:", (mig[0] + " .. " + mig[-1] + f" ({len(mig)})") if mig else "none")
        print("counts:", json.dumps(_counts(c, kb)))
        off = [t for t, on in rls if not on]
        print(f"kb tables: {len(rls)}; RLS off on: {off or 'none'}")
        if kb and c.execute("select to_regclass('kb.sync_runs') is not null").fetchone()[0]:
            r = c.execute("select id, trigger, status, conflicts from kb.sync_runs order by id desc limit 1").fetchone()
            print("last sync run:", r and {"id": r[0], "trigger": r[1], "status": r[2], "conflicts": r[3]})
    return 0


def cmd_backup() -> int:
    guard()
    BACKUPS.mkdir(exist_ok=True)
    name = "dev_backup_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + ".sql"
    env = dict(os.environ, KB_DEV_DUMP_URL=DEV)
    cmd = ["docker", "run", "--rm", "-e", "KB_DEV_DUMP_URL", "-v", f"{BACKUPS}:/out", "postgres:17",
           "sh", "-c", f'pg_dump "$KB_DEV_DUMP_URL" --no-owner --no-privileges -n public -n kb -f /out/{name}']
    p = subprocess.run(cmd, env=env, capture_output=True, text=True)
    if p.returncode != 0:
        print(scrub(p.stderr)[-800:])
        return 1
    f = BACKUPS / name
    txt = f.read_text(encoding="utf-8", errors="replace")
    print(f"backup: backups/{name} ({f.stat().st_size} bytes, {txt.count(chr(10) + 'COPY ')} tables with data)")
    return 0


def cmd_migrate() -> int:
    return run_child(["pipeline/migrate.py", "up"])


def cmd_rollback_test() -> int:
    """Run 5's migrations (0030, 0031) down and up again. 0030's down refuses
    once sync / legacy / owner state exists, so this runs before the import."""
    rc = run_child(["pipeline/migrate.py", "down", "--to", "0029"])
    if rc:
        return rc
    with connect() as c:
        gone = not c.execute("select to_regclass('kb.sync_map') is not null").fetchone()[0]
    print("after down: kb.sync_map " + ("gone" if gone else "STILL THERE"))
    rc = run_child(["pipeline/migrate.py", "up"])
    with connect() as c:
        back = c.execute("select to_regclass('kb.sync_map') is not null and to_regprocedure('kb.sync_schedule_install(text,text)') is not null").fetchone()[0]
    print("after up: run-5 objects " + ("back" if back else "MISSING"))
    return rc or (0 if gone and back else 1)


def _copy_blocks(path: Path, tables: tuple[str, ...]):
    """Yield (table, column list, rows-as-text) from a plain pg_dump data file."""
    want = {f"public.{t}": t for t in tables}
    cur, cols, buf = None, None, []
    with path.open(encoding="utf-8") as f:
        for line in f:
            if cur is None:
                m = re.match(r"^COPY (public\.\w+) \((.*)\) FROM stdin;$", line.rstrip("\n"))
                if m and m.group(1) in want:
                    cur, cols, buf = want[m.group(1)], m.group(2), []
                continue
            if line.rstrip("\n") == "\\.":
                yield cur, cols, "".join(buf)
                cur = None
                continue
            buf.append(line)


def cmd_load_old_tables() -> int:
    data = BACKUPS / "prod_data.sql"
    if not data.exists():
        sys.exit("backups/prod_data.sql is needed")
    blocks = {t: (cols, rows) for t, cols, rows in _copy_blocks(data, OLD_TABLES)}
    missing = [t for t in OLD_TABLES if t not in blocks]
    with connect() as c:
        with c.transaction():
            for t in OLD_TABLES:
                c.execute(f'alter table public."{t}" disable trigger user')
            c.execute("truncate " + ", ".join(f'public."{t}"' for t in OLD_TABLES) + " cascade")
            for t in OLD_TABLES:
                if t not in blocks:
                    continue
                cols, rows = blocks[t]
                with c.cursor().copy(f'copy public."{t}" ({cols}) from stdin') as cp:
                    cp.write(rows)
            for t in OLD_TABLES:
                c.execute(f'alter table public."{t}" enable trigger user')
        got = {t: c.execute(f'select count(*) from public."{t}"').fetchone()[0] for t in OLD_TABLES}
        want = {t: blocks[t][1].count("\n") if t in blocks else 0 for t in OLD_TABLES}
        off = c.execute("""select count(*) from pg_trigger t join pg_class r on r.oid = t.tgrelid join pg_namespace n on n.oid = r.relnamespace
                           where n.nspname = 'public' and not t.tgisinternal and t.tgenabled = 'D'""").fetchone()[0]
    bad = {t: (got[t], want[t]) for t in OLD_TABLES if got[t] != want[t]}
    print(f"loaded {len(OLD_TABLES) - len(missing)} tables, {sum(got.values())} rows; not in the dump: {missing or 'none'}; "
          f"counts equal the dump: {'yes' if not bad else bad}; user triggers left disabled: {off}")
    return 1 if bad or off else 0


def cmd_import() -> int:
    BACKUPS.mkdir(exist_ok=True)
    rc = run_child(["pipeline/kb_import_projection.py", "apply", "--operator", "--report", str(BACKUPS / "dev-import.json")])
    if rc:
        return rc
    return run_child(["pipeline/kb_legacy.py", "archive"])


def cmd_sync() -> int:
    return run_child(["pipeline/kb_import_projection.py", "apply", "--operator", "--report", str(BACKUPS / "dev-sync.json")])


def cmd_verify() -> int:
    import psycopg
    with connect() as c:
        dev = _counts(c, True)
        rls = c.execute("""select count(*), count(*) filter (where not c.relrowsecurity) from pg_class c
                           join pg_namespace n on n.oid = c.relnamespace where n.nspname = 'kb' and c.relkind = 'r'""").fetchone()
        mig = c.execute("select max(version), count(*) from public.np_schema_migrations").fetchone()
        last = c.execute("select trigger, status, conflicts from kb.sync_runs order by id desc limit 1").fetchone()
        dev_parity = _parity(c)
    with psycopg.connect(LOCAL_REALDATA) as c:
        loc = _counts(c, True)
        loc_parity = _parity(c)
    same = {k: dev[k] == loc[k] for k in dev}
    print("dev vs local real-data copy:", json.dumps({k: [dev[k], loc[k]] for k in dev}))
    print("equal:", all(same.values()), "| parity numbers equal:", dev_parity == loc_parity, json.dumps(dev_parity))
    print(f"RLS: {rls[0]} kb tables, {rls[1]} without RLS | migrations: latest {mig[0]} ({mig[1]} applied) | last sync: {last}")
    return 0 if all(same.values()) and dev_parity == loc_parity and rls[1] == 0 and last and last[1] == "ok" else 1


def _parity(c) -> dict:
    """The numbers docs/PARITY_REPORT.md checks against NP Autopilot."""
    q = lambda sql: c.execute(sql).fetchone()[0]                         # noqa: E731
    by = lambda typ, leg: q(f"""select count(*) from kb.nodes n join kb.node_types t on t.id = n.type_id
                                where t.key = '{typ}' and n.is_legacy = {leg}""")       # noqa: E731
    roles = dict(c.execute("""select e.props->>'role', count(*) from kb.edges e join kb.edge_types et on et.id = e.edge_type_id
                              where et.key = 'teaches' and e.props ? 'role' group by 1""").fetchall())
    return {"domains current/legacy": [by("domain", "false"), by("domain", "true")],
            "modules current/legacy": [by("module", "false"), by("module", "true")],
            "instructors current/legacy": [by("instructor", "false"), by("instructor", "true")],
            "roles": {k: roles.get(k, 0) for k in ("primary", "backup_1", "backup_2", "backup_3")},
            "archived by the legacy step": q("select count(*) from kb.legacy_archive")}


def cmd_legacy_plan() -> int:
    return run_child(["pipeline/kb_legacy_delete.py", "plan"])


def cmd_legacy_delete() -> int:
    """Run 6 R3 (owner-approved): export to backups/, then the permanent deletion."""
    return run_child(["pipeline/kb_legacy_delete.py", "delete"])


COMMANDS = {"check": cmd_check, "status": cmd_status, "backup": cmd_backup, "migrate": cmd_migrate,
            "rollback-test": cmd_rollback_test, "load-old-tables": cmd_load_old_tables, "import": cmd_import,
            "sync": cmd_sync, "verify": cmd_verify, "legacy-plan": cmd_legacy_plan, "legacy-delete": cmd_legacy_delete}

if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in COMMANDS:
        sys.exit(__doc__)
    try:
        sys.exit(COMMANDS[sys.argv[1]]())
    except SystemExit:
        raise
    except Exception as exc:                                           # noqa: BLE001
        sys.exit("failed: " + scrub(f"{type(exc).__name__}: {exc}").splitlines()[0])
