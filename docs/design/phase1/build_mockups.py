#!/usr/bin/env python3
"""Builds the Phase 1 visual-direction mockups: three static HTML files, one per
direction, each with the same four screens (Home, Search results, Record page,
Program view) and the same FICTIONAL content, so the directions differ only in
the visual system and layout. No data from the knowledge base is used.

    python docs/design/phase1/build_mockups.py      # writes direction-a.html, -b.html, -c.html
"""
from pathlib import Path

HERE = Path(__file__).resolve().parent

PROGRAMS = [("Applied Agentic AI for Software Engineers", "16 weeks", "Sept 2026 cohort", 4),
            ("SprintUP · Backend Engineering", "8 weeks", "Rolling", 3),
            ("EdgeUp · Data Engineering", "12 weeks", "Sept 2026 cohort", 4),
            ("India · Full-Stack Engineering", "20 weeks", "Jan 2027 cohort", 5)]
COURSES = ["System Design", "Backend Engineering", "RAG & Retrieval", "Agents & MCP"]
RECENT = [("Topic", "Consistent hashing", "edited summary", "12 min ago", "Alex Rivera"),
          ("Module", "Vector databases", "added 3 sources from the KYP", "1 h ago", "Ingestion"),
          ("Concept", "Replication lag", "linked as a prerequisite of Read replicas", "3 h ago", "Sam Okafor"),
          ("Program", "EdgeUp · Data Engineering", "schedule updated from KYP v14", "yesterday", "Ingestion")]
ATTENTION = [("4", "records without an owner"), ("2", "broken links"), ("7", "new concepts awaiting approval"), ("1", "source page failed to read")]

ICON = {
    "search": '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>',
    "home": '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 11 12 4l9 7v9a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z"/></svg>',
    "grad": '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 10 12 5 2 10l10 5 10-5z"/><path d="M6 12v5c3 2 9 2 12 0v-5"/></svg>',
    "book": '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 4h10a4 4 0 0 1 4 4v12H8a4 4 0 0 1-4-4z"/></svg>',
    "graph": '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><circle cx="5" cy="12" r="2"/><circle cx="19" cy="5" r="2"/><circle cx="19" cy="19" r="2"/><path d="M7 12h4l6-6M11 12l6 6"/></svg>',
    "link": '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><path d="M10 14a4 4 0 0 0 6 0l3-3a4 4 0 0 0-6-6l-1 1"/><path d="M14 10a4 4 0 0 0-6 0l-3 3a4 4 0 0 0 6 6l1-1"/></svg>',
    "map": '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 4 3 6v14l6-2 6 2 6-2V4l-6 2z"/><path d="M9 4v14M15 6v14"/></svg>',
    "shield": '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 3 4 6v6c0 5 3.5 8 8 9 4.5-1 8-4 8-9V6z"/></svg>',
    "file": '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 3H6a1 1 0 0 0-1 1v16a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V8z"/><path d="M14 3v5h5"/></svg>',
}

DIRECTIONS = {
    "a": {"name": "A · Clarity", "tag": "Light, calm and dense. The current workspace, refined: left sidebar, a global search bar at the top, IK blue as the single accent.",
          "font": "'Inter', system-ui, sans-serif", "layout": "sidebar",
          "tokens": """--bg:#f7f8fa;--surface:#ffffff;--surface-2:#f1f3f6;--border:#e3e6eb;--text:#16181d;--text-2:#4a515c;--text-3:#6b7280;
            --accent:#2670A6;--accent-soft:#e8f1f8;--accent-text:#1d5a87;--ok:#1f7a4d;--warn:#a16207;--danger:#b42318;--radius:8px;
            --shadow:0 1px 2px rgba(16,24,40,.06),0 1px 3px rgba(16,24,40,.08);--chip:#eef2f6;--head:#ffffff;--side:#ffffff;"""},
    "b": {"name": "B · Atlas", "tag": "Dark-first and map-led. The map and the workspace share one visual language: a top bar instead of a sidebar, deep navy surfaces, the graph always one click away.",
          "font": "'Inter', system-ui, sans-serif", "layout": "topbar",
          "tokens": """--bg:#0b1220;--surface:#111a2b;--surface-2:#162236;--border:#22314a;--text:#e7edf6;--text-2:#b3c0d4;--text-3:#8a99b1;
            --accent:#3996D2;--accent-soft:#12324d;--accent-text:#7cc0ec;--ok:#3fb27f;--warn:#e0a63a;--danger:#ef6b5b;--radius:10px;
            --shadow:0 1px 0 rgba(255,255,255,.03),0 8px 24px rgba(0,0,0,.35);--chip:#1a2840;--head:#0e1728;--side:#0e1728;"""},
    "c": {"name": "C · Studio", "tag": "Search-first and spacious. A warm neutral canvas, larger type and cards; the home page opens on one big search box, made for PMs browsing and comparing.",
          "font": "'Inter', system-ui, sans-serif", "layout": "studio",
          "tokens": """--bg:#faf8f5;--surface:#ffffff;--surface-2:#f4f1ec;--border:#e8e2d9;--text:#1f1b16;--text-2:#51493f;--text-3:#7a7065;
            --accent:#324158;--accent-soft:#e9edf3;--accent-text:#324158;--ok:#2f7d4f;--warn:#9a6a12;--danger:#b4372b;--radius:14px;
            --shadow:0 1px 2px rgba(40,30,20,.05),0 6px 18px rgba(40,30,20,.06);--chip:#f1ece4;--head:#faf8f5;--side:#ffffff;"""},
}

