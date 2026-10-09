from datetime import UTC, datetime

import pytest

from podcast_engine.common.models import ReliabilityTier
from podcast_engine.stages.ingest.extract import extract_page, source_tier, speakable_sentences

PAGE = """
<html><head><title>What is X? - Docs</title>
<meta property="article:modified_time" content="2026-08-23T10:00:00Z"></head>
<body>
<nav><p>Navigation menu text that must never be spoken aloud by anyone at all.
</p></nav>
<main>
<h1>What is X?</h1>
<span data-as="p">X is a column-oriented database built for analytics work. It is open source
and also offered as a cloud service. Teams use it to answer questions over very large
datasets.</span>
<h2 id="analytics">What are analytics?
<a href="#analytics">Direct link to What are analytics?</a></h2>
<span data-as="p">Analytics queries, e.g. aggregations over many rows, run over huge datasets.
They often must answer in under a second. Transactional queries touch only a few rows
instead.</span>
<span data-as="p">Row-oriented DBMS</span>
<p>As you can see in the diagram above, the query finishes quickly for everyone.</p>
<pre>SELECT count() FROM hits;</pre>
<p>Rows are stored one after another on disk, which suits lookups. Columns are stored
together instead.</p>
<h2>Documentation Index</h2>
<p>This index text should be skipped. It has several sentences. All of them are ignored
here.</p>
<h2 id="tiny">Tiny</h2>
<p>Too short to keep.</p>
</main></body></html>
"""


def test_sections_follow_the_headings_and_drop_noise() -> None:
    page = extract_page(PAGE)
    assert [s.heading for s in page.sections] == ["What is X?", "What are analytics?"]
    everything = " ".join(s.text for s in page.sections)
    assert "Navigation menu" not in everything
    assert "SELECT" not in everything
    assert "index text" not in everything


def test_span_paragraphs_and_anchors_are_kept() -> None:
    first, second = extract_page(PAGE).sections
    assert "column-oriented database" in first.text
    assert second.anchor == "analytics"
    assert "Direct link" not in second.heading


def test_page_title_and_date() -> None:
    page = extract_page(PAGE)
    assert page.title == "What is X? - Docs"
    assert page.published_at == datetime(2026, 8, 23, 10, 0, tzinfo=UTC)


def test_dropped_sections_are_reported_not_silent() -> None:
    assert extract_page(PAGE).dropped == ("Tiny",)


def test_date_falls_back_to_embedded_json() -> None:
    page = (
        "<html><head><title>T</title></head><body><main><h1>T</h1>"
        "<p>One sentence here is fine. Another one follows it. A third.</p></main>"
        '<script>{"dateModified":"2026-01-02T03:04:05.000Z"}</script></body></html>'
    )
    assert extract_page(page).published_at == datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)


def test_page_without_main_content_yields_no_sections() -> None:
    assert extract_page("<html><body><p>Hi.</p></body></html>").sections == ()


def test_speakable_sentences_drops_labels_visuals_and_code() -> None:
    text = (
        "Row-oriented DBMS\n\n"
        "Analytics queries, e.g. aggregations over many rows, run over huge datasets. "
        "As you can see in the diagram above, it is fast. "
        "Run `SELECT 1` to try it yourself today.\n\n"
        "Lead-in to a code sample that ends with a colon:"
    )
    assert speakable_sentences(text) == [
        "Analytics queries, e.g. aggregations over many rows, run over huge datasets."
    ]


def test_near_repeated_sentences_are_kept_once() -> None:
    text = (
        "X is a column-oriented SQL database management system for analytical processing.\n\n"
        "X is a high-performance, column-oriented SQL database management system for analytical "
        "processing. It is available as open-source software and as a cloud offering."
    )
    assert speakable_sentences(text) == [
        "X is a column-oriented SQL database management system for analytical processing.",
        "It is available as open-source software and as a cloud offering.",
    ]


def test_section_cannot_open_on_a_dangling_sentence_or_a_link() -> None:
    text = (
        "Such a level of speed needs the right layout. Rows are stored one after another on disk. "
        "This layout suits lookups of single rows. To learn why, see the Layout guide here."
    )
    assert speakable_sentences(text) == [
        "Rows are stored one after another on disk.",
        "This layout suits lookups of single rows.",  # fine mid-section: only the opener is checked
    ]


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://arxiv.org/abs/1", ReliabilityTier.PRIMARY),
        ("https://www.bbc.co.uk/news", ReliabilityTier.ESTABLISHED),
        ("https://example.org/x", ReliabilityTier.UNVERIFIED),
        ("https://notarxiv.org/x", ReliabilityTier.UNVERIFIED),
    ],
)
def test_source_tier(url: str, expected: ReliabilityTier) -> None:
    tiers = {"primary": ["arxiv.org"], "established": ["bbc.co.uk"], "default": "unverified"}
    assert source_tier(url, tiers) is expected
