#!/usr/bin/env python3
"""Crawl everything the registry sheet points at. READ-ONLY on Google, always.

    python pipeline/kb_registry_crawl.py [--out .measure/sources] [--workers 6]
                                         [--max-download-mb 60] [--no-extract]

The registry sheet (KB_SHEETS_ID) is the single source of truth for which
sources exist (owner decision 2026-11-07). This tool:

1. reads the registry through the **Sheets API** (not a Drive export): every tab,
   column and row, with the hyperlinks embedded in cells (cell links, rich-text
   runs and smart chips);
2. follows every link: spreadsheets (all tabs, their links followed one more
   level), Drive folders (recursively, shared drives included), Docs, Slides,
   PDFs, Word, PowerPoint and Excel files, shortcuts (to their targets);
3. extracts text from Docs, Slides, Sheets, PDF, Word, PowerPoint and Excel as a
   first pass. Audio and video are counted and sized only;
4. records every access failure (permission, 404, unsupported format, missing
   shortcut target, too large for the first pass) with the link and the reason.

Outputs (all local, gitignored, real data): ``catalog.json`` (one row per source:
live URL, resource id, version / modified time, md5, size, provenance chain,
status), ``failures.json``, ``links.json`` and ``text/<id>.txt``. The text files
are a processing CACHE, never the source of truth: a re-crawl compares each
resource's version and modified time by id, re-extracts what changed and marks
what disappeared.

Credentials: the service-account key PATH in NP_DRIVE_SA_KEY (outside the repo),
scopes drive.readonly and spreadsheets.readonly. Nothing is printed but counts.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import sys
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCOPES = ["https://www.googleapis.com/auth/drive.readonly",
          "https://www.googleapis.com/auth/spreadsheets.readonly"]
DRIVE = "https://www.googleapis.com/drive/v3"
SHEETS = "https://sheets.googleapis.com/v4/spreadsheets"
FOLDER = "application/vnd.google-apps.folder"
SHORTCUT = "application/vnd.google-apps.shortcut"
G = "application/vnd.google-apps."
ITEM_CAP = 60000

# What the first pass extracts, by MIME type -> extractor name.
EXTRACT = {
    G + "document": "gdoc", G + "presentation": "gslides", G + "spreadsheet": "gsheet",
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": "pptx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
}
# Formats recognised as documents but not readable by the first pass: reported, not skipped silently.
UNSUPPORTED_DOCS = {"application/msword": "legacy .doc", "application/vnd.ms-powerpoint": "legacy .ppt",
                    "application/vnd.ms-excel": "legacy .xls"}

ID = r"([A-Za-z0-9_-]{10,})"
PATTERNS = [
    ("spreadsheet", re.compile(r"docs\.google\.com/spreadsheets/(?:u/\d+/)?d/" + ID)),
    ("document", re.compile(r"docs\.google\.com/document/(?:u/\d+/)?d/" + ID)),
    ("presentation", re.compile(r"docs\.google\.com/presentation/(?:u/\d+/)?d/" + ID)),
    ("form", re.compile(r"docs\.google\.com/forms/(?:u/\d+/)?d/(?:e/)?" + ID)),
    ("drawing", re.compile(r"docs\.google\.com/drawings/(?:u/\d+/)?d/" + ID)),
    ("folder", re.compile(r"drive\.google\.com/(?:drive/)?(?:u/\d+/)?(?:mobile/)?folders/" + ID)),
    ("folder", re.compile(r"drive\.google\.com/folderview\?(?:[^ \"']*&)?id=" + ID)),
    ("file", re.compile(r"drive\.google\.com/file/(?:u/\d+/)?d/" + ID)),
    ("file", re.compile(r"drive\.google\.com/(?:open|uc)\?(?:[^ \"']*&)?id=" + ID)),
]
URL_RE = re.compile(r"https?://[^\s\"'<>)\]]+")


def live_url(kind_or_mime: str, rid: str) -> str:
    k = kind_or_mime
    if k in ("folder", FOLDER):
        return f"https://drive.google.com/drive/folders/{rid}"
    if k in ("spreadsheet", G + "spreadsheet"):
        return f"https://docs.google.com/spreadsheets/d/{rid}"
    if k in ("document", G + "document"):
        return f"https://docs.google.com/document/d/{rid}"
    if k in ("presentation", G + "presentation"):
        return f"https://docs.google.com/presentation/d/{rid}"
    if k in ("form", G + "form"):
        return f"https://docs.google.com/forms/d/{rid}"
    return f"https://drive.google.com/file/d/{rid}"


def links_in(text: str) -> list[tuple[str, str | None, str]]:
    """(kind, id, url) for every URL in a string; non-Google URLs come back with kind 'web'."""
    out = []
    if not isinstance(text, str) or "http" not in text:
        return out
    for m in URL_RE.finditer(text):
        url = m.group(0).rstrip(".,;")
        hit = None
        for kind, p in PATTERNS:
            mm = p.search(url)
            if mm:
                hit = (kind, mm.group(1), url)
                break
        out.append(hit or ("web", None, url))
    return out


def col_letter(i: int) -> str:
    s, i = "", i + 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


class ApiError(Exception):
    def __init__(self, status, reason, msg=""):
        super().__init__(f"{status} {reason}")
        self.status, self.reason, self.msg = status, reason, msg


def reason_of(e: ApiError) -> str:
    if e.status == 404:
        return "not found or not shared with the service account (Drive answers 404 for both)"
    if e.status == 403:
        return f"permission denied ({e.reason or 'forbidden'})"
    if e.status == 400:
        return f"bad request ({e.reason or 'invalid'})"
    return f"HTTP {e.status} {e.reason}".strip()


class Crawler:
    def __init__(self, out: Path, workers: int, max_mb: int, extract: bool):
        from dotenv import dotenv_values
        from google.auth.transport.requests import AuthorizedSession
        from google.oauth2 import service_account
        env = dotenv_values(REPO / ".env")
        key = Path(os.path.expanduser(env.get("NP_DRIVE_SA_KEY") or os.environ.get("NP_DRIVE_SA_KEY") or "")).resolve()
        if not key.is_file():
            sys.exit("NP_DRIVE_SA_KEY must name a service-account key file")
        if REPO in key.parents:
            sys.exit("refusing a key file inside the repository")
        self.registry_id = (env.get("KB_SHEETS_ID") or os.environ.get("KB_SHEETS_ID") or "").strip()
        if not self.registry_id:
            sys.exit("KB_SHEETS_ID is empty: set it to the registry sheet's id")
        del env
        self.creds = service_account.Credentials.from_service_account_file(str(key), scopes=SCOPES)
        self._local = threading.local()
        self._AuthorizedSession = AuthorizedSession
        self.out, self.workers, self.max_bytes, self.do_extract = out, workers, max_mb * 1024 * 1024, extract
        (out / "text").mkdir(parents=True, exist_ok=True)
        prev = out / "catalog.json"
        self.previous = {r["resource_id"]: r for r in json.loads(prev.read_text(encoding="utf-8"))["items"]} if prev.exists() else {}
        self.items: dict[str, dict] = {}
        self.links: list[dict] = []
        self.failures: list[dict] = []
        self.sheets: dict[str, dict] = {}
        self.stats = Counter()
        self.lock = threading.Lock()
        self.capped = False

    # ---------------- HTTP ----------------
    @property
    def S(self):
        s = getattr(self._local, "s", None)
        if s is None:
            s = self._local.s = self._AuthorizedSession(self.creds)
        return s

    def get(self, url, params=None, raw=False):
        import requests
        delay = 1.0
        for _ in range(7):
            try:
                r = self.S.get(url, params=params, timeout=180)
            except (requests.ConnectionError, requests.Timeout):
                self.stats["retry_conn"] += 1
                time.sleep(delay); delay *= 2
                continue
            self.stats["requests"] += 1
            if r.status_code == 200:
                return r.content if raw else r.json()
            if r.status_code in (429, 500, 502, 503, 504) or (r.status_code == 403 and "ateLimit" in r.text):
                self.stats["retry_backoff"] += 1
                time.sleep(delay); delay *= 2
                continue
            try:
                err = r.json().get("error", {})
                reason = (err.get("errors") or [{}])[0].get("reason") or err.get("status") or ""
                msg = err.get("message", "")[:300]
            except Exception:
                reason, msg = "", r.text[:200]
            raise ApiError(r.status_code, reason, msg)
        raise ApiError(0, "retries exhausted")

    def fail(self, link: str, reason: str, context: str, rid: str | None = None, kind: str | None = None):
        with self.lock:
            self.failures.append({"link": link, "resource_id": rid, "kind": kind, "reason": reason, "context": context})

    # ---------------- catalog rows ----------------
    FIELDS = ("id,name,mimeType,size,md5Checksum,modifiedTime,version,parents,driveId,trashed,webViewLink,"
              "shortcutDetails(targetId,targetMimeType,targetResourceKey)")

    def meta(self, rid: str) -> dict:
        return self.get(f"{DRIVE}/files/{rid}", {"fields": self.FIELDS, "supportsAllDrives": "true"})

    def add_item(self, f: dict, provenance: list[str], parent: str | None) -> dict | None:
        rid = f["id"]
        with self.lock:
            if rid in self.items:
                self.items[rid]["also_reached_from"].append(" > ".join(provenance))
                return None
            if len(self.items) >= ITEM_CAP:
                self.capped = True
                return None
            mime = f.get("mimeType", "")
            row = {"resource_id": rid, "provider": "drive", "title": f.get("name"), "mime": mime,
                   "url": f.get("webViewLink") or live_url(mime, rid),
                   "modified_time": f.get("modifiedTime"), "version": f.get("version"),
                   "md5": f.get("md5Checksum"), "size": int(f["size"]) if f.get("size") else None,
                   "parent_id": parent, "provenance": provenance, "also_reached_from": [],
                   "status": "listed", "extract": None}
            if mime.startswith("audio/") or mime.startswith("video/"):
                row["status"] = "media_listed"
            self.items[rid] = row
            return row

    # ---------------- sheets ----------------
    def read_sheet(self, sid: str, provenance: list[str], depth: int) -> list[tuple[str, str | None, str, str]]:
        """Every tab, every cell, with embedded links. Returns (kind, id, url, cell) for each link found."""
        fields = ("spreadsheetId,properties(title),sheets(properties(sheetId,title,gridProperties),"
                  "data(rowData(values(formattedValue,hyperlink,textFormatRuns(format(link(uri))),"
                  "chipRuns(chip(richLinkProperties(uri)))))))")
        data = self.get(f"{SHEETS}/{sid}", {"includeGridData": "true", "fields": fields})
        title = data.get("properties", {}).get("title")
        rec = {"id": sid, "title": title, "depth": depth, "provenance": provenance, "read_via": "sheets api", "tabs": []}
        found = []
        for sh in data.get("sheets", []):
            p = sh["properties"]
            tab = {"title": p["title"], "grid_rows": p.get("gridProperties", {}).get("rowCount"),
                   "grid_cols": p.get("gridProperties", {}).get("columnCount"), "rows": [], "links": 0}
            for d in sh.get("data", []):
                for ri, row in enumerate(d.get("rowData", []) or []):
                    vals = []
                    for ci, cell in enumerate(row.get("values", []) or []):
                        v = cell.get("formattedValue")
                        cell_links = set()
                        if cell.get("hyperlink"):
                            cell_links.add(cell["hyperlink"])
                        for run in cell.get("textFormatRuns", []) or []:
                            u = (((run.get("format") or {}).get("link")) or {}).get("uri")
                            if u:
                                cell_links.add(u)
                        for run in cell.get("chipRuns", []) or []:
                            u = (((run.get("chip") or {}).get("richLinkProperties")) or {}).get("uri")
                            if u:
                                cell_links.add(u)
                        for u in links_in(v or ""):
                            cell_links.add(u[2])
                        vals.append({"v": v, "links": sorted(cell_links)} if cell_links else v)
                        ref = f"{p['title']}!{col_letter(ci)}{ri + 1}"
                        for u in sorted(cell_links):
                            for kind, lid, url in (links_in(u) or [("web", None, u)]):
                                found.append((kind, lid, url, ref))
                                tab["links"] += 1
                    while vals and vals[-1] in (None, ""):
                        vals.pop()
                    tab["rows"].append(vals)
            while tab["rows"] and not tab["rows"][-1]:
                tab["rows"].pop()
            rec["tabs"].append(tab)
        with self.lock:
            self.sheets[sid] = rec
        return found

    # ---------------- folders ----------------
    def walk_folder(self, fid: str, provenance: list[str]):
        stack = [(fid, provenance)]
        seen = set()
        while stack:
            cur, prov = stack.pop()
            if cur in seen:
                continue
            seen.add(cur)
            token = None
            while True:
                params = {"q": f"'{cur}' in parents and trashed = false", "fields": f"nextPageToken,files({self.FIELDS})",
                          "pageSize": 1000, "supportsAllDrives": "true", "includeItemsFromAllDrives": "true",
                          "corpora": "allDrives"}
                if token:
                    params["pageToken"] = token
                try:
                    res = self.get(f"{DRIVE}/files", params)
                except ApiError as e:
                    self.fail(live_url("folder", cur), reason_of(e), "listing folder " + " > ".join(prov), cur, "folder")
                    break
                for f in res.get("files", []):
                    child_prov = prov + [f.get("name") or f["id"]]
                    if f["mimeType"] == SHORTCUT:
                        self.follow_shortcut(f, child_prov, cur, stack)
                        continue
                    row = self.add_item(f, child_prov, cur)
                    if row is None:
                        continue
                    if f["mimeType"] == FOLDER:
                        stack.append((f["id"], child_prov))
                token = res.get("nextPageToken")
                if not token:
                    break

    def follow_shortcut(self, f, prov, parent, stack):
        sd = f.get("shortcutDetails") or {}
        tid = sd.get("targetId")
        with self.lock:
            self.stats["shortcuts"] += 1
        if not tid:
            self.fail(live_url("file", f["id"]), "shortcut without a target", " > ".join(prov), f["id"], "shortcut")
            return
        try:
            t = self.meta(tid)
        except ApiError as e:
            self.fail(live_url(sd.get("targetMimeType", "file"), tid), "shortcut target missing: " + reason_of(e),
                      " > ".join(prov), tid, "shortcut")
            return
        row = self.add_item(t, prov + ["(shortcut target)"], parent)
        if row is not None:
            row["via_shortcut"] = f["id"]
            if t["mimeType"] == FOLDER:
                stack.append((t["id"], prov))

    # ---------------- link following ----------------
    def follow(self, kind, lid, url, context, provenance, depth):
        self.links.append({"kind": kind, "resource_id": lid, "url": url, "cell": context, "depth": depth})
        if kind == "web" or lid is None:
            return
        try:
            f = self.meta(lid)
        except ApiError as e:
            self.links[-1]["status"] = reason_of(e)
            self.fail(url, reason_of(e), f"linked from {context}", lid, kind)
            return
        self.links[-1]["status"] = "ok"
        prov = provenance + [f"{context}", f.get("name") or lid]
        if f["mimeType"] == SHORTCUT:
            stack = []
            self.follow_shortcut(f, prov, None, stack)
            for fid, p in stack:
                self.walk_folder(fid, p)
            return
        row = self.add_item(f, prov, None)
        if row is not None:
            row["linked_from"] = context
        if f["mimeType"] == FOLDER:
            if row is not None:
                self.walk_folder(lid, prov)
        elif f["mimeType"] == G + "spreadsheet" and depth < 2 and lid not in self.sheets:
            # read a linked sheet even when a folder walk already listed the file (fix, run C)
            try:
                for k2, l2, u2, ref in self.read_sheet(lid, prov, depth + 1):
                    self.follow(k2, l2, u2, f"{f.get('name')}!{ref.split('!', 1)[1]}" if "!" in ref else ref, prov, depth + 1)
            except ApiError as e:
                self.fail(url, "sheet not readable through the Sheets API: " + reason_of(e), f"linked from {context}", lid, kind)

    # ---------------- extraction ----------------
    def text_path(self, rid):
        return self.out / "text" / f"{rid}.txt"

    def unchanged(self, row) -> bool:
        p = self.previous.get(row["resource_id"])
        return bool(p and p.get("modified_time") == row["modified_time"] and str(p.get("version")) == str(row["version"])
                    and (p.get("extract") or {}).get("ok") and self.text_path(row["resource_id"]).exists())

    def extract_one(self, row):
        rid, mime = row["resource_id"], row["mime"]
        how = EXTRACT.get(mime)
        if how is None:
            if mime in UNSUPPORTED_DOCS:
                row["status"] = "failed"
                self.fail(row["url"], f"unsupported format for the first pass ({UNSUPPORTED_DOCS[mime]})", " > ".join(row["provenance"]), rid, mime)
            return
        if self.unchanged(row):
            row["extract"] = dict(self.previous[rid]["extract"], reused=True)
            row["status"] = "extracted"
            with self.lock:
                self.stats["extract_reused"] += 1
            return
        if row.get("size") and row["size"] > self.max_bytes:
            row["status"] = "failed"
            row["extract"] = {"ok": False, "error": "too large for the first pass"}
            self.fail(row["url"], f"too large for the first pass ({row['size'] // (1024 * 1024)} MB > {self.max_bytes // (1024 * 1024)} MB)",
                      " > ".join(row["provenance"]), rid, mime)
            return
        try:
            text = getattr(self, "x_" + how)(rid)
        except ApiError as e:
            row["status"] = "failed"
            row["extract"] = {"ok": False, "error": reason_of(e)}
            self.fail(row["url"], "could not read for extraction: " + reason_of(e), " > ".join(row["provenance"]), rid, mime)
            return
        except Exception as e:                       # a corrupt or password-protected file
            row["status"] = "failed"
            row["extract"] = {"ok": False, "error": type(e).__name__}
            self.fail(row["url"], f"could not parse the file ({type(e).__name__})", " > ".join(row["provenance"]), rid, mime)
            return
        text = text or ""
        self.text_path(rid).write_text(text, encoding="utf-8")
        row["extract"] = {"ok": True, "how": how, "chars": len(text), "sha1": hashlib.sha1(text.encode("utf-8")).hexdigest(),
                          "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        row["status"] = "extracted" if text.strip() else "extracted_empty"
        with self.lock:
            self.stats["extracted"] += 1

    def _export(self, rid, mime):
        return self.get(f"{DRIVE}/files/{rid}/export", {"mimeType": mime}, raw=True).decode("utf-8", "replace")

    def _download(self, rid):
        return self.get(f"{DRIVE}/files/{rid}", {"alt": "media", "supportsAllDrives": "true"}, raw=True)

    def x_gdoc(self, rid):
        return self._export(rid, "text/plain")

    def x_gslides(self, rid):
        return self._export(rid, "text/plain")

    def x_gsheet(self, rid):
        data = self.get(f"{SHEETS}/{rid}", {"includeGridData": "true",
                                             "fields": "sheets(properties(title),data(rowData(values(formattedValue,hyperlink))))"})
        out = []
        for sh in data.get("sheets", []):
            out.append(f"## {sh['properties']['title']}")
            for d in sh.get("data", []):
                for row in d.get("rowData", []) or []:
                    cells = [(c.get("formattedValue") or "") + (f" <{c['hyperlink']}>" if c.get("hyperlink") else "")
                             for c in row.get("values", []) or []]
                    if any(cells):
                        out.append(" | ".join(cells))
        return "\n".join(out)

    def x_pdf(self, rid):
        import fitz
        doc = fitz.open(stream=self._download(rid), filetype="pdf")
        return "\n".join(f"--- page {i + 1} ---\n" + p.get_text() for i, p in enumerate(doc))

    def x_docx(self, rid):
        import docx
        d = docx.Document(io.BytesIO(self._download(rid)))
        parts = [p.text for p in d.paragraphs]
        for t in d.tables:
            for r in t.rows:
                parts.append(" | ".join(c.text for c in r.cells))
        return "\n".join(parts)

    def x_pptx(self, rid):
        from pptx import Presentation
        prs = Presentation(io.BytesIO(self._download(rid)))
        out = []
        for i, s in enumerate(prs.slides, 1):
            out.append(f"--- slide {i} ---")
            for sh in s.shapes:
                if getattr(sh, "has_text_frame", False) and sh.has_text_frame:
                    out.append(sh.text_frame.text)
        return "\n".join(out)

    def x_xlsx(self, rid):
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(self._download(rid)), read_only=True, data_only=True)
        out = []
        for ws in wb.worksheets:
            out.append(f"## {ws.title}")
            for row in ws.iter_rows(values_only=True):
                if any(c not in (None, "") for c in row):
                    out.append(" | ".join("" if c is None else str(c) for c in row))
        return "\n".join(out)

    # ---------------- run ----------------
    def run(self):
        t0 = time.time()
        reg = self.registry_id
        try:
            rmeta = self.meta(reg)
        except ApiError as e:
            sys.exit(f"registry sheet not readable: {reason_of(e)}")
        row = self.add_item(rmeta, ["registry"], None)
        row["role"] = "registry"
        for kind, lid, url, ref in self.read_sheet(reg, ["registry"], 0):
            self.follow(kind, lid, url, ref, ["registry"], 0)
        print(f"walk done: {len(self.items)} items, {len(self.failures)} failures, {time.time() - t0:.0f}s", flush=True)
        if self.do_extract:
            todo = [r for r in self.items.values() if r["mime"] in EXTRACT or r["mime"] in UNSUPPORTED_DOCS]
            done = Counter()
            with ThreadPoolExecutor(self.workers) as ex:
                for _ in ex.map(self.extract_one, todo):
                    done["n"] += 1
                    if done["n"] % 200 == 0:
                        print(f"extracted {done['n']}/{len(todo)} ({time.time() - t0:.0f}s)", flush=True)
        # disappeared since the previous crawl
        gone = [rid for rid in self.previous if rid not in self.items]
        for rid in self.items:
            p = self.previous.get(rid)
            r = self.items[rid]
            r["change"] = "new" if not p else ("changed" if (p.get("modified_time"), str(p.get("version"))) != (r["modified_time"], str(r["version"])) else "unchanged")
        self.write(time.time() - t0, gone)

    def write(self, secs, gone):
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        cat = {"generated": now, "registry_id": self.registry_id, "seconds": round(secs), "capped": self.capped,
               "item_cap": ITEM_CAP, "stats": dict(self.stats), "removed_since_previous": gone,
               "items": sorted(self.items.values(), key=lambda r: (r["provenance"], r["resource_id"]))}
        (self.out / "catalog.json").write_text(json.dumps(cat, indent=1, ensure_ascii=False), encoding="utf-8")
        (self.out / "failures.json").write_text(json.dumps(self.failures, indent=1, ensure_ascii=False), encoding="utf-8")
        (self.out / "links.json").write_text(json.dumps(self.links, indent=1, ensure_ascii=False), encoding="utf-8")
        (self.out / "sheets.json").write_text(json.dumps(self.sheets, indent=1, ensure_ascii=False), encoding="utf-8")
        c = Counter(r["status"] for r in self.items.values())
        print(json.dumps({"items": len(self.items), "by_status": dict(c), "failures": len(self.failures),
                          "links": len(self.links), "sheets": len(self.sheets), "removed_since_previous": len(gone),
                          "capped": self.capped}, indent=1))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", default=str(REPO / ".measure" / "sources"))
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--max-download-mb", type=int, default=60)
    ap.add_argument("--no-extract", action="store_true")
    a = ap.parse_args(argv)
    out = Path(a.out).resolve()
    if REPO in out.parents and ".measure" not in out.parts:
        sys.exit("outputs hold real data: write them under .measure/ (gitignored) or outside the repo")
    Crawler(out, a.workers, a.max_download_mb, not a.no_extract).run()


if __name__ == "__main__":
    main()
