"""RSS and Atom feeds as sources (FR2): each recent entry becomes one or more citable sections.

An entry whose summary is long enough to talk about is used as it is. Many feeds carry only a
title, a teaser or nothing; for those the entry's own page is fetched and read like any web page,
so a feed without summaries still yields material (the notebook's TODO).
"""

import calendar
import re
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from podcast_engine.common.logging import get_logger
from podcast_engine.common.text import speakable_sentences
from podcast_engine.stages.ingest.extract import MIN_SECTION_SENTENCES, Section, extract_page

log = get_logger("ingest.feeds")

MIN_SUMMARY_WORDS = 40  # shorter summaries are teasers: read the linked page instead


def looks_like_feed(body: str) -> bool:
    """True for an RSS or Atom document (checked on the first few hundred bytes)."""
    head = body.lstrip()[:600].lower()
    return "<rss" in head or "<feed" in head or ("<?xml" in head and "<channel" in body[:2000])


def _text(html: str) -> str:
    """Summary HTML as plain paragraphs."""
    paragraphs = re.split(r"</p>|<br\s*/?>", html, flags=re.IGNORECASE)
    cleaned = (" ".join(re.sub(r"<[^>]+>", " ", p).split()) for p in paragraphs)
    return "\n\n".join(p for p in cleaned if p)


def _published(entry: Any) -> datetime | None:
    parts = entry.get("published_parsed") or entry.get("updated_parsed")
    # feedparser gives a UTC struct_time.
    return datetime.fromtimestamp(calendar.timegm(parts), tz=UTC) if parts else None


def feed_sections(
    body: str, fetch: Callable[[str], str], *, max_items: int
) -> tuple[str, list[tuple[str, Section, datetime | None]]]:
    """The feed's title and its sections as (url, section, published), newest entries first."""
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
        except Exception as error:  # one unreachable article should not lose the whole feed
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
