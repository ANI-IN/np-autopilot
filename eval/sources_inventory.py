"""READ-ONLY inventory of the registry sheet, linked sheets and Drive folders.
Never prints credentials. Uses read-only scopes only. Only GET requests."""
import json, os, re, sys, time
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import quote

REPO = Path(r"C:\Users\Lenovo\Desktop\np-autopilot")
OUT = REPO / ".measure" / "inventory"
LOG = Path(sys.argv[1]) if len(sys.argv) > 1 else None
ITEM_CAP = 30000
SCOPES = ["https://www.googleapis.com/auth/drive.readonly",
          "https://www.googleapis.com/auth/spreadsheets.readonly"]

from dotenv import dotenv_values
from google.oauth2 import service_account
from google.auth.transport.requests import AuthorizedSession
import requests

def log(*a):
    msg = time.strftime("%H:%M:%S ") + " ".join(str(x) for x in a)
    if LOG:
        with open(LOG, "a", encoding="utf-8") as f: f.write(msg + "\n")

env = dotenv_values(REPO / ".env")
key_path = Path(os.path.expanduser(env.get("NP_DRIVE_SA_KEY") or "")).resolve()
sheet_src = "KB_SHEETS_ID"
REGISTRY_ID = (env.get("KB_SHEETS_ID") or "").strip()
if not REGISTRY_ID:
    txt = (REPO / "docs/project-history/REGISTRY-INVENTORY.md").read_text(encoding="utf-8")
    m = re.search(r"titled \*\*`links`\*\*, id `([A-Za-z0-9_-]{20,})`", txt)
    REGISTRY_ID = m.group(1) if m else ""
    sheet_src = "REGISTRY-INVENTORY.md fallback (KB_SHEETS_ID empty)"
if not REGISTRY_ID: sys.exit("no registry id")
del env

creds = service_account.Credentials.from_service_account_file(str(key_path), scopes=SCOPES)
S = AuthorizedSession(creds)
DRIVE = "https://www.googleapis.com/drive/v3"
SHEETS = "https://sheets.googleapis.com/v4/spreadsheets"
stats = Counter()

class ApiError(Exception):
    def __init__(self, status, reason, msg):
        super().__init__(f"{status} {reason}"); self.status, self.reason, self.msg = status, reason, msg

def get(url, params=None):
    delay = 1.0
    for attempt in range(7):
        try:
            r = S.get(url, params=params, timeout=120)
        except (requests.ConnectionError, requests.Timeout) as e:
            stats["conn_retry"] += 1; log("conn retry", type(e).__name__); time.sleep(delay); delay *= 2; continue
        stats["requests"] += 1
        if r.status_code == 200: return r.json()
        if r.status_code in (429, 500, 502, 503, 504) or (r.status_code == 403 and "rateLimit" in r.text):
            stats["backoff"] += 1; time.sleep(delay); delay *= 2; continue
        try:
            err = r.json().get("error", {})
            reason = (err.get("errors") or [{}])[0].get("reason") or err.get("status") or ""
            msg = err.get("message", "")
        except Exception:
            reason, msg = "", r.text[:200]
        raise ApiError(r.status_code, reason, msg[:300])
    raise ApiError(0, "retries_exhausted", url.split("?")[0][-60:])

# ---------------- link extraction ----------------
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
GOOGLE_HINT = re.compile(r"(docs|drive)\.google\.com/[^\s\"')]+")

def extract(text):
    out, spans = [], []
    if not isinstance(text, str) or "google.com" not in text: return out
    for kind, p in PATTERNS:
        for m in p.finditer(text):
            out.append((kind, m.group(1), m.group(0))); spans.append(m.span())
    for m in GOOGLE_HINT.finditer(text):
        if not any(s <= m.start() < e for s, e in spans):
            out.append(("unparsed", None, m.group(0)[:200]))
    return out