CSS = """
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:14px/1.5 var(--font);-webkit-font-smoothing:antialiased}
a{color:var(--accent-text);text-decoration:none}a:hover{text-decoration:underline}
.switch{position:sticky;top:0;z-index:20;display:flex;gap:6px;align-items:center;padding:8px 16px;background:#111;color:#ddd;font-size:12px}
.switch a{color:#ddd;padding:3px 9px;border-radius:999px;border:1px solid #333}.switch a:hover{background:#222;text-decoration:none}
.switch .t{margin-right:auto;font-weight:600}
.screen{min-height:820px;border-bottom:6px solid #00000020;display:grid}
.app-sidebar{grid-template-columns:232px 1fr}.app-topbar,.app-studio{grid-template-rows:auto 1fr}
.side{background:var(--side);border-right:1px solid var(--border);padding:14px 10px;display:flex;flex-direction:column;gap:2px}
.brand{display:flex;align-items:center;gap:8px;font-weight:700;padding:4px 8px 12px}.mark{width:24px;height:24px;border-radius:6px;background:var(--accent);color:#fff;display:grid;place-items:center;font-size:11px}
.nav-g{font-size:11px;color:var(--text-3);text-transform:uppercase;letter-spacing:.06em;padding:12px 8px 4px}
.nav{display:flex;align-items:center;gap:9px;padding:7px 8px;border-radius:7px;color:var(--text-2)}.nav.on{background:var(--accent-soft);color:var(--accent-text);font-weight:600}
.nav .n{margin-left:auto;font-size:12px;color:var(--text-3)}
.admin-sep{margin-top:auto;border-top:1px dashed var(--border);padding-top:8px}
.top{display:flex;align-items:center;gap:14px;padding:10px 20px;background:var(--head);border-bottom:1px solid var(--border)}
.top .tabs{display:flex;gap:4px}.top .tabs a{padding:6px 11px;border-radius:7px;color:var(--text-2)}.top .tabs a.on{background:var(--accent-soft);color:var(--accent-text);font-weight:600}
.search{display:flex;align-items:center;gap:8px;flex:1;max-width:560px;background:var(--surface-2);border:1px solid var(--border);border-radius:var(--radius);padding:8px 12px;color:var(--text-3)}
.search kbd,.k{font:11px ui-monospace,monospace;border:1px solid var(--border);border-radius:4px;padding:1px 5px;color:var(--text-3);margin-left:auto;background:var(--surface)}
.avatar{width:28px;height:28px;border-radius:50%;background:var(--accent);color:#fff;display:grid;place-items:center;font-size:11px;font-weight:600}
.role{font-size:11px;color:var(--text-3)}
.main{padding:22px 28px;display:flex;flex-direction:column;gap:18px;min-width:0}
.crumbs{font-size:12.5px;color:var(--text-3);display:flex;gap:6px;flex-wrap:wrap}.crumbs b{color:var(--text-2);font-weight:500}
h1{font-size:22px;margin:0;letter-spacing:-.01em}h2{font-size:13px;margin:0;color:var(--text-2);text-transform:uppercase;letter-spacing:.05em}
.sub{color:var(--text-3);font-size:13px}
.grid{display:grid;gap:16px}.g2{grid-template-columns:1.4fr 1fr}.g3{grid-template-columns:repeat(3,1fr)}.g4{grid-template-columns:repeat(4,1fr)}
.card{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);box-shadow:var(--shadow);padding:16px}
.card h2{margin-bottom:10px}
.row{display:flex;align-items:center;gap:10px;padding:8px 0;border-top:1px solid var(--border)}.row:first-of-type{border-top:0}
.chip{display:inline-flex;align-items:center;gap:5px;font-size:11.5px;padding:2px 8px;border-radius:999px;background:var(--chip);color:var(--text-2);white-space:nowrap}
.chip.t-program{background:#f6e7d8;color:#8a4b12}.chip.t-course{background:#e2ebfb;color:#1d4fa8}.chip.t-module{background:#dcf2ea;color:#11674a}
.chip.t-topic{background:#eee6fb;color:#5b2fa6}.chip.t-concept{background:#fbe5ee;color:#9b1d50}.chip.t-resource{background:#e8eef3;color:#3b5163}
.dark .chip.t-program{background:#3a2a17;color:#f2b97a}.dark .chip.t-course{background:#18284a;color:#8fb3f5}.dark .chip.t-module{background:#123528;color:#77d6ae}
.dark .chip.t-topic{background:#271c45;color:#c3a8f6}.dark .chip.t-concept{background:#3d1828;color:#f39cbd}.dark .chip.t-resource{background:#1c2a38;color:#a7c0d4}
.muted{color:var(--text-3)}.small{font-size:12px}.grow{flex:1;min-width:0}.trunc{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.stat{font-size:26px;font-weight:700;letter-spacing:-.02em}.btn{display:inline-flex;align-items:center;gap:6px;padding:7px 12px;border-radius:8px;border:1px solid var(--border);background:var(--surface);color:var(--text);font-weight:500}
.btn.p{background:var(--accent);border-color:var(--accent);color:#fff}
.tag-admin{font-size:10px;text-transform:uppercase;letter-spacing:.06em;color:var(--warn);border:1px solid currentColor;border-radius:4px;padding:0 5px}
.cite{font-size:11.5px;color:var(--text-3)}.cite b{color:var(--accent-text);font-weight:600}
.bar{height:8px;border-radius:4px;background:var(--surface-2);overflow:hidden}.bar i{display:block;height:100%;background:var(--accent)}
.timeline{display:grid;grid-template-columns:150px repeat(16,1fr);gap:3px;align-items:center;font-size:11.5px}
.timeline .w{text-align:center;color:var(--text-3)}.timeline .lane{color:var(--text-2);font-weight:500}
.cell{height:24px;border-radius:5px;background:var(--surface-2)}.cell.on{background:var(--accent);opacity:.85}.cell.on2{background:var(--accent);opacity:.55}.cell.on3{background:var(--accent);opacity:.35}
.hero{padding:42px 28px 26px;display:flex;flex-direction:column;align-items:center;gap:14px;text-align:center}
.hero .search{max-width:720px;width:100%;padding:14px 18px;font-size:16px;border-radius:16px;background:var(--surface);box-shadow:var(--shadow)}
.pillrow{display:flex;gap:8px;flex-wrap:wrap;justify-content:center}
.group-h{display:flex;align-items:center;gap:8px;margin:4px 0}
.res{display:flex;gap:12px;padding:10px 0;border-top:1px solid var(--border)}.res:first-of-type{border-top:0}
.kv{display:grid;grid-template-columns:120px 1fr;gap:6px 12px;font-size:13px}.kv dt{color:var(--text-3)}.kv dd{margin:0}
.person{display:inline-flex;align-items:center;gap:6px;padding:3px 8px 3px 3px;border-radius:999px;background:var(--surface-2);font-size:12.5px}
.person .avatar{width:20px;height:20px;font-size:9px}
.note{font-size:12px;color:var(--text-3);border-left:3px solid var(--border);padding-left:10px}
"""


