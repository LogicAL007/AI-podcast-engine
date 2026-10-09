"""Ingest: fetch sources and detect which items changed."""

from uuid import UUID

import yaml

from podcast_engine.common.context import PipelineContext, get_context
from podcast_engine.common.logging import get_logger
from podcast_engine.common.models import EpisodeStatus, ReliabilityTier
from podcast_engine.common.queue import Stage
from podcast_engine.common.repository import SourceDoc
from podcast_engine.common.text import content_hash

__all__ = ["content_hash", "has_changed", "ingest_sources", "load_url_docs"]

log = get_logger("ingest")


def has_changed(previous_hash: str | None, text: str) -> bool:
    """True for a new item (no previous hash) or one whose content hash differs."""
    return previous_hash != content_hash(text)


def load_url_docs(urls: list[str], ctx: PipelineContext) -> list[SourceDoc]:
    """Fetch pages and return one document per section, so each can change and be cited alone."""
    from podcast_engine.stages.ingest.extract import extract_page, fetch_html, source_tier

    tiers_file = ctx.settings.config_dir / "source_tiers.yaml"
    tiers = yaml.safe_load(tiers_file.read_text(encoding="utf-8")) if tiers_file.exists() else {}
    fetch = ctx.fetch or fetch_html
    docs: list[SourceDoc] = []
    for url in urls:
        page = extract_page(fetch(url))
        if not page.sections:
            raise ValueError(f"No usable text found at {url}")
        tier: ReliabilityTier = source_tier(url, tiers or {})
        for section in page.sections:
            docs.append(
                SourceDoc(
                    url=f"{url}#{section.anchor}" if section.anchor else url,
                    title=section.heading,
                    text=section.text,
                    published_at=page.published_at,
                    reliability=tier,
                    position=len(docs),
                )
            )
        log.info("page_ingested", url=url, sections=len(page.sections), dropped=list(page.dropped))
    return docs


# TODO (from the notebook): RSS feeds without summaries, pages behind authentication, and PDF
# uploads (PyMuPDF) are not ingested yet; only web pages are.
def ingest_sources(episode_id: UUID, ctx: PipelineContext | None = None) -> Stage | None:
    """FR2: fetch the show's pages, store their sections, and record which ones changed.

    The first episode of a show uses every section. A later one (a refresh, FR8) only regenerates
    segments whose sections changed; if nothing changed it stops here: there is nothing new to say.
    """
    ctx = ctx or get_context()
    episode = ctx.repo.get_episode(episode_id)
    show = ctx.repo.get_show(episode.show_id)
    if not show.sources:
        raise ValueError("The show has no sources: add at least one URL.")
    result = ctx.repo.sync_items(show.show_id, load_url_docs(show.sources, ctx))
    previous = [e for e in ctx.repo.list_published(show.show_id) if e.episode_id != episode_id]
    log.info(
        "sources_synced",
        episode_id=str(episode_id),
        changed=len(result.changed),
        removed=len(result.removed),
        unchanged=len(result.unchanged),
        previous_episode=str(previous[0].episode_id) if previous else None,
    )
    if previous and not result.changed and not result.removed:
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
        changed_item_ids=result.changed if previous else None,
        revision=previous[0].revision + 1 if previous else 1,
    )
    return Stage.INDEX
