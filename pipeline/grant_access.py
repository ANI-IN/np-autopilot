#!/usr/bin/env python3
"""Grant, list and revoke access. The deliberate act that a session is not.

docs/AUTH.md: *"layer 3 permits an account to exist; a profile is what gives it
data."* This is that step, and it is a script run by an operator rather than an
HTTP route, because there is no self-service path into a role — an IK employee
who signs in successfully still reads nothing until someone runs this.

It connects as the OWNER over the session pooler. `profiles` has a self-select
policy and no insert policy at all, so this cannot be done over the web app even
by an admin, which is the intended shape: granting access is not a curation
write and does not belong on the same surface.

    python3 pipeline/grant_access.py list
    python3 pipeline/grant_access.py grant someone@interviewkickstart.com
    python3 pipeline/grant_access.py grant someone@… --role recruiting
    python3 pipeline/grant_access.py revoke someone@interviewkickstart.com
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.lib import db                                           # noqa: E402

ALLOWED_HD = os.environ.get("NP_ALLOWED_HD", "interviewkickstart.com")
ROLES = ("member", "recruiting", "admin")


def _shared_accounts() -> set[str]:
    return {s.strip().lower()
            for s in os.environ.get("NP_SHARED_ACCOUNTS", "").split(",") if s.strip()}


def _lookup(cur, email: str):
    """Find the auth.users row, and the hd the PROVIDER supplied at signup.

    `auth.identities.identity_data` rather than `auth.users.raw_user_meta_data`:
    user_metadata is writable by the user through the auth API, so an `hd` read
    from it is an attacker-controlled string. identity_data is what GoTrue
    recorded from Google and is not user-writable.

    Even so, this is corroboration, not the proof. The proof is that the row
    exists at all: /api/session verified the `hd` on a signed Google token
    before GoTrue was ever contacted, and the migration-0007 hook refuses to
    create a user without it.
    """
    cur.execute("""
        select u.id, u.email, i.identity_data ->> 'hd' as hd,
               u.created_at, u.last_sign_in_at
        from auth.users u
        left join auth.identities i
               on i.user_id = u.id and i.provider = 'google'
        where lower(u.email) = lower(%s)
    """, (email,))
    return cur.fetchone()


def cmd_list(_args) -> int:
    with db.connect(db.SESSION) as conn, conn.cursor() as cur:
        cur.execute("""
            select p.email, p.role, p.is_shared_account, p.email_domain,
                   p.created_at, u.last_sign_in_at
            from profiles p left join auth.users u on u.id = p.user_id
            order by p.role, p.email
        """)
        rows = cur.fetchall()
        cur.execute("""
            select u.email, u.created_at from auth.users u
            where not exists (select 1 from profiles p where p.user_id = u.id)
            order by u.created_at
        """)
        unprovisioned = cur.fetchall()

    print(f"{'EMAIL':<46} {'ROLE':<11} SHARED  LAST SIGN-IN")
    for email, role, shared, _dom, _c, last in rows:
        print(f"{email:<46} {role:<11} {'yes' if shared else ' - ':<6}  "
              f"{last.strftime('%Y-%m-%d %H:%M') if last else 'never'}")
    if not rows:
        print("  (no profiles — nobody can read anything)")

    if unprovisioned:
        # Not a warning. This is the correct resting state for someone who has
        # signed in and not yet been granted access, and naming it stops it
        # being mistaken for a broken login.
        print(f"\nSIGNED IN, NO PROFILE ({len(unprovisioned)}) — these accounts "
              "exist and read nothing:")
        for email, created in unprovisioned:
            print(f"  {email:<46} first seen {created.strftime('%Y-%m-%d')}")
    return 0


def cmd_grant(args) -> int:
    email = args.email.strip().lower()
    role = args.role
    if role not in ROLES:
        print(f"role must be one of {ROLES}", file=sys.stderr)
        return 2

    shared = email.split("@", 1)[0] in _shared_accounts()
    if shared and role != "member":
        # The database CHECK from 0008 would refuse this anyway. Saying it here
        # means the operator learns WHY rather than reading a constraint name.
        print(f"REFUSED: {email} is a configured shared account. A shared "
              f"account cannot hold {role!r} — the audit log would name an "
              "account, not a person, and `recruiting` reads named hiring "
              "outcomes about external people.", file=sys.stderr)
        return 1

    with db.connect(db.SESSION) as conn, conn.cursor() as cur:
        found = _lookup(cur, email)
        if not found:
            print(f"No auth.users row for {email}.\n"
                  "  They must sign in ONCE first. That is the intended order: "
                  "signing in proves the Workspace identity (and invokes the\n"
                  "  migration-0007 hook); this grants the access. "
                  "`grant_access.py list` shows who has signed in and is "
                  "waiting.", file=sys.stderr)
            return 1
        user_id, actual_email, hd, _created, _last = found

        if (hd or "").lower() != ALLOWED_HD:
            print(f"REFUSED: {actual_email} has provider hd={hd!r}, not "
                  f"{ALLOWED_HD!r}.\n"
                  "  An account with an IK address but no Workspace membership "
                  "is exactly the case email.endsWith() accepts and we do not.",
                  file=sys.stderr)
            return 1

        cur.execute("""
            insert into profiles (user_id, email, email_domain, role,
                                  is_shared_account)
            values (%s, %s, %s, %s, %s)
            on conflict (user_id) do update
               set role = excluded.role,
                   email = excluded.email,
                   is_shared_account = excluded.is_shared_account,
                   updated_at = now()
            returning role
        """, (user_id, actual_email, ALLOWED_HD, role, shared))
        new_role = cur.fetchone()[0]
        conn.commit()
    print(f"  {actual_email} -> {new_role}"
          f"{'  (shared account)' if shared else ''}")
    print("  Effective on their next query. No re-projection, no deploy.")
    return 0


def cmd_revoke(args) -> int:
    email = args.email.strip().lower()
    with db.connect(db.SESSION) as conn, conn.cursor() as cur:
        cur.execute("delete from profiles where lower(email) = lower(%s)", (email,))
        gone = cur.rowcount
        conn.commit()
    if not gone:
        print(f"  no profile for {email} — nothing to revoke")
        return 1
    print(f"  revoked {email}. Effective on their NEXT QUERY.")
    print("  Their session is still valid: an already-issued access token works "
          "until it expires (about an hour) but now resolves to role 'none',\n"
          "  so it reads nothing. To stop new tokens as well, suspend the "
          "Google Workspace account. Do both.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    g = sub.add_parser("grant")
    g.add_argument("email")
    g.add_argument("--role", default="member", choices=ROLES)
    r = sub.add_parser("revoke")
    r.add_argument("email")
    args = ap.parse_args()
    return {"list": cmd_list, "grant": cmd_grant, "revoke": cmd_revoke}[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
