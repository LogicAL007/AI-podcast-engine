"""Ingest: fetch sources and detect which items changed."""

from collections.abc import Callable, Mapping
from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

import yaml

from podcast_engine.common.context import PipelineContext, get_context
from podcast_engine.common.logging import get_logger
from podcast_engine.common.models import EpisodeStatus, ReliabilityTier
from podcast_engine.common.queue import Stage
from podcast_engine.common.repository import ShowRecord, SourceDoc
from podcast_engine.common.text import content_hash

__all__ = ["content_hash", "has_changed", "ingest_sources", "load_docs"]

if TYPE_CHECKING:
    from podcast_engine.stages.ingest.extract import Section
    from podcast_engine.stages.ingest.search import SearchProvider

log = get_logger("ingest")


def has_changed(previous_hash: str | None, text: str) -> bool:
    """True for a new item (no previous hash) or one whose content hash differs."""
    return previous_hash != content_hash(text)


def _add_search_results(
    show: ShowRecord,
    search: "SearchProvider",
    count: int,
    add: Callable[[str, "Section", datetime | None, ReliabilityTier], None],
    tiers: Mapping[str, object],
) -> None:
    """Read the top results of each of the show's searches like its own pages, skipping URLs it
    already lists and results that cannot be read."""
    from podcast_engine.stages.ingest.extract import extract_page, source_tier

    read = set(show.sources)
    for query in show.search_queries:
        # A failed search raises, so the stage retries: carrying on would make a refresh see
        # every result as removed and drop their segments.
        hits = search.search(query, language=show.language, count=count)
        used = 0
        for hit in hits:
            if hit.url in read:
                continue
            read.add(hit.url)
            try:
                page = extract_page(search.page(hit))
            except Exception as error:  # one unreadable result must not sink the episode
                log.warning("search_result_skipped", url=hit.url, reason=str(error)[:200])
                continue
            for section in page.sections:
                add(hit.url, section, page.published_at, source_tier(hit.url, tiers))
            used += bool(page.sections)
        log.info("search_ingested", query=query, results=len(hits), read=used)


def _search(ctx: PipelineContext) -> "SearchProvider | None":
    from podcast_engine.stages.ingest.search import make_search

    return getattr(ctx, "search", None) or make_search(ctx.settings)


def load_docs(show: ShowRecord, ctx: PipelineContext) -> list[SourceDoc]:
    """Every section of the show's sources, in order: its URLs (web pages or RSS/Atom feeds),
    the top results of its searches, then its uploaded PDFs. Each section can change and be
    cited on its own."""
    from podcast_engine.stages.ingest.extract import extract_page, source_tier
    from podcast_engine.stages.ingest.feeds import feed_sections, looks_like_feed
    from podcast_engine.stages.ingest.search import read_page

    tiers_file = ctx.settings.config_dir / "source_tiers.yaml"
    tiers = yaml.safe_load(tiers_file.read_text(encoding="utf-8")) if tiers_file.exists() else {}
    fetch = ctx.fetch or read_page
    docs: list[SourceDoc] = []

    # "Section" is quoted: it is imported only for type checking, and Python 3.12 (the images)
    # evaluates a nested function's annotations when it is defined, unlike 3.14.
    def add(
        url: str, section: "Section", published: datetime | None, tier: ReliabilityTier
    ) -> None:
        docs.append(
            SourceDoc(
                url=f"{url}#{section.anchor}" if section.anchor and "#" not in url else url,
                title=section.heading,
                text=section.text,
                published_at=published,
                reliability=tier,
                position=len(docs),
            )
        )

    for url in show.sources:
        body = fetch(url)
        if looks_like_feed(body):
            title, sections = feed_sections(body, fetch, max_items=ctx.settings.feed_max_items)
            if not sections:
                raise ValueError(f"The feed at {url} has no entries with usable text")
            for link, section, published in sections:
                add(link or url, section, published, source_tier(link or url, tiers or {}))
            log.info("feed_ingested", url=url, title=title, sections=len(sections))
            continue
        page = extract_page(body)
        if not page.sections:
            raise ValueError(f"No usable text found at {url}")
        for section in page.sections:
            add(url, section, page.published_at, source_tier(url, tiers or {}))
        log.info("page_ingested", url=url, sections=len(page.sections), dropped=list(page.dropped))

    search = _search(ctx) if show.search_queries else None
    if search is not None:
        _add_search_results(show, search, ctx.settings.search_results, add, tiers or {})

    for upload in ctx.repo.list_uploads(show.show_id):
        from podcast_engine.stages.ingest.pdf import extract_pdf

        pdf = extract_pdf(ctx.store.get(upload.object_key), filename=upload.filename)
        if not pdf.sections:
            raise ValueError(f"No usable text found in the upload {upload.filename}")
        # Citations link to the file through the API, at the page the passage is on.
        file_url = (
            f"{ctx.settings.public_feed_base_url}/api/v1/shows/{show.show_id}"
            f"/uploads/{upload.upload_id}/file"
        )
        for section in pdf.sections:
            # The creator supplied it, so it ranks as an established source.
            add(f"{file_url}#{section.anchor}", section, None, ReliabilityTier.ESTABLISHED)
        log.info("upload_ingested", upload=upload.filename, sections=len(pdf.sections))
    return docs


# Not ingested: pages behind authentication.
def ingest_sources(episode_id: UUID, ctx: PipelineContext | None = None) -> Stage | None:
    """FR2: fetch the show's pages, store their sections, and record which ones changed.

    The first episode of a show uses every section. A later one (a refresh, FR8) only regenerates
    segments whose sections changed; if nothing changed it stops here: there is nothing new to say.
    """
    ctx = ctx or get_context()
    episode = ctx.repo.get_episode(episode_id)
    show = ctx.repo.get_show(episode.show_id)
    if not show.sources and not show.search_queries and not ctx.repo.list_uploads(show.show_id):
        raise ValueError("The show has no sources: add a URL, a search or a PDF.")
    result = ctx.repo.sync_items(show.show_id, load_docs(show, ctx))
    previous = [e for e in ctx.repo.list_published(show.show_id) if e.episode_id != episode_id]
    log.info(
        "sources_synced",
        episode_id=str(episode_id),
        changed=len(result.changed),
        removed=len(result.removed),
        unchanged=len(result.unchanged),
        previous_episode=str(previous[0].episode_id) if previous else None,
    )
    # A rebuild regenerates every segment, so it goes on even when nothing changed.
    if previous and not episode.rebuild and not result.changed and not result.removed:
        ctx.repo.update_episode(
            episode_id,
            status=EpisodeStatus.UNCHANGED,
            error=(
                f"No source changed since episode {previous[0].episode_id}; nothing to regenerate."
            ),
        )
        return None
    ctx.repo.update_episode(
        episode_id,
        changed_item_ids=result.changed if previous and not episode.rebuild else None,
        revision=previous[0].revision + 1 if previous else 1,
    )
    return Stage.INDEX
