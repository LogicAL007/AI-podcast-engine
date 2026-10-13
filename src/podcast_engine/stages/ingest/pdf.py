"""Turn an uploaded PDF into titled sections of speakable text, like a web page (FR2, PDF sources).

Headings are found by type size: a short line set noticeably larger than the body text starts a
section. A PDF with no such lines (a scan with OCR, or one set in a single size) becomes one section
per page. Each section's anchor is ``page=N``, which PDF viewers open at that page, so a citation
lands where the passage is.
"""

import re
import statistics
from collections import Counter
from pathlib import PurePosixPath
from typing import Any

from podcast_engine.common.text import speakable_sentences
from podcast_engine.stages.ingest.extract import MIN_SECTION_SENTENCES, ExtractedPage, Section

HEADING_SCALE = 1.2  # a heading's type is at least this much larger than the body's
MAX_HEADING_WORDS = 15
MAX_PAGES = 500  # refuse to read more; an upload this long is unlikely to be one episode's source


def _clean(text: str) -> str:
    return " ".join(text.replace("­", "").split())


def _lines(document: Any) -> list[tuple[int, float, str]]:
    """Every text line as (page number from 1, type size, text), in reading order."""
    out: list[tuple[int, float, str]] = []
    for number, page in enumerate(document, start=1):
        for block in page.get_text("dict")["blocks"]:
            if block.get("type") != 0:  # 0 is text; images and drawings carry none
                continue
            for line in block["lines"]:
                spans = [span for span in line["spans"] if span["text"].strip()]
                if not spans:
                    continue
                text = _clean("".join(span["text"] for span in spans))
                size = max(span["size"] for span in spans)
                out.append((number, round(size, 1), text))
            out.append((number, 0.0, ""))  # a block boundary: the paragraph ends here
    return out


def _paragraphs(lines: list[str]) -> list[str]:
    """Join a block's lines into paragraphs, mending words hyphenated across a line break."""
    paragraphs, current = [], ""
    for line in lines:
        if not line:
            if current:
                paragraphs.append(current)
            current = ""
            continue
        if current.endswith("-") and line[:1].islower():
            current = current[:-1] + line
        else:
            current = f"{current} {line}".strip()
    if current:
        paragraphs.append(current)
    return paragraphs


def extract_pdf(data: bytes, *, filename: str = "") -> ExtractedPage:
    """Sections of an uploaded PDF. Raises ValueError for a file PyMuPDF cannot open."""
    import pymupdf

    try:
        document: Any = pymupdf.open(stream=data, filetype="pdf")  # type: ignore[no-untyped-call]
    except Exception as error:  # PyMuPDF raises its own types for damaged or encrypted files
        raise ValueError(f"{filename or 'upload'}: not a readable PDF ({error})") from error
    with document:
        if document.needs_pass:
            raise ValueError(f"{filename or 'upload'}: the PDF is password-protected")
        if document.page_count > MAX_PAGES:
            raise ValueError(
                f"{filename or 'upload'}: {document.page_count} pages; the limit is {MAX_PAGES}"
            )
        title = _clean((document.metadata or {}).get("title") or "") or PurePosixPath(filename).stem
        lines = _lines(document)

    weights: Counter[float] = Counter()
    for _, size, text in lines:
        if text:
            weights[size] += len(text)
    body = statistics.median_high(list(weights.elements())) if weights else 0.0

    def is_heading(size: float, text: str) -> bool:
        return (
            size >= body * HEADING_SCALE
            and len(text.split()) <= MAX_HEADING_WORDS
            and not text.endswith((".", ",", ";", ":"))
            and bool(re.search(r"[A-Za-z]", text))
        )

    raw: list[tuple[str, int, list[str]]] = []  # (heading, page, lines)
    heading, page = title or "Introduction", 1
    buffer: list[str] = []
    found_heading = False
    for number, size, text in lines:
        if text and is_heading(size, text):
            found_heading = True
            raw.append((heading, page, buffer))
            heading, page, buffer = text, number, []
        else:
            buffer.append(text)
    raw.append((heading, page, buffer))

    if not found_heading:  # no structure to follow: one section per page
        raw = []
        for number in sorted({n for n, _, _ in lines}):
            raw.append(
                (f"{title}, page {number}" if title else f"Page {number}", number,
                 [t for n, _, t in lines if n == number])
            )  # fmt: skip

    sections, dropped, seen = [], [], Counter[int]()
    for head, number, buffer_lines in raw:
        body_text = "\n\n".join(_paragraphs(buffer_lines))
        if len(speakable_sentences(body_text)) < MIN_SECTION_SENTENCES:
            if body_text:
                dropped.append(head)
            continue
        seen[number] += 1
        anchor = f"page={number}" if seen[number] == 1 else f"page={number}&section={seen[number]}"
        sections.append(Section(heading=head, anchor=anchor, text=body_text))
    return ExtractedPage(
        title=title, published_at=None, sections=tuple(sections), dropped=tuple(dropped)
    )
