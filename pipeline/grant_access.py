#!/usr/bin/env python3
"""Grant, list and revoke access. The deliberate act that a session is not.

SCOPE CHANGED 2026-09-18, migration 0015. `member` is no longer granted here:
a verified IK Workspace identity gets it automatically at signup, because the
manual step gated membership of the company — which layers 0 and 3 already
decide — rather than gating anything this script could refuse. docs/AUTH.md
records that as a reversal, with the reasoning and what it does NOT change.

This remains the only way to grant `recruiting` or `admin`, which are the roles
that actually gate something: the hiring funnel, and curation writes. It is a
script run by an operator rather than an HTTP route, and it is still the only
way to REVOKE anything, including a profile the trigger created.

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


def _shared_accounts(cur) -> set[str]:
    """The list, FROM THE DATABASE, not from the environment.

    It used to read NP_SHARED_ACCOUNTS. That variable was set in Vercel and
    never in the laptop environment this script runs in, so the list was empty,
    so no account was shared, so `grant --role recruiting` on the shared team
    mailbox succeeded — and migration 0008's CHECK did not fire either, because
    it is keyed on `is_shared_account`, which this script had just written as
    false.

    An unset variable made "no shared accounts exist" indistinguishable from "I
    was never told which accounts are shared", and the permissive reading won.
    Migration 0014 moved the list into the database and derives the flag with a
    trigger, so the caller can no longer supply it. This function reads the same
    table, so the script's message and the database's refusal agree.
    """
    cur.execute("select local_part from shared_accounts")
    return {r[0].lower() for r in cur.fetchall()}


#: Where GoTrue actually puts a non-standard OIDC claim. Established by reading
#: a real row, not from documentation:
#:
#:   identity_data -> 'custom_claims' ->> 'hd'   <-- where it IS
#:   identity_data ->> 'hd'                      <-- where this script looked
#:
#: The first version read only the second and found NULL for every account,
#: which it reported as "provider hd=None, not 'interviewkickstart.com'" — a
#: refusal that reads as "this account is not a Workspace identity" when it
#: actually meant "I looked in the wrong place". It would have refused every
#: legitimate user, and no test caught it because no test has a real GoTrue row.
HD_PATHS = (
    ("identity_data -> 'custom_claims' ->> 'hd'", "identities.custom_claims.hd"),
    ("identity_data ->> 'hd'", "identities.hd"),
)


def _lookup(cur, email: str):
    """Find the auth.users row, and the hd the PROVIDER supplied at signup.

    `auth.identities.identity_data` rather than `auth.users.raw_user_meta_data`:
    user_metadata is writable by the user through the auth API, so an `hd` read
    from it is an attacker-controlled string. identity_data is what GoTrue
    recorded from Google and is not user-writable.

    Even so, this is CORROBORATION, not the proof. The proof is that the row
    exists at all: /api/session verified the `hd` on a signed Google token
    before GoTrue was ever contacted, and the migration-0007 hook refuses to
    create a user without it. That distinction matters for how a missing value
    is reported — see cmd_grant.
    """
    # Each path is qualified with the identities alias; coalesce takes the
    # first that is present, so a shape change is survivable by adding a path.
    hd_expr = "coalesce(" + ", ".join(f"i.{sql}" for sql, _ in HD_PATHS) + ")"
    cur.execute(f"""
        select u.id, u.email, {hd_expr} as hd,
               u.created_at, u.last_sign_in_at,
               (i.user_id is not null) as has_google_identity
        from auth.users u
        left join auth.identities i
               on i.user_id = u.id and i.provider = 'google'
        where lower(u.email) = lower(%s)
    """, (email,))
    return cur.fetchone()


AUTO_GRANT_VERSION = "0015"
IK_DOMAIN = "interviewkickstart.com"


def _auto_grant_applied_at(cur):
    """When 0015 landed — DERIVED from the migration table, never hardcoded.

    The whole point of this check is to tell "the trigger should have fired"
    from "this account predates the trigger", and a date typed into this file
    would be a second source of truth about when that changed (instance 8).
    """
    cur.execute("select applied_at from np_schema_migrations where version = %s",
                (AUTO_GRANT_VERSION,))
    row = cur.fetchone()
    return row[0] if row else None


def _unprovisioned(cur):
    """auth.users rows with no profile, split by whether 0015 was live yet."""
    applied = _auto_grant_applied_at(cur)
    cur.execute("""
        select u.email, u.created_at, u.last_sign_in_at,
               u.email_confirmed_at is not null,
               now() - u.created_at
        from auth.users u
        where not exists (select 1 from profiles p where p.user_id = u.id)
        order by u.created_at
    """)
    out = []
    for email, created, last, confirmed, age in cur.fetchall():
        domain = (email or "").split("@")[-1].lower()
        ik = domain == IK_DOMAIN
        # A row with no created_at cannot be placed either side of the
        # migration. FAIL LOUD rather than open: an IK account whose age is
        # unknown is flagged, because the alternative is that a row with a
        # missing timestamp silently drops out of the only check that watches
        # for a broken auto-grant.
        if created is None or applied is None:
            after = None
        else:
            after = created > applied
        out.append({
            "email": email, "domain": domain, "created": created,
            "last_sign_in": last, "confirmed": confirmed, "age": age,
            "ik": ik,
            "after_auto_grant": after,
            # An IK account created after the trigger existed SHOULD have a
            # profile. `after is None` means undatable, which is also flagged.
            "anomalous": ik and after is not False,
            "undatable": created is None,
        })
    return applied, out


def _fmt_age(delta) -> str:
    if delta is None:
        return "?"
    days = delta.days
    if days >= 1:
        return f"{days}d"
    hours = delta.seconds // 3600
    return f"{hours}h" if hours else f"{delta.seconds // 60}m"


def _report_unprovisioned(_legacy=None) -> int:
    """Print the no-profile population. Returns the number of ANOMALIES.

    BEFORE 0015 this was, correctly, "the resting state for someone who has
    signed in and not yet been granted access". The auto-grant changed what the
    same observation means, and the old wording outlived its condition: an IK
    account with no profile is now a FAULT, not a queue.
    """
    with db.connect(db.SESSION) as conn, conn.cursor() as cur:
        applied, rows = _unprovisioned(cur)

    if not rows:
        print("\nNO-PROFILE ACCOUNTS: none — every auth.users row has a profile")
        return 0

    anomalies = [r for r in rows if r["anomalous"]]
    expected = [r for r in rows if not r["anomalous"]]

    if anomalies:
        print(f"\n*** {len(anomalies)} IK ACCOUNT(S) SIGNED IN AND GOT NOTHING ***")
        print("    These were created AFTER the auto-grant existed, so migration "
              f"{AUTO_GRANT_VERSION}'s trigger should have given each a profile.")
        for r in anomalies:
            print(f"      {r['email']:<46} no profile for {_fmt_age(r['age']):>5}"
                  f"   (created {r['created'].strftime('%Y-%m-%d %H:%M')})")
        print("    TWO CAUSES LOOK IDENTICAL HERE and this list cannot separate")
        print("    them: the trigger failed to fire, or the profile was REVOKED.")
        print("    `revoke` deletes the row and records nothing, so a revoked")
        print("    account is indistinguishable from a broken auto-grant.")
        print("    Check: did anyone revoke this person? If not, the trigger is")
        print("    the suspect — `select tgenabled from pg_trigger` on auth.users.")

    if expected:
        print(f"\nNO PROFILE, EXPECTED ({len(expected)}):")
        for r in expected:
            if not r["ik"]:
                why = "not an IK domain — correctly gets nothing"
            else:
                why = f"predates {AUTO_GRANT_VERSION}; needs a manual grant"
            print(f"  {r['email']:<46} {_fmt_age(r['age']):>5}  {why}")

    if applied is None:
        print(f"\n  NOTE: migration {AUTO_GRANT_VERSION} is NOT APPLIED to this "
              "database, so nothing is auto-granted and every row above is "
              "expected. That is itself the thing to fix.")
    return len(anomalies)


def cmd_check(_args) -> int:
    """Exit non-zero if any IK account is signed in with no profile.

    Exists so the gap is COUNTABLE rather than reported one person at a time
    when they complain. A teammate who signs in and reads nothing sees a
    plausible-looking empty state and assumes it is normal; nobody finds out
    the trigger stopped firing. This is what notices.
    """
    n = _report_unprovisioned()
    print()
    if n:
        print(f"FAIL: {n} IK account(s) with no profile.")
        return 1
    print("OK: no IK account is signed in without a profile.")
    return 0


def cmd_list(_args) -> int:
    with db.connect(db.SESSION) as conn, conn.cursor() as cur:
        cur.execute("""
            select p.email, p.role, p.is_shared_account, p.email_domain,
                   p.created_at, u.last_sign_in_at
            from profiles p left join auth.users u on u.id = p.user_id
            order by p.role, p.email
        """)
        rows = cur.fetchall()

    print(f"{'EMAIL':<46} {'ROLE':<11} SHARED  LAST SIGN-IN")
    for email, role, shared, _dom, _c, last in rows:
        print(f"{email:<46} {role:<11} {'yes' if shared else ' - ':<6}  "
              f"{last.strftime('%Y-%m-%d %H:%M') if last else 'never'}")
    if not rows:
        print("  (no profiles — nobody can read anything)")

    _report_unprovisioned()
    return 0


def cmd_grant(args) -> int:
    email = args.email.strip().lower()
    role = args.role
    if role not in ROLES:
        print(f"role must be one of {ROLES}", file=sys.stderr)
        return 2

    with db.connect(db.SESSION) as conn, conn.cursor() as cur:
        shared = email.split("@", 1)[0].lower() in _shared_accounts(cur)
        if shared and role != "member":
            # The 0014 trigger and the 0008 CHECK would refuse this anyway.
            # Saying it here means the operator learns WHY rather than reading a
            # constraint name out of a traceback.
            print(f"REFUSED: {email} is a shared account. It cannot hold "
                  f"{role!r} — the audit log would name an ACCOUNT, not a "
                  "person, and `recruiting` reads named hiring outcomes about "
                  "external people, which is exactly where an unattributable "
                  "access log stops being acceptable.", file=sys.stderr)
            return 1
        found = _lookup(cur, email)
        if not found:
            print(f"No auth.users row for {email}.\n"
                  "  They must sign in ONCE first. That is the intended order: "
                  "signing in proves the Workspace identity (and invokes the\n"
                  "  migration-0007 hook); this grants the access. "
                  "`grant_access.py list` shows who has signed in and is "
                  "waiting.", file=sys.stderr)
            return 1
        user_id, actual_email, hd, _created, _last, has_identity = found

        # THREE STATES, and they are not the same refusal.
        if not has_identity:
            print(f"REFUSED: {actual_email} has no Google identity row. The "
                  "account exists but did not arrive through the Google "
                  "provider, so there is nothing to corroborate.",
                  file=sys.stderr)
            return 1
        if hd is None:
            # NOT "the account is not a Workspace identity". The claim was
            # verified at /api/session before GoTrue was contacted, and the
            # 0007 hook refuses to create a user without it — so an account
            # that exists has already passed the domain rule twice. A null here
            # means the value is not where this script looked, which is a
            # storage-shape question, not an identity one.
            print(f"REFUSED: no hd recorded for {actual_email} in any known "
                  "location.\n"
                  "  Looked in: " + ", ".join(name for _, name in HD_PATHS) + "\n"
                  "  This does NOT mean the account failed the domain check — "
                  "it passed twice to exist at all (/api/session before GoTrue, "
                  "and the migration-0007 hook).\n"
                  "  It means GoTrue's storage shape has changed. Inspect "
                  "auth.identities.identity_data and add the new path to "
                  "HD_PATHS before granting.", file=sys.stderr)
            return 1
        if hd.lower() != ALLOWED_HD:
            print(f"REFUSED: {actual_email} has provider hd={hd!r}, not "
                  f"{ALLOWED_HD!r}.\n"
                  "  An account with an IK address but no Workspace membership "
                  "is exactly the case email.endsWith() accepts and we do not.",
                  file=sys.stderr)
            return 1

        # `is_shared_account` is passed for readability only — the 0014 trigger
        # overwrites it from the shared_accounts table, so a wrong value here
        # cannot disable the constraint that depends on it.
        try:
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
        except Exception as exc:                                   # noqa: BLE001
            conn.rollback()
            name = getattr(getattr(exc, "diag", None), "constraint_name", "") or ""
            if "shared_accounts_stay_member" in name:
                print(f"REFUSED by the database: {actual_email} is a shared "
                      f"account and cannot hold {role!r}. The trigger from "
                      "migration 0014 derived that from the shared_accounts "
                      "table, whatever this script believed.", file=sys.stderr)
                return 1
            raise
    print(f"  {actual_email} -> {new_role}"
          f"{'  (shared account — capped at member)' if shared else ''}")
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
    sub.add_parser("check")
    g = sub.add_parser("grant")
    g.add_argument("email")
    g.add_argument("--role", default="member", choices=ROLES)
    r = sub.add_parser("revoke")
    r.add_argument("email")
    args = ap.parse_args()
    return {"list": cmd_list, "check": cmd_check,
            "grant": cmd_grant, "revoke": cmd_revoke}[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
