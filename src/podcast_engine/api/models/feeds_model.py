"""Schemas for the feeds API."""

from uuid import UUID

from pydantic import BaseModel

RSS_MEDIA_TYPE = "application/rss+xml"


class RssFeed(BaseModel):
    """A show's rendered RSS document, as written by the publish stage."""

    show_id: UUID
    content: bytes
