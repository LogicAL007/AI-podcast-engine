from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from podcast_engine.api import dependencies
from podcast_engine.api.controllers.episodes_controller import EpisodeController
from podcast_engine.api.controllers.feeds_controller import FeedController
from podcast_engine.api.controllers.ops_controller import OpsController
from podcast_engine.api.controllers.shows_controller import ShowController
from podcast_engine.api.controllers.sources_controller import SourceController
from podcast_engine.api.controllers.uploads_controller import UploadController
from podcast_engine.api.main import create_app
from podcast_engine.api.services.episodes_service import EpisodeService
from podcast_engine.api.services.feeds_service import FeedService
from podcast_engine.api.services.ops_service import Check, OpsService
from podcast_engine.api.services.shows_service import ShowService
from podcast_engine.api.services.sources_service import SourceService
from podcast_engine.api.services.uploads_service import UploadService
from podcast_engine.common.queue import Stage
from tests.unit.api.fakes import (
    FakeEpisodeRepository,
    FakeObjectStore,
    FakeShowRepository,
    FakeSourceRepository,
    FakeUploadRepository,
)

MAX_UPLOAD_BYTES = 1024


class Harness:
    """A test client plus handles on everything behind it."""

    def __init__(self) -> None:
        self.shows = FakeShowRepository()
        self.episodes = FakeEpisodeRepository()
        self.sources = FakeSourceRepository()
        self.uploads = FakeUploadRepository()
        self.store = FakeObjectStore()
        self.enqueued: list[UUID] = []
        self.stages: list[tuple[UUID, Stage]] = []
        self.feeds_rebuilt: list[UUID] = []
        self.queue_down = False
        self.checks: dict[str, Check] = {"database": lambda: None, "queue": lambda: None}
        app = create_app()
        overrides = app.dependency_overrides
        overrides[dependencies.get_show_controller] = lambda: ShowController(
            ShowService(self.shows)
        )
        overrides[dependencies.get_episode_controller] = lambda: EpisodeController(
            EpisodeService(
                self.episodes, self.shows, self._enqueue, self.store, self.feeds_rebuilt.append
            )
        )
        overrides[dependencies.get_source_controller] = lambda: SourceController(
            SourceService(self.sources, self.shows)
        )
        overrides[dependencies.get_upload_controller] = lambda: UploadController(
            UploadService(self.uploads, self.shows, self.store, max_bytes=MAX_UPLOAD_BYTES)
        )
        overrides[dependencies.get_feed_controller] = lambda: FeedController(
            FeedService(self.store)
        )
        overrides[dependencies.get_ops_controller] = lambda: OpsController(OpsService(self.checks))
        self.client = TestClient(app)

    def _enqueue(self, episode_id: UUID, stage: Stage) -> None:
        if self.queue_down:
            raise ConnectionError("redis unreachable")
        self.enqueued.append(episode_id)
        self.stages.append((episode_id, stage))


@pytest.fixture
def harness() -> Harness:
    return Harness()
