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
    """Remove soft hyphens and collapse whitespace.

    Args:
        text: Text from the PDF.

    Returns:
        The text on one line.
    """
    return " ".join(text.replace("­", "").split())


def _lines(document: Any) -> list[tuple[int, float, str]]:
    """Read every text line of a PDF, in reading order.

    Only text blocks are read; images and drawings carry no text. An empty line marks the end of
    each block, where a paragraph ends.

    Args:
        document: The open PyMuPDF document.

    Returns:
        (page number from 1, type size, text) for each line, with (page, 0.0, "") at each block
        boundary.
    """
    out: list[tuple[int, float, str]] = []
    for number, page in enumerate(document, start=1):
        for block in page.get_text("dict")["blocks"]:
            if block.get("type") != 0:
                continue
            for line in block["lines"]:
                spans = [span for span in line["spans"] if span["text"].strip()]
                if not spans:
                    continue
                text = _clean("".join(span["text"] for span in spans))
                size = max(span["size"] for span in spans)
                out.append((number, round(size, 1), text))
            out.append((number, 0.0, ""))
    return out


def _paragraphs(lines: list[str]) -> list[str]:
    """Join a section's lines into paragraphs, mending words hyphenated across a line break.

    Args:
        lines: The lines, with empty strings at block boundaries.

    Returns:
        The paragraphs.
    """
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
    """Turn an uploaded PDF into titled sections of speakable text, like a web page (FR2).

    Headings are found by type size: a short line set at least 1.2 times larger than the body text,
    not ending in punctuation, starts a section. A PDF with no such lines (a scan with OCR, or one
    set in a single size) becomes one section per page. Each section's anchor is ``page=N``, which
    PDF viewers open at that page, so a citation lands where the passage is. Sections with too few
    speakable sentences are dropped and listed.

    Args:
        data: The PDF's bytes.
        filename: The name it was uploaded with, for the title and error messages.

    Returns:
        The document's title and its sections.

    Raises:
        ValueError: PyMuPDF cannot open the file (it raises its own types for damaged files), it is
            password-protected, or it has more than 500 pages.
    """
    import pymupdf

    try:
        document: Any = pymupdf.open(stream=data, filetype="pdf")  # type: ignore[no-untyped-call]
    except Exception as error:
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
        """Tell whether a line looks like a heading.

        Args:
            size: The line's type size.
            text: The line's text.

        Returns:
            True for a short line, larger than the body, with letters and no closing punctuation.
        """
        return (
            size >= body * HEADING_SCALE
            and len(text.split()) <= MAX_HEADING_WORDS
            and not text.endswith((".", ",", ";", ":"))
            and bool(re.search(r"[A-Za-z]", text))
        )

    raw: list[tuple[str, int, list[str]]] = []
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

    if not found_heading:
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
