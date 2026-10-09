"""FastAPI dependency providers: the one place that wires layers together.

Tests replace these with ``app.dependency_overrides`` to swap in fakes.
"""

from collections.abc import Callable, Iterator
from functools import lru_cache
from typing import Annotated
from uuid import UUID

from fastapi import Depends
from sqlalchemy.orm import Session

from podcast_engine.api.controllers.episodes_controller import EpisodeController
from podcast_engine.api.controllers.feeds_controller import FeedController
from podcast_engine.api.controllers.shows_controller import ShowController
from podcast_engine.api.repositories.episodes_repository import PostgresEpisodeRepository
from podcast_engine.api.repositories.shows_repository import PostgresShowRepository
from podcast_engine.api.services.episodes_service import EnqueueEpisode, EpisodeService
from podcast_engine.api.services.feeds_service import FeedService
from podcast_engine.api.services.shows_service import ShowService
from podcast_engine.common.config import get_settings
from podcast_engine.common.db import get_engine
from podcast_engine.common.queue import Stage, dispatch
from podcast_engine.common.storage import ObjectStore, S3ObjectStore


def get_session() -> Iterator[Session]:
    """One database session per request; anything uncommitted is rolled back on close."""
    with Session(get_engine()) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]


@lru_cache
def get_object_store() -> ObjectStore:
    return S3ObjectStore(get_settings())


def get_enqueue_episode() -> EnqueueEpisode:
    def enqueue(episode_id: UUID) -> None:
        dispatch(Stage.INGEST, episode_id=str(episode_id))

    return enqueue


def get_show_controller(session: SessionDep) -> ShowController:
    return ShowController(ShowService(PostgresShowRepository(session)))


def get_episode_controller(
    session: SessionDep,
    enqueue: Annotated[Callable[[UUID], None], Depends(get_enqueue_episode)],
) -> EpisodeController:
    service = EpisodeService(
        PostgresEpisodeRepository(session), PostgresShowRepository(session), enqueue
    )
    return EpisodeController(service)


def get_feed_controller(store: Annotated[ObjectStore, Depends(get_object_store)]) -> FeedController:
    return FeedController(FeedService(store))
