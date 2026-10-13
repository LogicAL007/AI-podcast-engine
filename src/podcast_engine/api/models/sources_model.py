"""Response schemas for a show's ingested sources."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from podcast_engine.common.models import ReliabilityTier


class SourceRead(BaseModel):
    """One section of a source, as last ingested: the unit that is cited and change-detected."""

    model_config = ConfigDict(from_attributes=True)

    item_id: UUID = Field(description="The section's id; claims cite its passages")
    url: str = Field(
        description="Where it comes from, with the section's anchor",
        examples=["https://clickhouse.com/docs/get-started/about/intro#sql-support"],
    )
    title: str = Field(description="The section's heading", examples=["SQL support"])
    position: int = Field(description="Order across the show's sources, from 0")
    reliability: ReliabilityTier = Field(description="Reliability tier, used in ranking")
    content_hash: str = Field(description="Hash of the text; a change marks the section changed")
    words: int = Field(description="Length of the section's text in words")
    chunks: int = Field(description="Passages it was split into for retrieval")
    published_at: datetime | None = Field(description="The source's own date, if it gives one")
    fetched_at: datetime = Field(description="When it was last fetched")
