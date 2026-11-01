#!/usr/bin/env python3
"""Google Sheets → KB import. Read-only on the Sheets side, always.

    # dry run (default): fetch → stage → validate → plan → report. Writes NOTHING.
    python3 pipeline/kb_import_sheets.py --as admin@interviewkickstart.com \
        [--fixture fixtures/sheets_sample.json | --sheet-id <id>]
    # apply the same plan, then record the run in kb.import_runs
    python3 pipeline/kb_import_sheets.py --as ... --apply [--report out.json]

The import ACTS AS a named KB admin (their profile email): every write goes
through web/lib/kb/service.py under that admin's RLS, attributed in the audit
log with actor_type='import'. There is no owner-privileged write path.

Refuses to --apply against a production database unless --allow-production is
given explicitly (docs/MIGRATION_REPORT.md has the procedure, backup first).

Live fetch uses a service-account key PATH (NP_DRIVE_SA_KEY), scope
spreadsheets.readonly, and the spreadsheet id from --sheet-id or KB_SHEETS_ID.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
# The script's own directory would make `lib` resolve to pipeline/lib (a regular
# package) instead of web/lib (a namespace package), so it is dropped.
sys.path[:] = [p for p in sys.path if Path(p or ".").resolve() != REPO / "pipeline"]
sys.path[:0] = [str(REPO), str(REPO / "web")]

from pipeline.lib import db                                           # noqa: E402
from pipeline.lib import kb_sheets                                    # noqa: E402

MAPPING = REPO / "config" / "kb-sheets-mapping.yaml"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]


def fetch_live(sheet_id: str, mapping: dict) -> dict:
    """spreadsheets.values.batchGet over the mapped tabs only. Read-only scope."""
    key = os.environ.get("NP_DRIVE_SA_KEY")
    if not key:
        sys.exit("NP_DRIVE_SA_KEY is not set: the PATH to a service-account key with the sheet shared to it")
    key_path = Path(key).expanduser().resolve()
    if REPO in key_path.parents:
        sys.exit("refusing a key file inside the repository (CLAUDE.md: keys live outside the repo)")
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    creds = service_account.Credentials.from_service_account_file(str(key_path), scopes=SCOPES)
    api = build("sheets", "v4", credentials=creds, cache_discovery=False)
    ranges = [f"'{t}'!A1:Z5000" for t in mapping["tabs"]]
    return api.spreadsheets().values().batchGet(spreadsheetId=sheet_id, ranges=ranges,
                                                majorDimension="ROWS").execute(num_retries=2)


def _user_id(email: str) -> str:
    with db.connect(db.SESSION) as conn:
        row = conn.execute("select user_id from profiles where lower(email) = %s", (email.lower(),)).fetchone()
    if not row:
        sys.exit(f"no profile for {email}; the importer acts as an existing KB admin")
    return str(row[0])


def run(args) -> dict:
    mapping = kb_sheets.load_mapping(MAPPING)
    if args.fixture:
        batch = json.loads(Path(args.fixture).read_text(encoding="utf-8"))
        source = f"fixture:{Path(args.fixture).name}"
    else:
        sheet_id = args.sheet_id or os.environ.get("KB_SHEETS_ID")
        if not sheet_id:
            sys.exit("give --fixture, --sheet-id, or set KB_SHEETS_ID")
        batch = fetch_live(sheet_id, mapping)
        source = f"sheets:{sheet_id}"
    sheet_id = batch.get("spreadsheetId") or "unknown"
    staged = kb_sheets.stage(mapping, kb_sheets.parse_tabs(batch), sheet_id)

    url = os.environ.get(db.SESSION) or ""
    reason = db.production_reason(url) if url else None
    if args.apply and reason and not args.allow_production:
        sys.exit(f"REFUSED: --apply against PRODUCTION ({reason}). Back up first "
                 "(db/window/backup.sh), then re-run with --allow-production.")

    from lib.kb import service as svc
    uid = _user_id(args.as_email)
    actor = svc.Actor(uid, "import")
    with db.connect(db.SESSION) as conn:
        conn.execute("select set_config('request.jwt.claims', %s, true), set_config('role', 'authenticated', true)",
                     (json.dumps({"role": "authenticated", "sub": uid}),))
        svc.begin(conn, actor)
        svc.require(conn, "admin", "importing")
        report = kb_sheets.plan(conn, svc, staged)
        report["source"] = source
        report["mode"] = "apply" if args.apply else "dry-run"
        if args.apply:
            report["written"] = kb_sheets.apply(conn, svc, actor, staged)
            conn.execute("insert into kb.import_runs (source, mode, counts, report, actor_id, finished_at) "
                         "values (%s, 'apply', %s, %s, %s, now())",
                         (source, json.dumps(report["counts"]), json.dumps(report, default=str), uid))
            conn.commit()
        else:
            conn.rollback()
    return report


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Google Sheets → KB import (dry run unless --apply)")
    ap.add_argument("--as", dest="as_email", required=True, help="profile email of the KB admin to act as")
    ap.add_argument("--fixture", help="a batchGet-shaped JSON file instead of the live API")
    ap.add_argument("--sheet-id")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--allow-production", action="store_true")
    ap.add_argument("--report", help="write the full JSON report here")
    args = ap.parse_args(argv)
    report = run(args)
    c = report["counts"]
    print(f"{report['mode']} from {report['source']}")
    print("  " + "  ".join(f"{k}={v}" for k, v in c.items()))
    if report.get("written"):
        print("  written: " + "  ".join(f"{k}={v}" for k, v in report["written"].items()))
    # COUNT, enumerate only what a person must act on (CLAUDE.md §5).
    for r in report["rows_needing_attention"][:50]:
        print(f"  {r['status']:9} {r['tab']}!{r['row']}: {r['why']}")
    if len(report["rows_needing_attention"]) > 50:
        print(f"  … and {len(report['rows_needing_attention']) - 50} more in the JSON report")
    for b in report["broken_references"][:20]:
        print(f"  broken    {b['tab']}!{b['row']}: missing {b.get('missing') or b.get('attach')}")
    if args.report:
        Path(args.report).write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