def col_letter(i):
    s = ""
    i += 1
    while i: i, r = divmod(i - 1, 26); s = chr(65 + r) + s
    return s

# ---------------- state ----------------
sheets_out = {}         # id -> sheet record
links = []              # every link occurrence
failures = []           # every access failure
meta_cache = {}         # id -> meta or ApiError
items = []              # every drive item found under folders
folder_seen = {}        # folder id -> first path
repeats = []
capped = False

def fail(target, reason, detail, context):
    failures.append({"target": target, "reason": reason, "detail": detail, "context": context})
    log("FAIL", reason, context)

def reason_of(e):
    if e.status == 404: return "404 not found / no access (Drive hides unshared files as 404)"
    if e.status == 403: return f"403 {e.reason or 'forbidden'}"
    if e.status == 400: return f"400 {e.reason or 'bad request'}"
    return f"{e.status} {e.reason}"

FILE_FIELDS = "id,name,mimeType,size,modifiedTime,parents,driveId,trashed,shortcutDetails(targetId,targetMimeType),owners(emailAddress)"
def meta(fid):
    if fid in meta_cache: return meta_cache[fid]
    try:
        m = get(f"{DRIVE}/files/{fid}", {"fields": FILE_FIELDS, "supportsAllDrives": "true"})
    except ApiError as e:
        m = e
    meta_cache[fid] = m
    return m

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
def get_bytes(url, params):
    delay = 1.0
    for attempt in range(6):
        try:
            r = S.get(url, params=params, timeout=300)
        except (requests.ConnectionError, requests.Timeout):
            stats["conn_retry"] += 1; time.sleep(delay); delay *= 2; continue
        stats["requests"] += 1
        if r.status_code == 200: return r.content
        if r.status_code in (429, 500, 502, 503, 504) or (r.status_code == 403 and "rateLimit" in r.text):
            stats["backoff"] += 1; time.sleep(delay); delay *= 2; continue
        try:
            err = r.json().get("error", {}); reason = (err.get("errors") or [{}])[0].get("reason") or err.get("status") or ""; msg = err.get("message", "")
        except Exception:
            reason, msg = "", r.text[:200]
        raise ApiError(r.status_code, reason, msg[:300])
    raise ApiError(0, "retries_exhausted", "export")

def inspect_sheet(sid, depth, label):
    """Sheets API is disabled for the SA project, so read via Drive export (xlsx, read-only), parsed in memory."""
    import io, openpyxl
    if sid in sheets_out: return []
    rec = {"id": sid, "depth": depth, "label": label, "tabs": [], "links_found": 0, "error": None, "read_via": "drive export xlsx"}
    sheets_out[sid] = rec
    m = meta(sid)
    if isinstance(m, ApiError):
        rec["error"] = reason_of(m); fail(sid, reason_of(m), m.msg, f"open sheet metadata ({label})"); return []
    rec["title"] = m.get("name"); rec["modifiedTime"] = m.get("modifiedTime")
    try:
        data = get_bytes(f"{DRIVE}/files/{sid}/export", {"mimeType": XLSX})
    except ApiError as e:
        r = reason_of(e)
        if e.reason == "exportSizeLimitExceeded": r = "403 export size limit exceeded (sheet too large to export)"
        rec["error"] = r; fail(sid, r, e.msg, f"export sheet ({label})"); return []
    try:
        wb = openpyxl.load_workbook(io.BytesIO(data), data_only=False)
    except Exception as e:
        rec["error"] = "xlsx parse error"; fail(sid, "xlsx parse error", type(e).__name__, f"parse ({label})"); return []
    log("sheet", depth, label, "tabs", len(wb.worksheets))
    found = []
    for ws in wb.worksheets:
        title = ws.title
        tab = {"title": title, "grid_rows": ws.max_row, "grid_cols": ws.max_column, "headers": [], "nonempty_rows": 0, "data_rows": 0, "links": 0}
        rec["tabs"].append(tab)
        seen_cell = set()
        def add(kind, lid, raw, r, c, via):
            key = (r, c, lid or raw)
            if key in seen_cell: return
            seen_cell.add(key)
            occ = {"kind": kind, "id": lid, "raw": raw, "sheet": sid, "tab": title, "cell": f"{col_letter(c)}{r+1}", "via": via, "depth": depth}
            links.append(occ); found.append(occ); tab["links"] += 1
        hdr_done = False; data_rows = 0; nonempty = 0
        for r, row in enumerate(ws.iter_rows()):
            vals = [c.value for c in row]
            if any(v is not None and str(v).strip() for v in vals):
                nonempty += 1
                if not hdr_done:
                    while vals and (vals[-1] is None or not str(vals[-1]).strip()): vals.pop()
                    tab["headers"] = ["" if v is None else str(v) for v in vals]; tab["header_row"] = r + 1; hdr_done = True
                else:
                    data_rows += 1
            for c, cell in enumerate(row):
                v = cell.value
                if isinstance(v, str):
                    for kind, lid, raw in extract(v): add(kind, lid, raw, r, c, "value/formula")
                hl = getattr(cell, "hyperlink", None)
                if hl is not None and getattr(hl, "target", None):
                    for kind, lid, raw in extract(hl.target): add(kind, lid, raw, r, c, "hyperlink")
        tab["nonempty_rows"] = nonempty; tab["data_rows"] = data_rows
    rec["links_found"] = len(found)
    del wb, data
    time.sleep(0.3)
    return found

