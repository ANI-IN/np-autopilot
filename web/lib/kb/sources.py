"""The source catalog for admins (Admin > Sources & sync), read from kb.sources (migration 0040).

Every source the registry sheet reaches (Drive folders and files, linked sheets), every KYP page and
attachment in Confluence, and every access failure, with its live link, version, modified time,
provenance and status. RLS: admins only.
"""
from __future__ import annotations

from .errors import Invalid
from .service import _q, _q1, require

STATUSES = ("extracted", "extracted_empty", "listed", "media_listed", "failed", "do_not_use", "deferred",
            "imported", "attachment_listed")


def list_sources(conn, params: dict) -> dict:
    require(conn, "admin", "the source catalog")
    where, args = ["true"], []
    st = params.get("status")
    if st:
        if st not in STATUSES:
            raise Invalid("unknown status", field="status")
        where.append("s.status = %s"); args.append(st)
    if params.get("provider"):
        where.append("s.provider = %s"); args.append(str(params["provider"])[:20])
    if params.get("kind"):
        where.append("s.kind = %s"); args.append(str(params["kind"])[:40])
    if params.get("q"):
        where.append("(lower(s.title) like %s or lower(s.url) like %s)")
        like = "%" + str(params["q"]).lower()[:100].replace("%", "").replace("_", "") + "%"
        args += [like, like]
    if params.get("removed") != "1":
        where.append("s.removed_at is null")
    limit = max(1, min(int(params.get("limit") or 50), 500))
    offset = max(0, int(params.get("offset") or 0))
    w = " and ".join(where)
    rows = _q(conn, f"""select s.id, s.provider, s.resource_id, s.kind, s.title, s.url, s.version, s.modified_at, s.size_bytes,
                               s.provenance, s.status, s.failure_reason, s.text_chars, s.extracted_at, s.last_seen,
                               s.last_changed, s.removed_at
                        from kb.sources s where {w}
                        order by (s.status = 'failed') desc, s.provider, s.provenance, s.title limit %s offset %s""",
              (*args, limit, offset))
    total = _q1(conn, f"select count(*) as c from kb.sources s where {w}", tuple(args))["c"]
    return {"items": rows, "total": total, "limit": limit, "offset": offset}


def summary(conn) -> dict:
    require(conn, "admin", "the source catalog")
    by_status = _q(conn, """select provider, status, count(*) as n, coalesce(sum(size_bytes), 0) as bytes
                            from kb.sources where removed_at is null group by 1, 2 order by 1, 2""")
    by_kind = _q(conn, """select kind, count(*) as n, coalesce(sum(size_bytes), 0) as bytes
                          from kb.sources where removed_at is null and provider = 'drive' group by 1 order by 2 desc""")
    last = _q1(conn, "select max(last_seen) as last_seen, count(*) filter (where removed_at is not null) as removed, "
                     "count(*) filter (where last_changed is not null) as changed from kb.sources")
    return {"by_status": by_status, "by_kind": by_kind, **(last or {})}
