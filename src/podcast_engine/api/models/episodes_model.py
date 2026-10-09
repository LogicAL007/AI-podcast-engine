"""Response schemas for the episodes API."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from podcast_engine.common.models import EpisodeStatus


class EpisodeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    episode_id: UUID
    show_id: UUID
    status: EpisodeStatus
    rewrite_count: int
    created_at: datetime
    published_at: datetime | None
