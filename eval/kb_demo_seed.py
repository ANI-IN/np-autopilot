#!/usr/bin/env python3
"""Reset the LOCAL knowledge base to a small, fictional demo set. Re-runnable.

    python eval/kb_demo_seed.py            # wipe kb content, recreate demo users + data

LOCAL ONLY: refuses unless the database and Supabase Auth are loopback (the
local stack in db/local). Never run against a shared project, so it lives in
eval/, which is never deployed.

What it does, every run:
  1. Demo users in the local Supabase Auth (email + password), each with an IK
     profile and a KB role: demo-admin (admin), demo-editor (editor),
     demo-contributor (contributor). Passwords are reset to DEMO_PASSWORD.
  2. Removes every kb record, relationship, resource, tag, proposal, token and
     audit entry (the bulk performance data included). Types and rules stay.
  3. Creates the demo set THROUGH THE SERVICE LAYER, as those users, so
     history, audit and validation behave exactly as they do in the app.

Everything is fictional: the people, programs, schedules and URLs. Deliberate
gaps for the Data quality page: the "Interview Strategy" module has no owner,
one solutions repo link is broken (checked for real when online), the draft
topic "Bit Manipulation" is not connected to anything, and a few live
sessions have no resources yet.
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path[:0] = [str(HERE), str(REPO), str(REPO / "web")]

import kb_local_stack as stack                                        # noqa: E402

DEMO_PASSWORD = "ik-demo-local"
USERS = {"admin": "demo-admin@interviewkickstart.com",
         "editor": "demo-editor@interviewkickstart.com",
         "contributor": "demo-contributor@interviewkickstart.com"}
CONTENT = ("link_checks", "node_tags", "node_resources", "edges", "nodes", "resources", "tags",
           "proposals", "api_tokens", "audit_log", "import_runs")
BROKEN_URL = "https://github.com/ik-demo/dp-on-grids-solutions"

# ---------------------------------------------------------------------------
# The demo set. (type, name, summary, owner, scope) — scope is a course name.
# ---------------------------------------------------------------------------
A, E, C = "admin", "editor", "contributor"

PROGRAMS = [
    ("ML Engineering Accelerator", "A 16-week program for software engineers moving into ML engineering roles.", A),
    ("Backend Engineering Interview Prep", "A 12-week program preparing backend engineers for senior and staff interviews.", A),
]
DOMAINS = [("Machine Learning", E), ("Generative AI", E), ("Algorithms", C), ("Distributed Systems", C)]
COURSES = [  # name, summary, owner, programs, domains
    ("ML Foundations", "Classical machine learning, from linear models to ensembles, with an evaluation mindset.",
     E, ["ML Engineering Accelerator"], ["Machine Learning"]),
    ("Deep Learning & LLM Applications", "Neural networks, transformers and building production LLM features.",
     E, ["ML Engineering Accelerator"], ["Machine Learning", "Generative AI"]),
    ("Data Structures & Algorithms", "The coding-interview core: patterns, complexity and communication.",
     C, ["Backend Engineering Interview Prep", "ML Engineering Accelerator"], ["Algorithms"]),
    ("System Design for Senior Engineers", "Designing large-scale systems and defending trade-offs in the interview.",
     A, ["Backend Engineering Interview Prep"], ["Distributed Systems"]),
]
# course -> [(module, owner, [(week, [(session, summary, instructor, [topics])])])]
STRUCTURE = {
    "ML Foundations": [
        ("Supervised Learning", E, [
            ("Week 1 · Regression and regularization", [
                ("Linear models from scratch", "Sat 9:00 AM PT · 2 h", "Avery Lindqvist", ["Regularization"])]),
            ("Week 2 · Trees and ensembles", [
                ("Gradient boosting in practice", "Sat 9:00 AM PT · 2 h", "Avery Lindqvist", ["Gradient boosting"])]),
        ]),
        ("Model Evaluation", C, [
            ("Week 3 · Metrics and validation", [
                ("Choosing the right metric", "Sat 9:00 AM PT · 2 h", "Noor Haddad", ["Precision and recall"]),
                ("ML case-study mock interview", "Sun 10:00 AM PT · 90 min", "Noor Haddad", ["Precision and recall"])]),
        ]),
    ],
    "Deep Learning & LLM Applications": [
        ("Neural Networks", E, [
            ("Week 1 · Backpropagation and optimizers", [
                ("Training a CNN end to end", "Sat 11:30 AM PT · 2 h", "Kenji Arakawa", ["Transformers"])]),
        ]),
        ("LLM Applications", A, [
            ("Week 2 · Retrieval-augmented generation", [
                ("Building a RAG pipeline", "Sat 11:30 AM PT · 2 h", "Kenji Arakawa", ["Embeddings"])]),
            ("Week 3 · Evaluating LLM systems", [
                ("LLM evaluation harnesses", "Sat 11:30 AM PT · 2 h", "Noor Haddad", ["Embeddings"])]),
        ]),
    ],
    "Data Structures & Algorithms": [
        ("Arrays and Hashing", C, [
            ("Week 1 · Two pointers and sliding window", [
                ("Sliding-window patterns", "Sun 8:00 AM PT · 2 h", "Marisol Ventura", ["Sliding window"])]),
        ]),
        ("Graphs and Dynamic Programming", C, [
            ("Week 2 · Graph traversal", [
                ("BFS and DFS patterns", "Sun 8:00 AM PT · 2 h", "Marisol Ventura", ["Graph traversal"])]),
            ("Week 3 · Dynamic programming", [
                ("DP on grids", "Sun 8:00 AM PT · 2 h", "Tobias Fennimore", ["Dynamic programming"])]),
        ]),
        ("Interview Strategy", None, [          # deliberate gap: no owner
            ("Week 4 · Communicating your approach", [
                ("Mock coding interview", "Sun 8:00 AM PT · 90 min", "Tobias Fennimore", [])]),
        ]),
    ],
    "System Design for Senior Engineers": [
        ("Scalability Fundamentals", A, [
            ("Week 1 · Caching and load balancing", [
                ("Designing a URL shortener", "Sat 1:00 PM PT · 2 h", "Rhea Castellano", ["Caching"])]),
        ]),
        ("Distributed Data", E, [
            ("Week 2 · Partitioning and replication", [
                ("Designing a news feed", "Sat 1:00 PM PT · 2 h", "Rhea Castellano", ["Sharding", "Consistent hashing"])]),
        ]),
    ],
}
MODULE_SUMMARIES = {
    "Supervised Learning": "Linear models, regularization, trees and ensembles, built from first principles.",
    "Model Evaluation": "Metrics, validation strategy and explaining model quality in an interview.",
    "Neural Networks": "Backpropagation, optimizers and training convolutional networks.",
    "LLM Applications": "Retrieval-augmented generation and evaluating LLM features before they ship.",
    "Arrays and Hashing": "Two pointers, sliding window and hash-map patterns.",
    "Graphs and Dynamic Programming": "Traversal patterns and the dynamic-programming toolkit.",
    "Interview Strategy": "Communicating an approach, handling hints and managing time in a coding round.",
    "Scalability Fundamentals": "Caching, load balancing and back-of-the-envelope estimates.",
    "Distributed Data": "Partitioning, replication and consistency trade-offs.",
}
INSTRUCTORS = [  # name, owner, teaches (courses)
    ("Avery Lindqvist", E, ["ML Foundations"]),
    ("Noor Haddad", E, ["ML Foundations", "Deep Learning & LLM Applications"]),
    ("Kenji Arakawa", A, ["Deep Learning & LLM Applications"]),
    ("Marisol Ventura", C, ["Data Structures & Algorithms"]),
    ("Tobias Fennimore", C, ["Data Structures & Algorithms"]),
    ("Rhea Castellano", A, ["System Design for Senior Engineers"]),
]
TOPIC_LINKS = [("related", "Sharding", "Consistent hashing"), ("prerequisite", "Gradient boosting", "Regularization"),
               ("related", "Embeddings", "Transformers"), ("prerequisite", "Dynamic programming", "Graph traversal")]
COURSE_LINKS = [("prerequisite", "Deep Learning & LLM Applications", "ML Foundations"),
                ("related", "System Design for Senior Engineers", "Data Structures & Algorithms")]
TAGS = {"ML Engineering Accelerator": ["flagship"], "Deep Learning & LLM Applications": ["new-2026"],
        "Building a RAG pipeline": ["new-2026"], "Designing a news feed": ["needs-refresh"]}

D, Z, G = "https://docs.google.com/presentation/d/1IKdemo", "https://ik-demo.zoom.us/rec/share/", "https://github.com/ik-demo/"
RESOURCES = [  # (attach to, kind, title, url, note)
    ("ML Foundations", "doc", "ML Foundations syllabus", "https://docs.google.com/document/d/1IKdemoMLFsyllabus/edit", None),
    ("Linear models from scratch", "slides", "Linear models — slides", D + "LinModels/edit", None),
    ("Linear models from scratch", "recording", "Linear models — recording", Z + "demo-linmodels-w1", "2 h 04 min"),
    ("Week 1 · Regression and regularization", "assignment", "Assignment 1: ridge vs lasso", "https://docs.google.com/document/d/1IKdemoA1ridge/edit", "Due Fri"),  # taxonomy-literal-ok: a KB resource kind (migration 0026 CHECK), not the corpus-graph taxonomy
    ("Week 1 · Regression and regularization", "solution", "Assignment 1 solution notebook", G + "ml-foundations-a1-solution", None),
    ("Gradient boosting in practice", "slides", "Gradient boosting — slides", D + "GBM/edit", None),
    ("Gradient boosting in practice", "recording", "Gradient boosting — recording", Z + "demo-gbm-w2", "1 h 58 min"),
    ("Choosing the right metric", "slides", "Evaluation metrics — slides", D + "Metrics/edit", None),
    ("Supervised Learning", "repo", "Supervised learning starter code", G + "supervised-learning-starter", None),
    ("Deep Learning & LLM Applications", "doc", "Deep Learning & LLM syllabus", "https://docs.google.com/document/d/1IKdemoDLsyllabus/edit", None),
    ("Training a CNN end to end", "slides", "CNN training — slides", D + "CNN/edit", None),
    ("Training a CNN end to end", "recording", "CNN training — recording", Z + "demo-cnn-w1", "2 h 10 min"),
    ("Building a RAG pipeline", "slides", "RAG pipeline — slides", D + "RAG/edit", None),
    ("Building a RAG pipeline", "repo", "RAG pipeline reference implementation", G + "rag-pipeline-reference", None),
    ("Week 2 · Retrieval-augmented generation", "assignment", "Assignment 2: build a retriever", "https://docs.google.com/document/d/1IKdemoA2retriever/edit", "Due Fri"),  # taxonomy-literal-ok: a KB resource kind (migration 0026 CHECK), not the corpus-graph taxonomy
    ("Data Structures & Algorithms", "doc", "DSA syllabus and problem list", "https://docs.google.com/spreadsheets/d/1IKdemoDSAlist/edit", None),
    ("Sliding-window patterns", "slides", "Sliding window — slides", D + "SlidingWindow/edit", None),
    ("Sliding-window patterns", "recording", "Sliding window — recording", Z + "demo-sliding-w1", "1 h 52 min"),
    ("BFS and DFS patterns", "slides", "Graph traversal — slides", D + "Graphs/edit", None),
    ("Week 3 · Dynamic programming", "assignment", "DP problem set", "https://docs.google.com/document/d/1IKdemoDPset/edit", "12 problems"),  # taxonomy-literal-ok: a KB resource kind (migration 0026 CHECK), not the corpus-graph taxonomy
    ("DP on grids", "solution", "DP on grids — solutions repo", BROKEN_URL, "Repo was renamed; link not updated"),
    ("System Design for Senior Engineers", "doc", "System design syllabus", "https://docs.google.com/document/d/1IKdemoSDsyllabus/edit", None),
    ("Designing a URL shortener", "slides", "URL shortener — slides", D + "URLShortener/edit", None),
    ("Designing a URL shortener", "recording", "URL shortener — recording", Z + "demo-urlshort-w1", "2 h 01 min"),
    ("Distributed Data", "repo", "Sharding simulator", G + "sharding-simulator", None),
]


# ---------------------------------------------------------------------------
# plumbing
# ---------------------------------------------------------------------------

def _auth(st: dict, method: str, path: str, body: dict | None = None) -> dict:
    req = urllib.request.Request(f"{st['API_URL']}/auth/v1/{path}", method=method,
                                 data=json.dumps(body).encode() if body is not None else None)
    req.add_header("content-type", "application/json")
    req.add_header("apikey", st["SERVICE_ROLE_KEY"])
    req.add_header("authorization", f"Bearer {st['SERVICE_ROLE_KEY']}")
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read() or b"{}")


def ensure_users(st: dict, owner) -> dict:
    """Create (or reset the password of) each demo user; give each a profile and role."""
    existing = {u["email"]: u["id"] for u in _auth(st, "GET", "admin/users?per_page=1000").get("users", [])}
    ids = {}
    for role, email in USERS.items():
        if email in existing:
            uid = existing[email]
            _auth(st, "PUT", f"admin/users/{uid}", {"password": DEMO_PASSWORD, "email_confirm": True})
        else:
            uid = _auth(st, "POST", "admin/users", {"email": email, "password": DEMO_PASSWORD,
                                                    "email_confirm": True})["id"]
        ids[role] = uid
        owner.execute("insert into profiles (user_id, email, email_domain, role) values (%s, %s, 'interviewkickstart.com', 'member') "
                      "on conflict (user_id) do nothing", (uid, email))
        owner.execute("insert into kb.memberships (user_id, role) values (%s, %s) "
                      "on conflict (user_id) do update set role = excluded.role, archived_at = null", (uid, role))
    # Test-suite users (tests/kb_support.py) would clutter Settings → Members and
    # the owner picker; the tests recreate them whenever they run.
    owner.execute("delete from kb.memberships m using profiles p where p.user_id = m.user_id "
                  "and p.email like 'kbtest-%%@interviewkickstart.com'")
    return ids


class Seeder:
    def __init__(self, dsn: str, ids: dict):
        import psycopg
        self.conn = psycopg.connect(dsn)
        self.ids, self.nodes, self.as_role = ids, {}, None

    def act(self, role: str):
        """Switch the acting user (commits what the previous one did)."""
        from lib.kb import service as svc
        self.conn.commit()
        self.as_role = role
        claims = json.dumps({"role": "authenticated", "sub": self.ids[role]})
        self.conn.execute("select set_config('request.jwt.claims', %s, false), set_config('role', 'authenticated', false)", (claims,))
        svc.begin(self.conn, svc.Actor(self.ids[role]))
        self.conn.execute("select set_config('kb.actor_type', 'human', false)")
        return svc.Actor(self.ids[role])

    def node(self, type_key, name, summary=None, owner=None, scope=None, status="active"):
        from lib.kb import service as svc
        actor = self.act(owner or "editor")
        body = {"type": type_key, "name": name, "status": status}
        if summary:
            body["summary"] = summary
        body["owner_id"] = self.ids[owner] if owner else None     # explicit: None is the deliberate gap
        if scope:
            body["scope"] = str(self.nodes[scope]["id"])
        n = svc.create_node(self.conn, actor, body)
        self.nodes[name] = n
        return n

    def edge(self, type_key, source, target, role="editor"):
        from lib.kb import service as svc
        svc.create_edge(self.conn, self.act(role), {"type": type_key, "source_id": str(self.nodes[source]["id"]),
                                                     "target_id": str(self.nodes[target]["id"])})

    def close(self):
        self.conn.commit()
        self.conn.close()


def build(s: Seeder) -> dict:
    from lib.kb import service as svc
    for name, summary, owner in PROGRAMS:
        s.node("program", name, summary, owner)
    for name, owner in DOMAINS:
        s.node("domain", name, f"Subject area: {name}.", owner)
    for name, summary, owner, programs, domains in COURSES:
        s.node("course", name, summary, owner, scope=programs[0])     # home program; others via contains
        for p in programs:
            s.edge("contains", p, name, "admin")
        for d in domains:
            s.edge("covers", name, d)
    topics = sorted({t for mods in STRUCTURE.values() for _, _, weeks in mods for _, sess in weeks
                     for *_x, ts in sess for t in ts} | {t for _, a, b in TOPIC_LINKS for t in (a, b)})
    for t in topics:
        s.node("topic", t, f"Concept: {t.lower()}.", "contributor")
    s.node("topic", "Bit Manipulation", None, "contributor", status="draft")      # deliberate orphan
    for name, owner, courses in INSTRUCTORS:
        s.node("instructor", name, "Fictional instructor (demo data).", owner)
        for c in courses:
            s.edge("teaches", name, c)
    for course, modules in STRUCTURE.items():
        for module, owner, weeks in modules:
            s.node("module", module, MODULE_SUMMARIES[module], owner, scope=course)
            s.edge("contains", course, module)
            for week, sessions in weeks:
                s.node("week", week, f"{course}: {week.split('·', 1)[1].strip()}.", owner or "editor", scope=course)
                s.edge("contains", module, week)
                for title, when, instructor, ts in sessions:
                    s.node("session", title, f"Live session · {when}.", owner or "editor", scope=course)
                    s.edge("contains", week, title)
                    s.edge("teaches", instructor, title)
                    for t in ts:
                        s.edge("covers", title, t, "contributor")
                        s.edge("covers", module, t, "contributor") if not _has_cover(s, module, t) else None
    for kind, a, b in TOPIC_LINKS + COURSE_LINKS:
        s.edge(kind, a, b)
    s.node("process", "New cohort launch checklist",
           "Steps before a cohort starts: schedule live sessions, assign instructors, publish week 1 resources.", "admin")
    for target in ("ML Engineering Accelerator", "Backend Engineering Interview Prep"):
        s.edge("related", "New cohort launch checklist", target, "admin")
    for name, tags in TAGS.items():
        for t in tags:
            svc.tag_node(s.conn, s.act("editor"), str(s.nodes[name]["id"]), {"name": t})
    broken = None
    for i, (target, kind, title, url, note) in enumerate(RESOURCES):
        role = ("admin", "editor", "contributor")[i % 3]
        body = {"url": url, "title": title, "kind": kind}
        if note:
            body["note"] = note
        out = svc.attach_resource(s.conn, s.act(role), str(s.nodes[target]["id"]), body)
        if url == BROKEN_URL:
            broken = out
    s.conn.commit()
    return {"broken": broken}


_COVERS: set = set()


def _has_cover(s, module, topic) -> bool:
    key = (module, topic)
    if key in _COVERS:
        return True
    _COVERS.add(key)
    return False


def check_broken_link(s: Seeder) -> str:
    """HEAD the deliberately broken URL for real and record the TRUE result, as
    the check_broken_links tool would. Offline: record nothing, say so."""
    from lib.kb import service as svc
    rid = s.conn.execute("select id from kb.resources where url = %s", (BROKEN_URL,)).fetchone()[0]
    try:
        req = urllib.request.Request(BROKEN_URL, method="HEAD", headers={"user-agent": "ik-kb-linkcheck/1"})
        with urllib.request.urlopen(req, timeout=8) as r:
            code = r.status
    except urllib.error.HTTPError as exc:
        code = exc.code
    except (urllib.error.URLError, TimeoutError) as exc:
        return f"link check skipped (offline: {type(exc).__name__}); the Link health list will be empty"
    status = "broken" if code >= 400 else "ok"
    svc.record_link_results(s.conn, s.act("editor"), [{"id": str(rid), "status": status, "http": code}])
    s.conn.commit()
    return f"link check: {BROKEN_URL} answered HTTP {code} -> recorded as {status}"


def main() -> int:
    st = stack.status()
    stack.configure_env(st)
    import os
    import psycopg
    dsn = os.environ["SUPABASE_DB_URL_SESSION"]
    with psycopg.connect(dsn, autocommit=True) as owner:
        if not owner.execute("select to_regclass('kb.link_checks') is not null").fetchone()[0]:
            sys.exit("kb migrations through 0026 are not applied: run  python pipeline/migrate.py up")
        ids = ensure_users(st, owner)
        owner.execute("truncate " + ", ".join(f"kb.{t}" for t in CONTENT) + " cascade")
    s = Seeder(dsn, ids)
    try:
        build(s)
        msg = check_broken_link(s)
        counts = s.conn.execute("""select (select count(*) from kb.nodes), (select count(*) from kb.edges),
                                          (select count(*) from kb.resources)""").fetchone()
    finally:
        s.close()
    print(f"demo data: {counts[0]} records, {counts[1]} relationships, {counts[2]} resources")
    print(msg)
    print("sign in at http://localhost:8765/local-login as " + ", ".join(USERS.values())
          + f"  (password: {DEMO_PASSWORD})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