def list_children(fid):
    out, token = [], None
    while True:
        params = {"q": f"'{fid}' in parents and trashed = false", "pageSize": 1000,
                  "fields": "nextPageToken,files(id,name,mimeType,size,modifiedTime,shortcutDetails(targetId,targetMimeType))",
                  "supportsAllDrives": "true", "includeItemsFromAllDrives": "true"}
        if token: params["pageToken"] = token
        page = get(f"{DRIVE}/files", params)
        out.extend(page.get("files", []))
        token = page.get("nextPageToken")
        if not token: return out

def walk_folder(root_id, root_label):
    global capped
    stack = [(root_id, root_label)]
    while stack:
        fid, path = stack.pop()
        if fid in folder_seen:
            repeats.append({"folder": fid, "first_path": folder_seen[fid], "again_path": path}); continue
        folder_seen[fid] = path
        if len(items) >= ITEM_CAP:
            capped = True; return
        try:
            kids = list_children(fid)
        except ApiError as e:
            fail(fid, reason_of(e), e.msg, f"list folder {path}"); continue
        stats["folders_listed"] += 1
        if stats["folders_listed"] % 100 == 0: log("folders", stats["folders_listed"], "items", len(items))
        for k in kids:
            it = {"id": k["id"], "name": k["name"], "mimeType": k["mimeType"], "size": int(k["size"]) if k.get("size") else None,
                  "modifiedTime": k.get("modifiedTime"), "parent_path": path, "root": root_label, "parent_id": fid}
            items.append(it)
            if k["mimeType"] == "application/vnd.google-apps.folder":
                stack.append((k["id"], f"{path}/{k['name']}"))
            elif k["mimeType"] == "application/vnd.google-apps.shortcut":
                sd = k.get("shortcutDetails") or {}
                it["shortcut_target"] = sd.get("targetId"); it["shortcut_target_mime"] = sd.get("targetMimeType")
                tm = meta(sd.get("targetId")) if sd.get("targetId") else None
                if tm is None or isinstance(tm, ApiError) or tm.get("trashed"):
                    why = "shortcut target missing" + (f" ({reason_of(tm)})" if isinstance(tm, ApiError) else (" (trashed)" if tm else ""))
                    it["shortcut_broken"] = why
                    fail(sd.get("targetId"), why, "", f"shortcut {path}/{k['name']}")
                elif sd.get("targetMimeType") == "application/vnd.google-apps.folder":
                    stack.append((sd["targetId"], f"{path}/{k['name']} [shortcut]"))