def side(active):
    def nav(ic, label, on=False, n=""):
        return f'<a class="nav{" on" if on else ""}">{ICON[ic]}<span>{label}</span><span class="n">{n}</span></a>'
    return f"""<aside class="side"><div class="brand"><div class="mark">IK</div>Knowledge Base</div>
      {nav("home", "Home", active == "home")}{nav("search", "Search", active == "search")}
      <div class="nav-g">Browse</div>{nav("grad", "Programs", active == "program", "4")}{nav("book", "Courses", False, "4")}
      {nav("graph", "Graph")}{nav("link", "Sources")}{nav("map", "Map")}
      <div class="admin-sep"><div class="nav-g">Admin <span class="tag-admin">admin</span></div>{nav("shield", "Approvals", False, "7")}{nav("shield", "Data quality", False, "14")}{nav("file", "Sources & sync")}</div></aside>"""


def topbar(active, d):
    tabs = "".join(f'<a class="{"on" if active == k else ""}">{l}</a>' for k, l in
                   (("home", "Home"), ("program", "Programs"), ("courses", "Courses"), ("graph", "Graph"), ("map", "Map"), ("sources", "Sources")))
    return f"""<header class="top"><div class="brand" style="padding:0"><div class="mark">IK</div>Knowledge Base</div>
      <nav class="tabs">{tabs}</nav><div class="search">{ICON["search"]}<span>Search programs, topics, concepts, sources…</span><kbd>Ctrl K</kbd></div>
      <a class="nav" style="padding:6px 8px">{ICON["shield"]}<span class="small">Admin</span></a><div class="avatar">AR</div></header>"""


