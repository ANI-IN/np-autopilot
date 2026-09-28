"""Turn a downloaded binary into text, or say why it could not.

THERE IS NO THIRD OUTCOME. Either this returns text, or it returns
`(None, {"reason": ...})` and the caller records the file as metadata only.
What it must never do is return bytes decoded as if they were text: a `.pptx`
is a zip, and `zip_bytes.decode("utf-8", "replace")` produces a page of
replacement characters that looks like a successful extraction to everything
downstream. `docs/A7B.md` — the failure that produces output is the one nothing
reports.

TYPE COMES FROM MAGIC BYTES, NOT THE EXTENSION. `CLAUDE.md` records
`A_sample_Mock_Session_Feedback_Documentation.docx` as plain UTF-8 with a
`.docx` extension, on which `python-docx` raises. The declared mime is used
only to choose which extractor to TRY first.

IT DOES NOT REDACT. Redaction belongs to the caller, at the single point where
text reaches disk, so there is exactly one place to check that it happened —
`tests/test_text_extraction.py` asserts this module leaves an address intact.
"""
from __future__ import annotations

import io
import zipfile

PDF = "application/pdf"
PPTX = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

_ZIP_MAGIC = b"PK\x03\x04"
_PDF_MAGIC = b"%PDF"


def _looks_textual(data: bytes) -> bool:
    """Printable enough to be a text file that was misnamed."""
    sample = data[:4096]
    if not sample:
        return False
    if b"\x00" in sample:
        return False
    try:
        sample.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


def _pdf(data: bytes) -> tuple[str, dict]:
    import fitz
    doc = fitz.open(stream=data, filetype="pdf")
    parts = []
    for i, page in enumerate(doc, 1):
        body = (page.get_text() or "").strip()
        if body:
            parts.append(f"[page {i}]\n{body}")
    return "\n\n".join(parts), {"page_count": doc.page_count}


def _pptx(data: bytes) -> tuple[str, dict]:
    """Slide numbers are EMITTED, not recovered afterwards.

    Phase 3 wants a topic to cite the slide it came from. Flattening the deck
    and inferring slide boundaries later is guesswork; the library already
    knows, so the number is written down at the only moment it is free.
    Speaker notes are included and labelled — REGISTRY-INVENTORY §6 found they
    read as instructions to the instructor, which is content about the class.
    """
    from pptx import Presentation
    prs = Presentation(io.BytesIO(data))
    parts, n = [], 0
    for i, slide in enumerate(prs.slides, 1):
        n = i
        chunks = []
        for shape in slide.shapes:
            if shape.has_text_frame and shape.text_frame.text.strip():
                chunks.append(shape.text_frame.text.strip())
        if slide.has_notes_slide:
            notes = (slide.notes_slide.notes_text_frame.text or "").strip()
            if notes:
                chunks.append(f"(speaker notes) {notes}")
        if chunks:
            parts.append(f"[slide {i}]\n" + "\n".join(chunks))
    return "\n\n".join(parts), {"slide_count": n}


def _docx(data: bytes) -> tuple[str, dict]:
    import docx
    d = docx.Document(io.BytesIO(data))
    paras = [p.text.strip() for p in d.paragraphs if p.text.strip()]
    for table in d.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells if c.text.strip()]
            if cells:
                paras.append(" | ".join(cells))
    return "\n".join(paras), {"paragraph_count": len(paras)}


def _xlsx(data: bytes) -> tuple[str, dict]:
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    parts = []
    for tab in wb.sheetnames:
        rows = []
        for r in wb[tab].iter_rows(values_only=True):
            cells = [str(c).strip() for c in r if c is not None and str(c).strip()]
            if cells:
                rows.append(" | ".join(cells))
        if rows:
            parts.append(f"[tab {tab}]\n" + "\n".join(rows))
    wb.close()
    return "\n\n".join(parts), {"tab_count": len(wb.sheetnames)}


#: Tried in order, after the declared mime's own extractor.
_BY_MIME = {PDF: _pdf, PPTX: _pptx, DOCX: _docx, XLSX: _xlsx}


def extract(data: bytes, mime: str, name: str) -> tuple[str | None, dict]:
    """(text, meta) or (None, {"reason": ...}). Never decoded noise."""
    if not data:
        return None, {"reason": "empty file"}

    # 1. The declared type, if the bytes agree with it.
    fn = _BY_MIME.get(mime)
    magic_ok = ((data.startswith(_PDF_MAGIC) and mime == PDF)
                or (data.startswith(_ZIP_MAGIC) and mime in (PPTX, DOCX, XLSX)))
    if fn and magic_ok:
        try:
            text, meta = fn(data)
            if text.strip():
                return text, meta
            return None, {"reason": f"{mime} parsed but held no text"}
        except Exception as exc:                                   # noqa: BLE001
            return None, {"reason": f"{type(exc).__name__} parsing {mime}"}

    # 2. The extension lied. Plain text is the common case and is cheap to
    #    confirm, so it is tried before anything is given up on.
    if _looks_textual(data):
        return data.decode("utf-8", "strict"), {"recovered_by": "magic-bytes"}

    # 3. A zip that is not the Office type it claimed — a source archive with
    #    a .pptx name, say. Guessing further means opening an unknown archive.
    if data.startswith(_ZIP_MAGIC):
        try:
            names = zipfile.ZipFile(io.BytesIO(data)).namelist()
        except Exception:                                          # noqa: BLE001
            names = []
        marker = {PPTX: "ppt/", DOCX: "word/", XLSX: "xl/"}.get(mime, "")
        if marker and any(n.startswith(marker) for n in names):
            try:
                text, meta = _BY_MIME[mime](data)
                if text.strip():
                    return text, meta
            except Exception:                                      # noqa: BLE001
                pass
        return None, {"reason": f"zip archive that is not a {mime}"}

    return None, {"reason": f"no text extractor for {mime}"}