# ---------------- run ----------------
def main():
    log("start; registry source:", sheet_src)
    reg_found = inspect_sheet(REGISTRY_ID, 0, "Sheet 1 (registry)")
    # resolve every link, depth-limited sheet opening
    queue = list(reg_found)
    folders_to_walk = []
    n = 0
    while queue:
        occ = queue.pop(0)
        if occ["kind"] == "unparsed":
            occ["status"] = "unsupported link form"
            fail(occ["raw"], "unsupported/unparsed Google link", "", f"{occ['tab']}!{occ['cell']}"); continue
        m = meta(occ["id"])
        if isinstance(m, ApiError):
            occ["status"] = reason_of(m)
            fail(occ["id"], reason_of(m), m.msg, f"link in {sheets_out[occ['sheet']].get('label')} {occ['tab']}!{occ['cell']}"); continue
        occ["resolved"] = {"name": m.get("name"), "mimeType": m.get("mimeType"), "trashed": m.get("trashed")}
        mt = m.get("mimeType")
        if m.get("trashed"):
            occ["status"] = "trashed"; fail(occ["id"], "target is trashed", "", f"{occ['tab']}!{occ['cell']}")
        elif mt == "application/vnd.google-apps.shortcut":
            sd = m.get("shortcutDetails") or {}; mt = sd.get("targetMimeType"); tid = sd.get("targetId")
            tm = meta(tid) if tid else None
            if tm is None or isinstance(tm, ApiError):
                occ["status"] = "shortcut target missing"; fail(tid, "shortcut target missing", "", f"{occ['tab']}!{occ['cell']}"); continue
            occ["id_effective"] = tid
        else:
            occ["status"] = "ok"
        eff = occ.get("id_effective", occ["id"])
        if mt == "application/vnd.google-apps.folder":
            occ["status"] = "ok"; folders_to_walk.append((eff, occ))
        elif mt == "application/vnd.google-apps.spreadsheet" and occ["depth"] < 2:
            occ["status"] = "ok"
            n += 1
            lbl = f"Sheet d{occ['depth']+1}-{len(sheets_out)+1}"
            queue.extend(inspect_sheet(eff, occ["depth"] + 1, lbl))
        elif mt == "application/vnd.google-apps.spreadsheet":
            occ["status"] = occ.get("status") or "ok"; occ["note"] = "sheet beyond depth 2: metadata only"
    walked = set()
    for i, (fid, occ) in enumerate(folders_to_walk):
        if fid in walked: continue
        walked.add(fid)
        label = f"Folder {i+1}"
        occ["folder_label"] = label
        log("walk", label)
        walk_folder(fid, label)
        if capped: log("CAPPED"); break
    if capped:
        remaining = [f for f, _ in folders_to_walk if f not in walked]
        fail("(crawl)", "item cap reached", f"cap {ITEM_CAP}; {len(remaining)} linked folder(s) not walked", "folder crawl")
    result = {"generated": time.strftime("%Y-%m-%dT%H:%M:%S"), "registry_source": sheet_src, "registry_id": REGISTRY_ID,
              "item_cap": ITEM_CAP, "capped": capped, "stats": dict(stats),
              "sheets": list(sheets_out.values()), "links": links, "linked_folders": [{"id": f, "label": o.get("folder_label"), "name": (o.get("resolved") or {}).get("name"), "from": f"{o['tab']}!{o['cell']}"} for f, o in folders_to_walk],
              "items": items, "folder_repeats": repeats, "failures": failures}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "sheets_drive_inventory.json").write_text(json.dumps(result, indent=1, ensure_ascii=False), encoding="utf-8")
    log("done", dict(stats), "items", len(items), "failures", len(failures))

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log("CRASH", type(e).__name__, str(e)[:300]); raise