def chip(t, label=None):
    return f'<span class="chip t-{t.lower()}">{label or t}</span>'


def home(d):
    progs = "".join(f'<div class="row"><div class="grow"><div class="trunc"><b>{p}</b></div><div class="muted small">{c} courses · {w} · {s}</div></div>{chip("Program")}</div>'
                    for p, w, s, c in PROGRAMS)
    recent = "".join(f'<div class="row">{chip(t)}<div class="grow"><div class="trunc"><b>{n}</b> <span class="muted">· {what}</span></div>'
                     f'<div class="muted small">{who} · {when}</div></div></div>' for t, n, what, when, who in RECENT)
    att = "".join(f'<div class="row"><span class="stat" style="font-size:18px;min-width:30px">{n}</span><span class="grow">{l}</span><a class="small">Fix</a></div>' for n, l in ATTENTION)
    mine = "".join(f'<div class="row">{chip(t)}<span class="grow trunc">{n}</span><span class="muted small">{r}</span></div>' for t, n, r in
                   (("Course", "System Design", "owner"), ("Module", "Caching & load balancing", "owner"), ("Topic", "Tool calling", "SME")))
    hero = ""
    if d["layout"] == "studio":
        hero = f"""<div class="hero"><h1 style="font-size:28px">What are you looking for?</h1>
          <div class="search">{ICON["search"]}<span>Search programs, courses, topics, concepts and sources…</span><kbd>Ctrl K</kbd></div>
          <div class="pillrow">{"".join(f'<span class="chip">{x}</span>' for x in ("RAG pipelines", "Consistent hashing", "MCP servers", "System design interview", "Kafka"))}</div></div>"""
    stats = "".join(f'<div class="card"><div class="muted small">{l}</div><div class="stat">{n}</div></div>' for l, n in
                    (("Programs", "4"), ("Courses", "4"), ("Topics", "2,733"), ("Sources", "1,827")))
    return f"""{hero}<div class="main"><div><h1>Good morning, Alex</h1><div class="sub">What changed, what is yours, and what needs a look.</div></div>
      <div class="grid g4">{stats}</div>
      <div class="grid g2"><div class="card"><h2>Recently changed</h2>{recent}</div><div class="card"><h2>Needs attention <span class="tag-admin">admin</span></h2>{att}</div></div>
      <div class="grid g2"><div class="card"><h2>Programs</h2>{progs}</div><div class="card"><h2>My items</h2>{mine}</div></div></div>"""


