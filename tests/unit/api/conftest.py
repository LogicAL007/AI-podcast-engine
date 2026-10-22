from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from podcast_engine.api import dependencies
from podcast_engine.api.controllers.auth_controller import AuthController
from podcast_engine.api.controllers.episodes_controller import EpisodeController
from podcast_engine.api.controllers.feeds_controller import FeedController
from podcast_engine.api.controllers.ops_controller import OpsController
from podcast_engine.api.controllers.shows_controller import ShowController
from podcast_engine.api.controllers.sources_controller import SourceController
from podcast_engine.api.controllers.uploads_controller import UploadController
from podcast_engine.api.main import create_app
from podcast_engine.api.models.auth_model import CurrentUser
from podcast_engine.api.repositories.login_attempts_repository import (
    LimitsConfig,
    MemoryLoginAttempts,
)
from podcast_engine.api.services.auth_service import AuthService
from podcast_engine.api.services.episodes_service import EpisodeService
from podcast_engine.api.services.feeds_service import FeedService
from podcast_engine.api.services.ops_service import Check, OpsService
from podcast_engine.api.services.shows_service import ShowService
from podcast_engine.api.services.sources_service import SourceService
from podcast_engine.api.services.uploads_service import UploadService
from podcast_engine.common.mailer import Email
from podcast_engine.common.queue import Stage
from tests.unit.api.fakes import (
    FakeAuthRepository,
    FakeEpisodeRepository,
    FakeObjectStore,
    FakeSecurityEventRepository,
    FakeShowRepository,
    FakeSourceRepository,
    FakeUploadRepository,
)

MAX_UPLOAD_BYTES = 1024
TOKEN_KEY = b"test-only token key"
ADMIN = CurrentUser(
    user_id=uuid4(),
    email="admin@example.org",
    role="admin",
    token_id=uuid4(),
    token_kind="session",
    expires_at=datetime.now(UTC) + timedelta(days=180),
)


class RecordingMailer:
    def __init__(self) -> None:
        self.sent: list[Email] = []

    def send(self, email: Email) -> None:
        self.sent.append(email)


LIMITS = LimitsConfig(
    max_failures=5, address_max_failures=20, window_s=900, lockout_s=900, reset_max=3
)


class Harness:
    """A test client plus handles on everything behind it."""

    def __init__(self, *, signed_in: bool = True) -> None:
        """``signed_in``: every request acts as an admin. False: requests go through real login."""
        self.auth = FakeAuthRepository()
        self.now = datetime.now(UTC)
        self.seconds = 0.0  # the login counters' clock
        self.attempts = MemoryLoginAttempts(LIMITS, clock=lambda: self.seconds)
        self.mailer = RecordingMailer()
        self.events = FakeSecurityEventRepository()
        self.auth_service = AuthService(
            self.auth,
            token_key=TOKEN_KEY,
            token_days=180,
            now=lambda: self.now,
            claim_unowned=lambda owner: self.shows.claim_unowned(owner),
            attempts=self.attempts,
            events=self.events,
            purge_files=lambda owner: dependencies.purge_stored_files(
                self.shows.stored_files(owner_id=owner), self.store
            ),
            reset_minutes=30,
            reset_max_requests=3,
            web_url="https://podcasts.example",
        )
        self.shows = FakeShowRepository()
        self.episodes = FakeEpisodeRepository(self.shows)
        self.sources = FakeSourceRepository()
        self.uploads = FakeUploadRepository()
        self.store = FakeObjectStore()
        self.auth.on_delete.append(self.shows.drop_owner)
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
        overrides[dependencies.get_auth_service] = lambda: self.auth_service
        overrides[dependencies.get_auth_controller] = lambda: AuthController(
            self.auth_service, self.mailer
        )
        if signed_in:
            overrides[dependencies.get_current_user] = lambda: ADMIN
        self.client = TestClient(app)

    def _enqueue(self, episode_id: UUID, stage: Stage) -> None:
        if self.queue_down:
            raise ConnectionError("redis unreachable")
        self.enqueued.append(episode_id)
        self.stages.append((episode_id, stage))


@pytest.fixture
def harness() -> Harness:
    return Harness()
