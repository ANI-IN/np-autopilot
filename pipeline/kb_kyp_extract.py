#!/usr/bin/env python3
"""Fetch the KYP pages from Confluence and extract the curriculum structure.
READ-ONLY on Confluence (GET only). Writes local, gitignored files only.

    python pipeline/kb_kyp_extract.py [--out .measure/kyp-c] [--offline]

KYPs are the primary reference for curriculum STRUCTURE (owner decision
2026-11-07): programs, courses, modules, their order, topics, tools, the listed
instructors, owner notes, resources. They are parsed as structure, not stored
as documents. Scope and domain names come from config/kb-curriculum-scope.yaml.

1. Lists every page under the KYP starting points with its current version
   (for the Sources page), flags "[Do not Use]" pages and lists attachments
   (never downloaded).
2. Fetches the in-scope pages and the pages they include at their CURRENT
   version; a page whose version did not change is read from the cache.
3. Extracts, per family shape:
   * curriculum-table: rows "Week | Module | Agenda". "Course - Module" titles
     name their course; the agenda's items are the topics.
   * kyp-with-outline: the KYP page includes an outline page; each outline row
     is a course (column 2) whose nested list holds modules (bold items with
     children) and topics (their leaf items).
   * module-table: a reusable domain course page, rows "No | Module | Agenda".
4. Writes curriculum.json: programs, courses, modules (with a content hash so an
   identical module in several programs is ONE module, and a same-titled module
   with different content is a variant), placements (order and the optional,
   program-specific week label), topics, concepts (tools), resources, listed
   instructors, owner notes, skipped pages and attachments, ambiguities.

Every extracted item carries its provenance: page id, page version, heading,
table and row. Nothing is invented: a row that does not fit a shape is reported
as an ambiguity, not guessed.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
SCOPE = yaml.safe_load((REPO / "config" / "kb-curriculum-scope.yaml").read_text(encoding="utf-8"))
DASH = "–—-"


def norm(s: str | None) -> str:
    return re.sub(r"\s+", " ", (s or "").replace(" ", " ")).strip()


def key(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", norm(s).lower()).strip("-")


def h(s: str, n: int = 10) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:n]


# ---------------------------------------------------------------- Confluence
class Confluence:
    def __init__(self, offline: bool):
        self.offline = offline
        if offline:
            return
        from dotenv import dotenv_values
        env = dotenv_values(REPO / ".env")
        site = (env.get("CONFLUENCE_BASE_URL") or "").rstrip("/")
        if not site or not env.get("CONFLUENCE_API_TOKEN"):
            sys.exit("CONFLUENCE_BASE_URL / CONFLUENCE_EMAIL / CONFLUENCE_API_TOKEN are not set")
        self.auth = "Basic " + base64.b64encode(f"{env['CONFLUENCE_EMAIL']}:{env['CONFLUENCE_API_TOKEN']}".encode()).decode()
        self.site = site
        del env
        with urllib.request.urlopen(site + "/_edge/tenant_info", timeout=30) as r:
            cloud = json.load(r)["cloudId"]
        self.api = f"https://api.atlassian.com/ex/confluence/{cloud}/wiki"
        self.calls = 0

    def get(self, path: str):
        url = path if path.startswith("http") else self.api + path
        for _ in range(5):
            req = urllib.request.Request(url, headers={"Accept": "application/json", "Authorization": self.auth})
            try:
                self.calls += 1
                with urllib.request.urlopen(req, timeout=60) as r:
                    return r.status, json.load(r)
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    time.sleep(int(e.headers.get("Retry-After", "5")))
                    continue
                return e.code, {}
            except (urllib.error.URLError, TimeoutError):
                time.sleep(3)
        return 0, {}

    def page_url(self, pid: str) -> str:
        return f"{self.site}/wiki/pages/viewpage.action?pageId={pid}" if not self.offline else f"confluence:page:{pid}"


# ---------------------------------------------------------------- storage-format parsing
def parse(body: str):
    import lxml.html as LH
    return LH.fromstring("<div>" + body + "</div>")


def text(el) -> str:
    return norm(" ".join(t.strip() for t in el.itertext() if t.strip()))


def own_text(li) -> str:
    """The text of a list item without its nested lists."""
    parts = []

    def rec(e):
        for c in e:
            if c.tag in ("ul", "ol"):
                continue
            if c.text:
                parts.append(c.text)
            rec(c)
            if c.tail:
                parts.append(c.tail)
    if li.text:
        parts.append(li.text)
    rec(li)
    return norm(" ".join(parts))


def owner_table(el):
    p = el.getparent()
    while p is not None and p.tag != "table":
        p = p.getparent()
    return p


def table_rows(t):
    return [[c for c in tr if c.tag in ("td", "th")] for tr in t.iter("tr") if owner_table(tr) is t]


def cell_items(c) -> list[str]:
    lis = [own_text(li) for li in c.iter("li")]
    if lis:
        return [x for x in lis if x]
    ps = [x for x in (text(p) for p in c.iter("p")) if x]
    return ps or ([text(c)] if text(c) else [])


def sections(root):
    """[(h2, h3, element)] in document order for top-level blocks (tables, lists, paragraphs)."""
    out, cur = [], {"h2": None, "h3": None}

    def rec(el, depth=0):
        for c in el:
            tag = c.tag if isinstance(c.tag, str) else ""
            if tag == "ac:adf-fallback":
                continue
            if tag in ("h1", "h2"):
                cur["h2"], cur["h3"] = text(c), None
                continue
            if tag in ("h3", "h4", "h5"):
                cur["h3"] = text(c)
                continue
            if tag in ("table", "ul", "ol", "p"):
                out.append((cur["h2"], cur["h3"], c))
                if tag == "table":
                    continue
                if tag in ("ul", "ol"):
                    continue
            rec(c, depth + 1)
    rec(root)
    return out


def links_of(el) -> list[tuple[str, str]]:
    out = []
    for a in el.iter("a"):
        href = a.get("href") or ""
        if href.startswith("http"):
            out.append((href, text(a)))
    return out


WEEK = re.compile(r"^(?:week\s*)?(F)?(\d+)(?:\s*[" + DASH + r"]\s*(\d+))?(\+| onwards)?", re.I)


def parse_week(label: str) -> dict:
    """The program-specific schedule label, kept as optional data on the placement."""
    lab = norm(label)
    m = WEEK.match(lab)
    if not m:
        return {"label": lab or None}
    a = int(m.group(2))
    b = int(m.group(3)) if m.group(3) else a
    out = {"label": lab}
    if m.group(1):
        out["floater"] = True
    else:
        out.update(start=a, end=b)
    if re.search(r"self.?paced", lab, re.I):
        out["self_paced"] = True
    if re.search(r"\blive\b", lab, re.I):
        out["live"] = True
    return out


# ---------------------------------------------------------------- extraction
class Extract:
    def __init__(self, cf: Confluence, out: Path):
        self.cf, self.out = cf, out
        self.raw = out / "raw"
        self.raw.mkdir(parents=True, exist_ok=True)
        self.D = {"programs": [], "courses": [], "modules": {}, "placements": [], "program_courses": [],
                  "topics": [], "concepts": [], "resources": [], "instructors": [], "owner_notes": [],
                  "pages": [], "skipped": [], "attachments": [], "ambiguities": [], "deferred": []}
        self.domains = SCOPE["domains"]

    # ---- domain from a title (longest alias wins; whole-word, case-insensitive)
    def domain_of(self, s: str) -> str | None:
        best = None
        for d in self.domains:
            for a in [d["name"]] + d["aliases"]:
                if re.search(r"(?<![A-Za-z])" + re.escape(a) + r"(?![A-Za-z])", s or "", re.I):
                    if best is None or len(a) > best[1]:
                        best = (d["name"], len(a))
        return best[0] if best else None

    # ---- fetching with a version cache
    def page(self, pid: str, known_version: int | None = None) -> dict | None:
        cache = self.raw / f"{pid}.json"
        if cache.exists():
            c = json.loads(cache.read_text(encoding="utf-8"))
            if self.cf.offline or (known_version is not None and c["version"]["number"] == known_version):
                c["_from_cache"] = True
                return c
        if self.cf.offline:
            return None
        code, p = self.cf.get(f"/api/v2/pages/{pid}?body-format=storage")
        if code != 200:
            self.D["ambiguities"].append({"page_id": pid, "issue": f"page could not be fetched (HTTP {code})"})
            return None
        cache.write_text(json.dumps(p, ensure_ascii=False), encoding="utf-8")
        return p

    def prov(self, p, heading=None, table=None, row=None, **extra):
        d = {"source": "confluence", "page_id": p["id"], "page_title": p["title"], "page_version": p["version"]["number"],
             "page_modified": p["version"].get("createdAt"), "url": self.cf.page_url(p["id"])}
        if heading:
            d["heading"] = heading
        if table:
            d["table"] = table
        if row is not None:
            d["row"] = row
        d.update({k: v for k, v in extra.items() if v is not None})
        return d

    # ---- listing (every page under the starting points, with current versions)
    def listing(self, structure: dict):
        dnu = re.compile(SCOPE["do_not_use_pattern"], re.I)
        deferred = [re.compile(x, re.I) for x in SCOPE["deferred_title_patterns"]]
        for p in structure["pages"]:
            cur_v, cur_mod = p["version"], p["last_modified"]
            if not self.cf.offline:
                code, m = self.cf.get(f"/api/v2/pages/{p['id']}")
                if code == 200:
                    cur_v, cur_mod = m["version"]["number"], m["version"].get("createdAt")
                else:
                    self.D["ambiguities"].append({"page_id": p["id"], "issue": f"page metadata could not be refreshed (HTTP {code})"})
            row = {"page_id": p["id"], "title": p["title"], "root": p["root"], "depth": p["depth"],
                   "version": cur_v, "modified": cur_mod, "version_at_previous_crawl": p["version"],
                   "changed_since_previous_crawl": cur_v != p["version"], "url": self.cf.page_url(p["id"]),
                   "do_not_use": bool(p.get("do_not_use") or dnu.search(p["title"])),
                   "deferred": any(x.search(p["title"]) or x.search(p["root"] or "") for x in deferred),
                   "attachments": len(p.get("attachments") or [])}
            self.D["pages"].append(row)
            if row["do_not_use"]:
                self.D["skipped"].append({"kind": "page", "page_id": p["id"], "title": p["title"], "url": row["url"],
                                          "reason": "marked [Do not Use]"})
            for a in p.get("attachments") or []:
                self.D["attachments"].append({"on_page_id": p["id"], "on_page_title": p["title"], "name": a.get("name"),
                                              "media_type": a.get("mediaType"), "size_bytes": a.get("size"),
                                              "reason": "attachment listed only (not downloaded)"})

    # ---- program record
    def program(self, p, family, name, domain, extra_pages=()):
        prog = {"key": "kyp:program:" + p["id"], "name": name, "family": family, "domain": domain,
                "provenance": self.prov(p), "also_from": [self.prov(x) for x in extra_pages], "attributes": {}}
        self.D["programs"].append(prog)
        return prog

    def course(self, prog, name, order, p, heading, table, row, domain):
        c = {"key": f"kyp:course:{prog['key'].split(':')[-1] if prog else 'shared'}:{key(name)}", "name": name,
             "program": prog["key"] if prog else None, "order": order, "domain": domain,
             "provenance": self.prov(p, heading, table, row)}
        self.D["courses"].append(c)
        if prog:
            self.D["program_courses"].append({"program": prog["key"], "course": c["key"], "order": order,
                                              "provenance": c["provenance"]})
        return c

    def module(self, name, topics, domain, p, heading, table, row):
        """One module per (title, content). Same title + other content = a variant."""
        title = norm(name)
        sig = h(key(title) + "|" + "|".join(key(t) for t in topics))
        mk = f"kyp:module:{key(title)}:{sig}"
        m = self.D["modules"].get(mk)
        pv = self.prov(p, heading, table, row)
        if m is None:
            m = self.D["modules"][mk] = {"key": mk, "name": title, "title_key": key(title), "content_sig": sig,
                                         "domains": [], "topics": [], "provenance": [pv]}
            for i, t in enumerate(topics, 1):
                self.D["topics"].append({"key": f"{mk}:t{i}", "module": mk, "name": t[:300], "order": i, "provenance": pv})
                m["topics"].append(f"{mk}:t{i}")
        else:
            m["provenance"].append(pv)
        if domain and domain not in m["domains"]:
            m["domains"].append(domain)
        return m

    def place(self, course, module, order, week, p, heading, table, row):
        self.D["placements"].append({"course": course["key"], "module": module["key"], "order": order,
                                     "schedule": {k: v for k, v in week.items() if v is not None} if week else None,
                                     "provenance": self.prov(p, heading, table, row)})

    # ---- common sections (instructors, tools, owner notes, links)
    def common(self, p, prog, root):
        for h2, h3, el in sections(root):
            hh = h2 or ""
            if re.search(r"Instructors", hh, re.I):
                for item in (cell_items(el) if el.tag != "table" else [x for r in table_rows(el) for c in r for x in cell_items(c)]):
                    m = re.match(r"^([A-Z][\w.'\-]+(?: [A-Z][\w.'\-]+){1,3})\s*,", item)
                    if m:
                        self.D["instructors"].append({"name": m.group(1), "program": prog["key"], "listing": item[:200],
                                                      "provenance": self.prov(p, hh)})
            if re.search(r"Tools\s*&\s*tech", hh, re.I) and el.tag == "table":
                rs = table_rows(el)
                hdr = [text(c).lower() for c in rs[0]] if rs else []
                if len(hdr) >= 2 and "tool" in " ".join(hdr):
                    for ri, r in enumerate(rs[1:], 1):
                        cat = text(r[0])
                        for tool in re.split(r",|;|\n", text(r[1])):
                            if norm(tool):
                                self.D["concepts"].append({"name": norm(tool), "kind": "tool", "category": cat,
                                                           "program": prog["key"], "provenance": self.prov(p, hh, "tools", ri)})
            t = text(el)
            for m in re.finditer(r"[Oo]wned by ([A-Z][a-z]+(?: [A-Z][a-z]+)?)", t):
                self.D["owner_notes"].append({"program": prog["key"], "section": hh, "name": m.group(1),
                                              "note": t[:160], "provenance": self.prov(p, hh)})
            for href, label in links_of(el):
                if re.search(r"(docs|drive)\.google\.com", href):
                    self.D["resources"].append({"url": href, "title": label or None, "program": prog["key"],
                                                "section": hh, "provenance": self.prov(p, hh)})
        sched = []
        for h2, h3, el in sections(root):
            if re.search(r"^\d*\.?\s*Schedule", h2 or "", re.I) and el.tag == "table":
                for r in table_rows(el)[1:]:
                    vals = [text(c) for c in r]
                    if len(vals) >= 2 and vals[0]:
                        sched.append({"when": vals[0], "what": vals[1]})
        if sched:
            prog["attributes"]["weekly_cadence"] = sched

    # ---- shape 1: Week | Module | Agenda
    def curriculum_table(self, p, prog, domain):
        root = parse(p["body"]["storage"]["value"])
        self.common(p, prog, root)
        courses = {}
        corder = 0
        morder = {}
        found = False
        for h2, h3, el in sections(root):
            if el.tag != "table" or not re.search(r"curriculum", h2 or "", re.I):
                continue
            rs = table_rows(el)
            hdr = [text(c) for c in rs[0]] if rs else []
            if not (len(hdr) >= 3 and re.search(r"week", hdr[0], re.I) and re.search(r"module", hdr[1], re.I)):
                continue
            found = True
            tname = " | ".join(hdr)
            for ri, r in enumerate(rs[1:], 1):
                vals = [text(c) for c in r]
                if len(vals) < 3 or not vals[1]:
                    self.D["ambiguities"].append({"page_id": p["id"], "row": ri, "issue": "curriculum row without a module title"})
                    continue
                title = vals[1]
                week = parse_week(vals[0])
                opt = re.search(r"\s*\((optional)\)\s*$", title, re.I)
                if opt:
                    title = title[:opt.start()].strip()
                    week["optional"] = True
                # "Course - Module" or "Course: Module" names the course; a bare title has none
                m = re.match(r"^(.+?)\s+[" + DASH + r"]\s+(.+)$", title) or re.match(r"^([^:]{3,40}):\s*(.+)$", title)
                cname, mname = (norm(m.group(1)), norm(m.group(2))) if m else (None, title)
                topics = cell_items(r[2])
                if cname:
                    if cname not in courses:
                        corder += 1
                        courses[cname] = self.course(prog, cname, corder, p, h2, tname, ri, self.domain_of(cname))
                    c = courses[cname]
                else:
                    c = None
                mdom = self.domain_of(cname) if cname else None
                mod = self.module(mname, topics, mdom, p, h2, tname, ri)
                if c is not None:
                    morder[c["key"]] = morder.get(c["key"], 0) + 1
                    self.place(c, mod, morder[c["key"]], week, p, h2, tname, ri)
                else:
                    morder[prog["key"]] = morder.get(prog["key"], 0) + 1
                    self.D["placements"].append({"program": prog["key"], "module": mod["key"], "order": ri,
                                                 "schedule": week, "provenance": self.prov(p, h2, tname, ri)})
        if not found:
            self.D["ambiguities"].append({"page_id": p["id"], "issue": "no Week | Module | Agenda curriculum table"})

    # ---- shape 2: KYP page including an outline page
    def kyp_with_outline(self, p, prog, domain, outline):
        root = parse(p["body"]["storage"]["value"])
        self.common(p, prog, root)
        if outline is None:
            self.D["ambiguities"].append({"page_id": p["id"], "issue": "the included course outline could not be read"})
            return
        oroot = parse(outline["body"]["storage"]["value"])
        self.common(outline, prog, oroot)
        corder = 0
        seen, morder = {}, {}
        for h2, h3, el in sections(oroot):
            if el.tag != "table":
                continue
            rs = table_rows(el)
            hdr = [text(c) for c in rs[0]] if rs else []
            if not (len(hdr) >= 3 and re.search(r"week|date", hdr[0], re.I)):
                continue
            tname = " | ".join(hdr)
            for ri, r in enumerate(rs[1:], 1):
                if len(r) < 3:
                    continue
                week = parse_week(" ".join(cell_items(r[0])))
                cname = text(r[1])
                struct = r[2]
                mods = self.nested_modules(struct)
                if not cname:
                    # a row with no course: program-level items (orientation, careers, support period)
                    for mname, tops in (mods or [(text(struct), [])]):
                        if not mname:
                            continue
                        mod = self.module(mname, tops, None, outline, h3 or h2, tname, ri)
                        self.D["placements"].append({"program": prog["key"], "module": mod["key"], "order": ri,
                                                     "schedule": week, "provenance": self.prov(outline, h3 or h2, tname, ri)})
                    continue
                # consecutive week rows naming the same course are ONE course of this program
                c = seen.get(key(cname))
                if c is None:
                    corder += 1
                    c = seen[key(cname)] = self.course(prog, cname, corder, outline, h3 or h2, tname, ri, self.domain_of(cname))
                    c["schedule_rows"] = []
                c["schedule_rows"].append(week)
                if not mods:
                    tops = cell_items(struct)
                    mods = [(cname, tops)]
                    self.D["ambiguities"].append({"page_id": outline["id"], "row": ri,
                                                  "issue": f"course '{cname}' row has no module heading; kept as one module of the course's name"})
                for mname, tops in mods:
                    mod = self.module(mname, tops, self.domain_of(cname), outline, h3 or h2, tname, ri)
                    morder[c["key"]] = morder.get(c["key"], 0) + 1
                    self.place(c, mod, morder[c["key"]], week, outline, h3 or h2, tname, ri)

    @staticmethod
    def nested_modules(cell) -> list[tuple[str, list[str]]]:
        """Two shapes the outlines use, tried in order:
        (a) a list item whose nested list holds only leaves: the item is the module, the leaves its topics;
        (b) a fully bold paragraph followed by a list: the paragraph is the module, the list items its topics."""
        out = []
        for li in cell.iter("li"):
            subs = [x for x in li if x.tag in ("ul", "ol")]
            if not subs:
                continue
            kids = [k for s in subs for k in s if k.tag == "li"]
            if kids and all(not any(x.tag in ("ul", "ol") for x in k) for k in kids):
                name = own_text(li).rstrip(":").strip()
                out.append((name, [own_text(k) for k in kids if own_text(k)]))
        if out:
            return out
        kids = list(cell)
        for i, c in enumerate(kids):
            if c.tag != "p":
                continue
            bold = "".join(text(b) for b in c.iter("strong", "b"))
            if not bold or norm(bold) != text(c):
                continue
            nxt = kids[i + 1] if i + 1 < len(kids) else None
            if nxt is not None and nxt.tag in ("ul", "ol"):
                out.append((text(c).rstrip(":").strip(), [own_text(li) for li in nxt.iter("li") if own_text(li)]))
        return out

    # ---- shape 3: reusable domain course page
    def module_table(self, p, cname, domain):
        root = parse(p["body"]["storage"]["value"])
        c = self.course(None, cname, None, p, None, None, None, domain)
        c["key"] = "kyp:course:" + p["id"]
        c["reusable"] = True
        for h2, h3, el in sections(root):
            if el.tag != "table":
                continue
            rs = table_rows(el)
            hdr = [text(x) for x in rs[0]] if rs else []
            if not (len(hdr) >= 3 and re.search(r"module", hdr[1], re.I)):
                continue
            tname = " | ".join(hdr)
            for ri, r in enumerate(rs[1:], 1):
                vals = [text(x) for x in r]
                if len(vals) < 3 or not vals[1]:
                    continue
                mod = self.module(vals[1], cell_items(r[2]), domain, p, h2, tname, ri)
                self.place(c, mod, ri, None, p, h2, tname, ri)
        return c

    # ---- run
    def run(self, structure: dict, includes: dict):
        self.listing(structure)
        fam = SCOPE["families"]
        P = {p["page_id"]: p for p in self.D["pages"]}
        by_title = {norm(p["title"]): p for p in self.D["pages"]}
        deferred = [re.compile(x, re.I) for x in SCOPE["deferred_title_patterns"]]
        for row in self.D["pages"]:
            if row["do_not_use"]:
                continue
            if row["deferred"]:
                self.D["deferred"].append({"page_id": row["page_id"], "title": row["title"], "root": row["root"],
                                           "url": row["url"], "reason": "Agentic AI / combined / PM-TPM-EM program: deferred in this run"})
                continue
            dom = self.domain_of(row["title"])
            if row["root"] == fam["ip-2026"]["root_label"] and re.search(fam["ip-2026"]["title"], row["title"], re.I):
                if not dom:
                    continue
                p = self.page(row["page_id"], row["version"])
                if p:
                    prog = self.program(p, "Interview Preparation 2026", norm(p["title"]), dom)
                    self.curriculum_table(p, prog, dom)
            elif row["root"] == fam["india"]["root_label"] and re.search(fam["india"]["title"], row["title"], re.I):
                if not dom:
                    continue
                p = self.page(row["page_id"], row["version"])
                if not p:
                    continue
                inc = re.findall(r'<ri:page ri:content-title="([^"]+)"', p["body"]["storage"]["value"])
                outline = None
                for t in inc:
                    o = by_title.get(norm(t.replace("&amp;", "&")))
                    if o and re.search(r"outline", t, re.I):
                        outline = self.page(o["page_id"], o["version"])
                name = re.sub(r"\s*KYP$", "", norm(p["title"]))
                prog = self.program(p, "Interview Preparation India", name, dom, [outline] if outline else [])
                self.kyp_with_outline(p, prog, dom, outline)
        # reusable domain courses (included by the deferred SprintUP wrappers)
        rx = re.compile(fam["sprintup-domain-course"]["include_title"])
        for title, info in sorted(includes.items()):
            m = rx.match(norm(title))
            if not m or info.get("status") != 200:
                continue
            dom = self.domain_of(m.group(1))
            if not dom:
                continue
            p = self.page(info["id"], info.get("version"))
            if p:
                self.module_table(p, norm(re.sub(r"^Module\s*-\s*", "", title)), dom)
        self.finish()

    def merge_repeats(self):
        """The same module title placed more than once in ONE course (or one program's own list) is one
        module taught over several weeks: its rows merge into one module, topics in row order."""
        D = self.D
        groups = {}
        for pl in D["placements"]:
            cont = pl.get("course") or pl.get("program")
            groups.setdefault((cont, D["modules"][pl["module"]]["title_key"]), []).append(pl)
        for (cont, tk), pls in groups.items():
            mks = list(dict.fromkeys(pl["module"] for pl in pls))
            if len(pls) < 2:
                continue
            parts = [D["modules"][k] for k in mks]
            names, seen = [], set()
            for pl in pls:
                for t in [t for t in D["topics"] if t["module"] == pl["module"]]:
                    if key(t["name"]) not in seen:
                        seen.add(key(t["name"]))
                        names.append((t["name"], t["provenance"]))
            sig = h(tk + "|" + "|".join(key(n) for n, _ in names))
            mk = f"kyp:module:{tk}:{sig}"
            if mk not in D["modules"]:
                D["modules"][mk] = {"key": mk, "name": parts[0]["name"], "title_key": tk, "content_sig": sig,
                                    "domains": sorted({d for m in parts for d in m["domains"]}), "topics": [],
                                    "provenance": [pl["provenance"] for pl in pls], "merged_rows": len(pls)}
                for i, (n, pv) in enumerate(names, 1):
                    D["topics"].append({"key": f"{mk}:t{i}", "module": mk, "name": n, "order": i, "provenance": pv})
                    D["modules"][mk]["topics"].append(f"{mk}:t{i}")
            first = pls[0]
            first["module"] = mk
            first["schedule_rows"] = [pl.get("schedule") for pl in pls]
            for pl in pls[1:]:
                D["placements"].remove(pl)
            D["ambiguities"].append({"page_id": first["provenance"]["page_id"], "row": first["provenance"].get("row"),
                                     "issue": f"module '{parts[0]['name']}' appears on {len(pls)} rows of one course; merged into one module"})
        # drop modules no placement uses any more
        used = {pl["module"] for pl in D["placements"]}
        for k in [k for k in D["modules"] if k not in used]:
            del D["modules"][k]
        D["topics"] = [t for t in D["topics"] if t["module"] in used]

    def finish(self):
        D = self.D
        self.merge_repeats()
        # variants: same title, different content -> link every other variant to one canonical
        by_title = {}
        for m in D["modules"].values():
            by_title.setdefault(m["title_key"], []).append(m)
        for ms in by_title.values():
            if len(ms) > 1:
                ms.sort(key=lambda m: (-len(m["provenance"]), m["provenance"][0]["page_id"]))
                for v in ms[1:]:
                    v["variant_of"] = ms[0]["key"]
        D["modules"] = list(D["modules"].values())
        D["generated"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        D["confluence_calls"] = getattr(self.cf, "calls", 0)
        (self.out / "curriculum.json").write_text(json.dumps(D, indent=1, ensure_ascii=False), encoding="utf-8")
        print(json.dumps({k: len(v) for k, v in D.items() if isinstance(v, list)}, indent=1))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", default=str(REPO / ".measure" / "kyp-c"))
    ap.add_argument("--structure", default=str(REPO / ".measure" / "kyp" / "kyp_structure.json"),
                    help="the earlier page listing (local, gitignored); every page in it is re-checked")
    ap.add_argument("--includes", default=str(REPO / ".measure" / "kyp" / "raw" / "includes_resolved.json"))
    ap.add_argument("--offline", action="store_true", help="use cached pages only")
    a = ap.parse_args(argv)
    out = Path(a.out).resolve()
    if REPO in out.parents and ".measure" not in out.parts:
        sys.exit("outputs hold real data: write them under .measure/")
    out.mkdir(parents=True, exist_ok=True)
    structure = json.loads(Path(a.structure).read_text(encoding="utf-8"))
    includes = json.loads(Path(a.includes).read_text(encoding="utf-8"))
    Extract(Confluence(a.offline), out).run(structure, includes)


if __name__ == "__main__":
    main()
