#!/usr/bin/env python3
"""Grant the KB `admin` role to the accounts named in ADMIN_EMAILS.

The ONLY way anyone becomes a KB admin without an existing admin granting it in
the app. Nobody is auto-admin: a signed-in IK profile with no membership row is
a viewer (migration 0023, kb.role()).

    ADMIN_EMAILS=a@interviewkickstart.com,b@interviewkickstart.com \
        python3 pipeline/kb_admins.py [--dry-run]

Matches on the PROFILE email (written from a verified Google token, domain-
checked by a constraint), so an address must have signed in once first; one
that has not is reported, never invented. Refuses a profile marked
is_shared_account (derived by migration 0014): an admin action must be
attributable to a person.

Runs through SUPABASE_DB_URL_SESSION as the table owner — an operator action,
like pipeline/grant_access.py.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.lib import db                                           # noqa: E402


def wanted() -> list[str]:
    raw = os.environ.get("ADMIN_EMAILS", "")
    return sorted({e.strip().lower() for e in raw.split(",") if e.strip()})


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    emails = wanted()
    if not emails:
        print("ADMIN_EMAILS is not set (comma-separated emails); nothing to do", file=sys.stderr)
        return 2
    with db.connect(db.SESSION) as conn, conn.cursor() as cur:
        missing, granted = [], []
        for email in emails:
            cur.execute("select user_id, is_shared_account from profiles where lower(email) = %s", (email,))
            row = cur.fetchone()
            if not row:
                missing.append(email)
                continue
            if row[1]:
                print(f"REFUSED {email}: profile is marked as a shared account")
                continue
            if not args.dry_run:
                cur.execute("select set_config('kb.actor_type', 'system', true)")
                cur.execute("insert into kb.memberships (user_id, role) values (%s, 'admin') "
                            "on conflict (user_id) do update set role = 'admin'", (row[0],))
            granted.append(email)
        if not args.dry_run:
            conn.commit()
    for e in granted:
        print(f"{'would grant' if args.dry_run else 'granted'} admin: {e}")
    for e in missing:
        print(f"NO PROFILE {e}: sign in once with Google first, then re-run")
    return 0 if not missing else 1


if __name__ == "__main__":
    sys.exit(main())
