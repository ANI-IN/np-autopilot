"""Write canaries for the production_only read-only guard (tests/db_guard.py).

HARMLESS BY CONSTRUCTION even if one is NOT refused: every
statement touches zero rows (WHERE false) or runs inside a transaction that is
always rolled back, with a 1 s lock timeout. A canary PASSES when refused."""
import os, sys, psycopg
#: The four that must be refused anywhere, production included. Canary 5 is a
#: KNOWN GAP (a session setting cannot refuse SET TRANSACTION READ WRITE) and
#: is never run against production: it would execute a write there and prove
#: nothing new (owner decision, 2026-09-30).
PRODUCTION_SAFE = ("INSERT", "UPDATE", "DELETE", "TRUNCATE")


def canaries(connect, only=None):
    T = "curation_notes"
    cases = [
        ("INSERT", [f"insert into {T} (scope,row_key,note,position,author_email,created_at,updated_at,version) select scope,row_key,note,position,author_email,created_at,updated_at,version from {T} where false"]),
        ("UPDATE", [f"update {T} set note = note where false"]),
        ("DELETE", [f"delete from {T} where false"]),
        ("TRUNCATE", [f"truncate {T}"]),
        ("SET TRANSACTION READ WRITE, then INSERT", ["set transaction read write",
                                                     f"insert into {T} (scope,row_key,note,position,author_email,created_at,updated_at,version) select scope,row_key,note,position,author_email,created_at,updated_at,version from {T} where false"]),
    ]
    if only is not None:
        unknown = set(only) - {n for n, _ in cases}
        if unknown:
            raise SystemExit(f"unknown canaries: {sorted(unknown)}")
        cases = [c for c in cases if c[0] in only]
    out = []
    for name, stmts in cases:
        conn = connect()
        try:
            with conn.cursor() as cur:
                cur.execute("set local lock_timeout = '1s'") if not conn.autocommit else None
                try:
                    for s in stmts:
                        cur.execute(s)
                    out.append((name, False, "EXECUTED (not refused) — rolled back"))
                except (psycopg.errors.ReadOnlySqlTransaction, psycopg.errors.InsufficientPrivilege) as e:
                    out.append((name, True, f"refused: {type(e).__name__}: {str(e).splitlines()[0][:70]}"))
                except psycopg.Error as e:
                    # ANY OTHER error means the canary is broken, not that the
                    # write was refused (the first version hit an identity column).
                    raise SystemExit(f"CANARY INVALID ({name}): {type(e).__name__}: {e}")
        finally:
            conn.rollback(); conn.close()
    return out
if __name__ == "__main__":
    sys.path.insert(0, os.getcwd())
    from pipeline.lib import db
    # As a script it runs the PRODUCTION-SAFE four only — the form used
    # against production. Canary 5 runs only inside the local pooler tests.
    res = canaries(lambda: db.connect(db.SESSION), only=PRODUCTION_SAFE)
    for name, ok, msg in res:
        print(f"  {'REFUSED ' if ok else 'NOT REFUSED'}  {name:<42} {msg}")
    print("ALL REFUSED" if all(r[1] for r in res) else "SOME NOT REFUSED")
