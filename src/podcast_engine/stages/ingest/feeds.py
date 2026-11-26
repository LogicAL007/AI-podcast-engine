import calendar
import re
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from podcast_engine.common.logging import get_logger
from podcast_engine.common.text import speakable_sentences
from podcast_engine.stages.ingest.extract import MIN_SECTION_SENTENCES, Section, extract_page

log = get_logger("ingest.feeds")

MIN_SUMMARY_WORDS = 40


def looks_like_feed(body: str) -> bool:
    """Tell whether a fetched document is an RSS or Atom feed.

    Only the first few hundred bytes are checked.

    Args:
        body: The fetched document.

    Returns:
        True for an RSS or Atom document.
    """
    head = body.lstrip()[:600].lower()
    return "<rss" in head or "<feed" in head or ("<?xml" in head and "<channel" in body[:2000])


def _text(html: str) -> str:
    """Turn summary HTML into plain paragraphs.

    Args:
        html: The entry's summary or content HTML.

    Returns:
        The text, with paragraphs separated by blank lines.
    """
    paragraphs = re.split(r"</p>|<br\s*/?>", html, flags=re.IGNORECASE)
    cleaned = (" ".join(re.sub(r"<[^>]+>", " ", p).split()) for p in paragraphs)
    return "\n\n".join(p for p in cleaned if p)


def _published(entry: Any) -> datetime | None:
    """Return when a feed entry was published, else when it was last updated.

    Args:
        entry: A feedparser entry.

    Returns:
        The date in UTC (feedparser gives a UTC struct_time), or None when the entry has neither.
    """
    parts = entry.get("published_parsed") or entry.get("updated_parsed")
    return datetime.fromtimestamp(calendar.timegm(parts), tz=UTC) if parts else None


def feed_sections(
    body: str, fetch: Callable[[str], str], *, max_items: int
) -> tuple[str, list[tuple[str, Section, datetime | None]]]:
    """Read an RSS or Atom feed's recent entries as citable sections (FR2).

    An entry whose summary is long enough to talk about (at least 40 words in enough speakable
    sentences) is used as it is. Many feeds carry only a title, a teaser or nothing; for those the
    entry's own page is fetched and read like any web page, so a feed without summaries still yields
    material. One unreachable article is skipped and logged, rather than losing the whole feed.

    Args:
        body: The feed document.
        fetch: Fetches a URL and returns its HTML.
        max_items: Most entries to read.

    Returns:
        The feed's title, and its sections as (url, section, published) in the feed's order, newest
        first.

    Raises:
        ValueError: The document is not a readable feed.
    """
    import feedparser

    parsed = feedparser.parse(body)
    if parsed.bozo and not parsed.entries:
        raise ValueError(f"not a readable feed: {parsed.bozo_exception}")
    out: list[tuple[str, Section, datetime | None]] = []
    for entry in parsed.entries[:max_items]:
        link = entry.get("link", "")
        title = " ".join(entry.get("title", "").split()) or "Untitled entry"
        published = _published(entry)
        content = entry.get("content") or []
        summary = _text(content[0].get("value", "") if content else entry.get("summary", ""))
        if (
            len(summary.split()) >= MIN_SUMMARY_WORDS
            and len(speakable_sentences(summary)) >= MIN_SECTION_SENTENCES
        ):
            out.append((link, Section(heading=title, anchor="", text=summary), published))
            continue
        if not link:
            log.info("feed_entry_skipped", title=title, reason="no summary and no link")
            continue
        try:
            page = extract_page(fetch(link))
        except Exception as error:
            log.warning("feed_entry_skipped", url=link, reason=str(error)[:200])
            continue
        for section in page.sections:
            heading = title if section.heading == page.title else f"{title}: {section.heading}"
            url = f"{link}#{section.anchor}" if section.anchor else link
            out.append(
                (
                    url,
                    section.model_copy(update={"heading": heading}),
                    published or page.published_at,
                )
            )
    return " ".join(parsed.feed.get("title", "").split()), out
