"""Retrieve and plan: freshness-aware ranking, then the segment outline."""

import math
from datetime import UTC, datetime
from uuid import UUID

from podcast_engine.common.queue import Stage


def recency_score(published_at: datetime | None, *, now: datetime, half_life_days: float) -> float:
    """Exponential decay in (0, 1]: 1.0 for brand-new items, 0.5 after one half-life.

    Items with no publish date score 0 so they never outrank dated ones on recency alone.
    """
    if published_at is None:
        return 0.0
    if half_life_days <= 0:
        raise ValueError("half_life_days must be positive")
    age_days = max((now - published_at).total_seconds() / 86_400, 0.0)
    return math.pow(0.5, age_days / half_life_days)


def combined_score(relevance: float, recency: float, *, recency_weight: float) -> float:
    """Blend relevance and recency: a daily show uses a high weight, an explainer a low one."""
    if not 0.0 <= recency_weight <= 1.0:
        raise ValueError("recency_weight must be in [0, 1]")
    return (1 - recency_weight) * relevance + recency_weight * recency


def utc_now() -> datetime:
    return datetime.now(UTC)


def retrieve_and_plan(episode_id: UUID) -> Stage | None:
    """FR3: rank passages for the topic and build the segment outline tagged with sources."""
    raise NotImplementedError("retrieve_and_plan: query pgvector, then outline with the LLM")
