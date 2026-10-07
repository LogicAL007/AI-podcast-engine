"""Ingest: fetch sources and detect which items changed."""

import hashlib
from uuid import UUID

from podcast_engine.common.queue import Stage


def content_hash(text: str) -> str:
    """Hash of whitespace-normalised text, so reflowed but identical content is unchanged."""
    normalised = " ".join(text.split())
    return hashlib.sha256(normalised.encode("utf-8")).hexdigest()


def has_changed(previous_hash: str | None, text: str) -> bool:
    """True for a new item (no previous hash) or one whose content hash differs."""
    return previous_hash != content_hash(text)


def ingest_sources(episode_id: UUID) -> Stage | None:
    """FR2: fetch the show's feeds, URLs, PDFs and search results; store changed items."""
    raise NotImplementedError("ingest_sources: fetch with feedparser/trafilatura/PyMuPDF")
