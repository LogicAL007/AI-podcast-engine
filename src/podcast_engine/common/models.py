"""Domain models passed between stages.

Stages exchange only ids over the queue (workers are stateless); these models describe what
each stage reads from and writes to Postgres and object storage.
"""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class Tone(StrEnum):
    CASUAL = "casual"
    NEUTRAL = "neutral"
    FORMAL = "formal"


class ExpertiseLevel(StrEnum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    EXPERT = "expert"


class ReliabilityTier(StrEnum):
    PRIMARY = "primary"
    ESTABLISHED = "established"
    UNVERIFIED = "unverified"


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True)


class ShowConfig(_Model):
    """FR1: what a creator configures for a show."""

    show_id: UUID
    topic: str
    tone: Tone = Tone.NEUTRAL
    target_minutes: int = Field(default=7, ge=1, le=30)
    host_count: int = Field(default=2, ge=1, le=4)
    language: str = "en"
    expertise: ExpertiseLevel = ExpertiseLevel.INTERMEDIATE
    sources: tuple[str, ...] = ()


class SourceItem(_Model):
    """One ingested document, identified by a content hash for change detection."""

    item_id: UUID
    show_id: UUID
    url: str
    title: str
    published_at: datetime | None
    content_hash: str
    reliability: ReliabilityTier = ReliabilityTier.UNVERIFIED


class Passage(_Model):
    """A retrieved chunk with its relevance and recency scores."""

    chunk_id: UUID
    item_id: UUID
    text: str
    relevance: float
    recency: float


class Segment(_Model):
    """One outline segment, tagged with the sources it uses (drives incremental regen)."""

    segment_id: UUID
    position: int
    title: str
    source_item_ids: tuple[UUID, ...]


class Claim(_Model):
    """A factual statement in the script and the passage that supports it (FR5)."""

    claim_id: UUID
    text: str
    chunk_ids: tuple[UUID, ...] = ()


class ScriptLine(_Model):
    speaker: str
    text: str
    claims: tuple[Claim, ...] = ()


class FactCheckReport(_Model):
    """FR9: result of the gate between script and voice."""

    episode_id: UUID
    unsupported: tuple[Claim, ...]
    total_claims: int

    @property
    def passed(self) -> bool:
        return not self.unsupported

    @property
    def support_rate(self) -> float:
        if self.total_claims == 0:
            return 1.0
        return 1 - len(self.unsupported) / self.total_claims


class EpisodeStatus(StrEnum):
    """Lifecycle of an episode; the pipeline stages and the API both read and write it."""

    QUEUED = "queued"
    PROCESSING = "processing"
    NEEDS_REVIEW = "needs_review"
    PUBLISHED = "published"
    FAILED = "failed"
