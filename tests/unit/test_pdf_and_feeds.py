import pymupdf
import pytest

from podcast_engine.stages.ingest.feeds import feed_sections, looks_like_feed
from podcast_engine.stages.ingest.pdf import extract_pdf

BODY = (
    "Tidewater stores every column of a table in its own file on disk. "
    "Queries read only the columns they need, which keeps scans fast. "
    "Similar values sit next to each other and compress well."
)


def make_pdf(pages: list[list[tuple[float, str]]], *, title: str = "") -> bytes:
    document = pymupdf.open()
    for blocks in pages:
        page = document.new_page()
        y = 72.0
        for size, text in blocks:
            page.insert_textbox(pymupdf.Rect(72, y, 520, y + 200), text, fontsize=size)
            y += 40 + 14 * (len(text) // 70)
    if title:
        document.set_metadata({"title": title})
    data: bytes = document.tobytes()
    document.close()
    return data


def test_pdf_splits_at_headings_and_anchors_each_section_to_its_page() -> None:
    data = make_pdf(
        [[(20, "Storage engine"), (11, BODY)], [(20, "Replication"), (11, BODY)]],
        title="Tidewater whitepaper",
    )
    page = extract_pdf(data, filename="tidewater.pdf")
    assert page.title == "Tidewater whitepaper"
    assert [(s.heading, s.anchor) for s in page.sections] == [
        ("Storage engine", "page=1"),
        ("Replication", "page=2"),
    ]
    assert "compress well" in page.sections[0].text


def test_pdf_without_headings_becomes_one_section_per_page() -> None:
    page = extract_pdf(make_pdf([[(11, BODY)], [(11, BODY)]]), filename="notes.pdf")
    assert [(s.heading, s.anchor) for s in page.sections] == [
        ("notes, page 1", "page=1"),
        ("notes, page 2", "page=2"),
    ]


def test_pdf_with_too_little_text_has_no_sections() -> None:
    page = extract_pdf(make_pdf([[(20, "Cover"), (11, "Draft.")]]), filename="cover.pdf")
    assert page.sections == ()


def test_unreadable_pdf_is_a_clear_error() -> None:
    with pytest.raises(ValueError, match="not a readable PDF"):
        extract_pdf(b"%PDF-1.7 but then nothing", filename="broken.pdf")


RSS = f"""<?xml version="1.0"?>
<rss version="2.0"><channel><title>Tidewater blog</title>
<item><title>Full post</title><link>https://blog.test/full</link>
<pubDate>Mon, 05 Oct 2026 10:00:00 GMT</pubDate>
<description><![CDATA[<p>{BODY} {BODY}</p><p>{BODY}</p>]]></description></item>
<item><title>Teaser only</title><link>https://blog.test/teaser</link>
<description>Read more.</description></item>
<item><title>Broken link</title><link>https://blog.test/missing</link></item>
</channel></rss>"""
ARTICLE = (
    "<html><head><title>Teaser only</title></head><body><main><h1>Teaser only</h1>"
    f"<p>{BODY}</p></main></body></html>"
)


def test_feed_uses_summaries_and_reads_the_page_when_there_is_none() -> None:
    def fetch(url: str) -> str:
        if url.endswith("/teaser"):
            return ARTICLE
        raise ConnectionError("404")

    title, sections = feed_sections(RSS, fetch, max_items=10)
    assert title == "Tidewater blog"
    assert [(url, section.heading) for url, section, _ in sections] == [
        ("https://blog.test/full", "Full post"),
        ("https://blog.test/teaser", "Teaser only"),
    ]
    assert sections[0][2] is not None  # the entry's date
    assert sections[0][1].text.count("\n\n") == 1  # paragraphs kept


def test_feed_detection() -> None:
    assert looks_like_feed(RSS)
    assert looks_like_feed('<feed xmlns="http://www.w3.org/2005/Atom"><title>x</title></feed>')
    assert not looks_like_feed(ARTICLE)


def test_max_items_limits_the_entries_read() -> None:
    _, sections = feed_sections(RSS, lambda url: ARTICLE, max_items=1)
    assert [section.heading for _, section, _ in sections] == ["Full post"]
