"""Binary files must yield real text, or say plainly that they did not.

FOUND BEFORE THE FIRST CRAWL, by asking what `_export_text` does with a file
that is not natively exportable. It downloaded the bytes and the caller ran
`raw.decode("utf-8", "replace")` — so a `.pptx` (a zip) and a `.pdf` would have
been written into the cache as replacement-character noise, in a file named
`.txt`, and Phase 3 would have extracted "topics" from it.

That is the shape this project keeps finding: **the failure produces output, so
nothing reports an error.** 347 of the 991 files in scope are binary — 170
.docx, 125 .pptx, 51 .pdf, 1 .xlsx — so it would have been most of the decks.

Two rules come out of it, and both are tested here:
  * an extractor exists for a type, or the file is METADATA ONLY with a named
    reason. There is no third outcome where garbage is stored as text;
  * the type is decided by MAGIC BYTES, not the extension — `CLAUDE.md`'s
    `A_sample_Mock_Session_Feedback_Documentation.docx` is plain UTF-8 with the
    wrong extension and `python-docx` raises on it.
"""
from __future__ import annotations

import io
import sys
import zipfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from pipeline.lib import extract_text as ex                    # noqa: E402

PPTX = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
PDF = "application/pdf"


def _real_pptx(slides: list[str]) -> bytes:
    from pptx import Presentation
    from pptx.util import Inches
    prs = Presentation()
    for body in slides:
        s = prs.slides.add_slide(prs.slide_layouts[5])
        tb = s.shapes.add_textbox(Inches(1), Inches(1), Inches(6), Inches(2))
        tb.text_frame.text = body
    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


def _real_docx(paras: list[str]) -> bytes:
    import docx
    d = docx.Document()
    for p in paras:
        d.add_paragraph(p)
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


def _real_pdf(pages: list[str]) -> bytes:
    import fitz
    doc = fitz.open()
    for body in pages:
        pg = doc.new_page()
        pg.insert_text((72, 72), body)
    return doc.tobytes()


# ---------------------------------------------------------------------------

def test_a_pptx_yields_its_slide_text():
    text, meta = ex.extract(_real_pptx(["REST constraints", "HATEOAS"]), PPTX, "d.pptx")
    assert "REST constraints" in text
    assert "HATEOAS" in text


def test_a_pptx_carries_slide_numbers():
    """Phase 3 wants topics WITH slide numbers, so the extractor has to emit
    them — recovering a slide number from flat text afterwards is guesswork."""
    text, meta = ex.extract(_real_pptx(["one", "two", "three"]), PPTX, "d.pptx")
    assert meta["slide_count"] == 3
    assert "[slide 1]" in text and "[slide 3]" in text


def test_a_docx_yields_its_paragraphs():
    text, _ = ex.extract(_real_docx(["Object modelling", "Normalisation"]), DOCX, "x.docx")
    assert "Object modelling" in text and "Normalisation" in text


def test_a_pdf_yields_its_page_text_with_page_numbers():
    text, meta = ex.extract(_real_pdf(["Concurrency basics", "Thread pools"]), PDF, "x.pdf")
    assert "Concurrency basics" in text
    assert meta["page_count"] == 2
    assert "[page 1]" in text


def test_a_file_whose_extension_lies_is_read_by_its_magic_bytes():
    """CLAUDE.md: `A_sample_Mock_Session_Feedback_Documentation.docx` is plain
    UTF-8 with the wrong extension, and python-docx raises on it."""
    text, _ = ex.extract(b"Just plain text, honestly.", DOCX, "lying.docx")
    assert "Just plain text" in text


def test_an_unparseable_binary_returns_none_rather_than_noise():
    """The whole point. No third outcome where garbage is stored as text."""
    text, meta = ex.extract(b"\x00\x01\x02\xff\xfe not a document", PDF, "broken.pdf")
    assert text is None
    assert meta["reason"]


def test_a_zip_that_is_not_an_office_file_returns_none():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("readme.txt", "source code")
    text, meta = ex.extract(buf.getvalue(), PPTX, "code.pptx")
    assert text is None


def test_extracted_text_is_still_redacted_by_the_caller():
    """Negative control on the boundary: this module does NOT redact, so a
    caller that forgot would be visible here rather than silently fine."""
    text, _ = ex.extract(_real_docx(["mail me at a@b.com"]), DOCX, "x.docx")
    assert "a@b.com" in text