def search(d):
    groups = [("Topic", [("Consistent hashing", "System Design › Distributed data", "Used in 3 programs")]),
              ("Concept", [("Hash ring", "Concept under Consistent hashing", "2 sources"), ("Virtual nodes", "Concept under Consistent hashing", "1 source")]),
              ("Resource", [("Distributed data — slides", "Slide 14 of 38 · Google Slides", "“…keys are placed on a ring, so adding a node moves only K/N keys…”"),
                            ("KYP: Applied Agentic AI — Week 6", "Section 3.2 · Confluence, v13", "“…students implement consistent hashing for a sharded cache…”")]),
              ("Module", [("Distributed data", "System Design · 4 topics", "Week 6 in Agentic AI · Week 3 in SprintUP")])]
    body = ""
    for t, items in groups:
        body += f'<div class="group-h">{chip(t, t + "s")}<span class="muted small">{len(items)}</span></div>'
        for n, ctx, extra in items:
            body += f'<div class="res"><div class="grow"><div><b>{n}</b></div><div class="muted small">{ctx}</div><div class="cite">{extra}</div></div><a class="small">Open</a></div>'
    filters = "".join(f'<div class="row"><input type="checkbox" {"checked" if i < 4 else ""}> {chip(t)}</div>' for i, t in enumerate(("Program", "Course", "Module", "Topic", "Concept", "Resource")))
    return f"""<div class="main"><div class="search" style="max-width:none;background:var(--surface)">{ICON["search"]}<b style="color:var(--text)">consistent hashing</b><kbd>Esc</kbd></div>
      <div class="sub">9 results · grouped by kind · sources cite the exact slide, page or section</div>
      <div class="grid" style="grid-template-columns:220px 1fr"><div class="card"><h2>Show</h2>{filters}<h2 style="margin-top:14px">Recent</h2>
        <div class="row small">Vector databases</div><div class="row small">EdgeUp · Data Engineering</div></div><div class="card">{body}</div></div></div>"""


def record(d):
    used = "".join(f'<div class="row"><div class="grow"><b>{p}</b><div class="muted small">{c}</div></div><span class="chip">{w}</span></div>' for p, c, w in
                   (("Applied Agentic AI for Software Engineers", "via System Design › Distributed data", "Week 6 · order 2"),
                    ("SprintUP · Backend Engineering", "via System Design › Distributed data", "Week 3 · order 1"),
                    ("India · Full-Stack Engineering", "via Backend Engineering › Scaling", "Week 11 · order 4")))
    src = "".join(f'<div class="res">{ICON["file"]}<div class="grow"><b>{t}</b><div class="cite"><b>{loc}</b> · {q}</div></div><span class="muted small">{k}</span></div>' for t, loc, q, k in
                  (("Distributed data — slides", "Slide 14", "“adding a node moves only K/N keys”", "Slides"),
                   ("KYP: Applied Agentic AI", "Section 3.2, v13", "“implement consistent hashing for a sharded cache”", "Confluence"),
                   ("Recording: Live session 6", "38:12", "“why modulo hashing breaks when you scale”", "Recording")))
    return f"""<div class="main"><div class="crumbs"><span>Programs</span>›<span>Applied Agentic AI</span>›<b>System Design</b>›<b>Distributed data</b>›<b>Consistent hashing</b></div>
      <div style="display:flex;align-items:center;gap:12px">{chip("Topic")}<h1>Consistent hashing</h1><span class="muted small">reusable · 1 record</span>
        <span style="margin-left:auto;display:flex;gap:8px"><a class="btn">Open in graph</a><a class="btn p">Edit</a></span></div>
      <div class="grid g2"><div style="display:flex;flex-direction:column;gap:16px">
        <div class="card"><h2>Summary</h2><p style="margin:0">Places keys and servers on a ring so that adding or removing a server moves only a small share of keys. Taught as the basis of sharded caches and partitioned stores.</p>
          <div class="pillrow" style="justify-content:flex-start;margin-top:10px">{chip("Concept", "Hash ring")}{chip("Concept", "Virtual nodes")}{chip("Concept", "Rebalancing")}</div></div>
        <div class="card"><h2>Where it's used</h2>{used}<div class="note" style="margin-top:8px">Week and order belong to each program, not to the topic.</div></div>
        <div class="card"><h2>Sources</h2>{src}</div></div>
      <div style="display:flex;flex-direction:column;gap:16px"><div class="card"><h2>People</h2><dl class="kv"><dt>Owners</dt><dd><span class="person"><span class="avatar">AR</span>Alex Rivera</span></dd>
          <dt>Subject experts</dt><dd><span class="person"><span class="avatar">SO</span>Sam Okafor</span> <span class="person"><span class="avatar">JL</span>Jordan Lee</span></dd></dl></div>
        <div class="card"><h2>Related</h2><div class="row"><span class="muted small" style="width:90px">Prerequisite</span>{chip("Topic", "Hash functions")}</div>
          <div class="row"><span class="muted small" style="width:90px">Leads to</span>{chip("Topic", "Sharding")}</div><div class="row"><span class="muted small" style="width:90px">Overlaps</span>{chip("Topic", "Rendezvous hashing")}</div></div>
        <div class="card"><h2>Details</h2><dl class="kv"><dt>Level</dt><dd>Intermediate</dd><dt>Tools</dt><dd>Redis, Cassandra</dd><dt>Updated</dt><dd>12 min ago by Alex Rivera</dd></dl></div></div></div></div>"""


