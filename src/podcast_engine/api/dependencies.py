"""FastAPI dependency providers: the one place that wires layers together.

Tests replace these with ``app.dependency_overrides`` to swap in fakes.
"""

from collections.abc import Iterator
from functools import lru_cache
from typing import Annotated
from uuid import UUID

from fastapi import Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from podcast_engine.api.controllers.episodes_controller import EpisodeController
from podcast_engine.api.controllers.feeds_controller import FeedController
from podcast_engine.api.controllers.home_controller import HomeController
from podcast_engine.api.controllers.ops_controller import OpsController
from podcast_engine.api.controllers.shows_controller import ShowController
from podcast_engine.api.controllers.sources_controller import SourceController
from podcast_engine.api.controllers.uploads_controller import UploadController
from podcast_engine.api.repositories.episodes_repository import PostgresEpisodeRepository
from podcast_engine.api.repositories.shows_repository import PostgresShowRepository
from podcast_engine.api.repositories.sources_repository import PostgresSourceRepository
from podcast_engine.api.repositories.uploads_repository import PostgresUploadRepository
from podcast_engine.api.services.episodes_service import EnqueueStage, EpisodeService, RebuildFeed
from podcast_engine.api.services.feeds_service import FeedService
from podcast_engine.api.services.ops_service import Check, OpsService
from podcast_engine.api.services.shows_service import ShowService
from podcast_engine.api.services.sources_service import SourceService
from podcast_engine.api.services.uploads_service import UploadService
from podcast_engine.common.config import get_settings
from podcast_engine.common.db import get_engine
from podcast_engine.common.queue import Stage, celery_app, dispatch, dispatch_feed_rebuild
from podcast_engine.common.storage import ObjectStore, S3ObjectStore


def get_session() -> Iterator[Session]:
    """One database session per request; anything uncommitted is rolled back on close."""
    with Session(get_engine()) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]


@lru_cache
def get_object_store() -> ObjectStore:
    return S3ObjectStore(get_settings())


def get_enqueue_stage() -> EnqueueStage:
    def enqueue(episode_id: UUID, stage: Stage) -> None:
        dispatch(stage, episode_id=str(episode_id))

    return enqueue


def get_rebuild_feed() -> RebuildFeed:
    def rebuild(show_id: UUID) -> None:
        dispatch_feed_rebuild(str(show_id))

    return rebuild


def get_show_controller(session: SessionDep) -> ShowController:
    return ShowController(ShowService(PostgresShowRepository(session)))


def get_episode_controller(
    session: SessionDep,
    enqueue: Annotated[EnqueueStage, Depends(get_enqueue_stage)],
    store: Annotated[ObjectStore, Depends(get_object_store)],
    rebuild_feed: Annotated[RebuildFeed, Depends(get_rebuild_feed)],
) -> EpisodeController:
    service = EpisodeService(
        PostgresEpisodeRepository(session),
        PostgresShowRepository(session),
        enqueue,
        store,
        rebuild_feed,
    )
    return EpisodeController(service)


def get_feed_controller(store: Annotated[ObjectStore, Depends(get_object_store)]) -> FeedController:
    return FeedController(FeedService(store))


def get_source_controller(session: SessionDep) -> SourceController:
    return SourceController(
        SourceService(PostgresSourceRepository(session), PostgresShowRepository(session))
    )


def get_upload_controller(
    session: SessionDep, store: Annotated[ObjectStore, Depends(get_object_store)]
) -> UploadController:
    service = UploadService(
        PostgresUploadRepository(session),
        PostgresShowRepository(session),
        store,
        max_bytes=get_settings().max_upload_mb * 1024 * 1024,
    )
    return UploadController(service)


def _check_database() -> None:
    with get_engine().connect() as connection:
        connection.execute(text("SELECT 1"))


def _check_queue() -> None:
    with celery_app.connection_for_read() as connection:
        connection.ensure_connection(max_retries=1, timeout=3)


def _check_storage() -> None:
    store = get_object_store()
    if isinstance(store, S3ObjectStore):
        store.check()


def get_readiness_checks() -> dict[str, Check]:
    return {"database": _check_database, "queue": _check_queue, "storage": _check_storage}


def get_ops_controller(
    checks: Annotated[dict[str, Check], Depends(get_readiness_checks)],
) -> OpsController:
    return OpsController(OpsService(checks))


def get_home_controller() -> HomeController:
    return HomeController()
