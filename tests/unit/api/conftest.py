from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from podcast_engine.api import dependencies
from podcast_engine.api.controllers.episodes_controller import EpisodeController
from podcast_engine.api.controllers.feeds_controller import FeedController
from podcast_engine.api.controllers.shows_controller import ShowController
from podcast_engine.api.main import create_app
from podcast_engine.api.services.episodes_service import EpisodeService
from podcast_engine.api.services.feeds_service import FeedService
from podcast_engine.api.services.shows_service import ShowService
from tests.unit.api.fakes import FakeEpisodeRepository, FakeObjectStore, FakeShowRepository


class Harness:
    """A test client plus handles on everything behind it."""

    def __init__(self) -> None:
        self.shows = FakeShowRepository()
        self.episodes = FakeEpisodeRepository()
        self.store = FakeObjectStore()
        self.enqueued: list[UUID] = []
        self.queue_down = False
        app = create_app()
        app.dependency_overrides[dependencies.get_show_controller] = lambda: ShowController(
            ShowService(self.shows)
        )
        app.dependency_overrides[dependencies.get_episode_controller] = lambda: EpisodeController(
            EpisodeService(self.episodes, self.shows, self._enqueue, self.store)
        )
        app.dependency_overrides[dependencies.get_feed_controller] = lambda: FeedController(
            FeedService(self.store)
        )
        self.client = TestClient(app)

    def _enqueue(self, episode_id: UUID) -> None:
        if self.queue_down:
            raise ConnectionError("redis unreachable")
        self.enqueued.append(episode_id)


@pytest.fixture
def harness() -> Harness:
    return Harness()