def program(d):
    lanes = [("System Design", [0, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]), ("Backend Engineering", [0, 0, 0, 0, 0, 2, 2, 2, 2, 0, 0, 0, 0, 0, 0, 0]),
             ("RAG & Retrieval", [0, 0, 0, 0, 0, 0, 0, 0, 0, 3, 3, 3, 0, 0, 0, 0]), ("Agents & MCP", [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1])]
    head = '<div></div>' + "".join(f'<div class="w">W{i}</div>' for i in range(1, 17))
    rows = "".join(f'<div class="lane trunc">{n}</div>' + "".join(f'<div class="cell{" on" if v == 1 else " on2" if v == 2 else " on3" if v == 3 else ""}"></div>' for v in cells) for n, cells in lanes)
    courses = "".join(f'<div class="row"><span class="muted" style="width:22px">{i}</span>{chip("Course")}<b class="grow">{c}</b><span class="muted small">{m} modules · weeks {w}</span></div>'
                      for i, (c, m, w) in enumerate((("System Design", 4, "2–5"), ("Backend Engineering", 5, "6–9"), ("RAG & Retrieval", 3, "10–12"), ("Agents & MCP", 4, "13–16")), 1))
    return f"""<div class="main"><div class="crumbs"><span>Programs</span>›<b>Applied Agentic AI for Software Engineers</b></div>
      <div style="display:flex;align-items:center;gap:12px">{chip("Program")}<h1>Applied Agentic AI for Software Engineers</h1>
        <span style="margin-left:auto;display:flex;gap:8px"><a class="btn">Compare with…</a><a class="btn p">Add existing course</a></span></div>
      <div class="sub">16 weeks · Sept 2026 cohort · schedule from KYP v13 (Confluence, updated 2 days ago)</div>
      <div class="card"><h2>Schedule</h2><div class="timeline">{head}{rows}</div></div>
      <div class="grid g2"><div class="card"><h2>Courses, in order</h2>{courses}</div>
        <div class="card"><h2>Coverage</h2><div class="row"><span class="grow">Topics with sources</span><span>82%</span></div><div class="bar"><i style="width:82%"></i></div>
          <div class="row"><span class="grow">Shared with other programs</span><span>11 of 16 modules</span></div><div class="row"><span class="grow">Missing vs the KYP</span><a>3 topics</a></div></div></div></div>"""


def page(key, d):
    dark = " dark" if key == "b" else ""
    screens = [("home", "Home", home), ("search", "Search results", search), ("record", "Record page", record), ("program", "Program view", program)]
    out = []
    for sid, title, fn in screens:
        lay = d["layout"]
        if lay == "sidebar":
            out.append(f'<section class="screen app-sidebar" id="{sid}">{side(sid)}<div>{fn(d)}</div></section>')
        else:
            out.append(f'<section class="screen app-{lay}" id="{sid}">{topbar(sid, d)}<div>{fn(d)}</div></section>')
    links = "".join(f'<a href="#{s}">{t}</a>' for s, t, _ in screens)
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Direction {d["name"]} · IK Knowledge Base mockups</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>:root{{{d["tokens"]}--font:{d["font"]}}}{CSS}</style></head><body class="{dark.strip()}">
<div class="switch"><span class="t">Direction {d["name"]}</span>{links}<span style="margin-left:12px;color:#999">{d["tag"]}</span></div>
{"".join(out)}
<p style="padding:16px 28px;color:#888;font-size:12px">Static mockup with fictional content. Not connected to any data.</p></body></html>"""


if __name__ == "__main__":
    for k, d in DIRECTIONS.items():
        (HERE / f"direction-{k}.html").write_text(page(k, d), encoding="utf-8")
        print("wrote", HERE / f"direction-{k}.html")
