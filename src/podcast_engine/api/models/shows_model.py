"""Request and response schemas for the shows API."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field

from podcast_engine.common.models import ExpertiseLevel, Tone

Topic = Annotated[str, Field(min_length=3, max_length=200)]
Language = Annotated[str, Field(pattern=r"^[a-z]{2}(-[A-Z]{2})?$", examples=["en", "fr-CA"])]
Minutes = Annotated[int, Field(ge=1, le=30)]
HostCount = Annotated[int, Field(ge=1, le=4)]
SourceUrls = Annotated[list[AnyHttpUrl], Field(max_length=50)]


class ShowCreate(BaseModel):
    """FR1: what a creator supplies to set up a show."""

    topic: Topic
    tone: Tone = Tone.NEUTRAL
    target_minutes: Minutes = 7
    host_count: HostCount = 2
    language: Language = "en"
    expertise: ExpertiseLevel = ExpertiseLevel.INTERMEDIATE
    sources: SourceUrls = []


class ShowUpdate(BaseModel):
    """Partial update: omitted or null fields are left unchanged."""

    topic: Topic | None = None
    tone: Tone | None = None
    target_minutes: Minutes | None = None
    host_count: HostCount | None = None
    language: Language | None = None
    expertise: ExpertiseLevel | None = None
    sources: SourceUrls | None = None


class ShowRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    show_id: UUID
    topic: str
    tone: Tone
    target_minutes: int
    host_count: int
    language: str
    expertise: ExpertiseLevel
    sources: list[str]
    created_at: datetime
