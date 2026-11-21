from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from podcast_engine.api import dependencies
from podcast_engine.api.controllers.assistant_controller import AssistantController
from podcast_engine.api.controllers.auth_controller import AuthController
from podcast_engine.api.controllers.episodes_controller import EpisodeController
from podcast_engine.api.controllers.feeds_controller import FeedController
from podcast_engine.api.controllers.music_controller import MusicController
from podcast_engine.api.controllers.ops_controller import OpsController
from podcast_engine.api.controllers.shows_controller import ShowController
from podcast_engine.api.controllers.sources_controller import SourceController
from podcast_engine.api.controllers.speech_controller import SpeechController
from podcast_engine.api.controllers.uploads_controller import UploadController
from podcast_engine.api.controllers.voices_controller import VoiceController
from podcast_engine.api.main import create_app
from podcast_engine.api.models.auth_model import CurrentUser
from podcast_engine.api.repositories.assistant_usage_repository import MemoryAssistantUsage
from podcast_engine.api.repositories.login_attempts_repository import (
    LimitsConfig,
    MemoryLoginAttempts,
)
from podcast_engine.api.services.assistant_service import AssistantService
from podcast_engine.api.services.auth_service import AuthService
from podcast_engine.api.services.episodes_service import EpisodeService, ProgressPacing
from podcast_engine.api.services.feeds_service import FeedService
from podcast_engine.api.services.music_service import MusicService
from podcast_engine.api.services.ops_service import Check, OpsService
from podcast_engine.api.services.shows_service import ShowService
from podcast_engine.api.services.sources_service import SourceService
from podcast_engine.api.services.speech_service import SpeechService
from podcast_engine.api.services.uploads_service import UploadService
from podcast_engine.api.services.voices_service import VoiceService
from podcast_engine.common.config import Settings
from podcast_engine.common.llm import LlmClient
from podcast_engine.common.mailer import Email
from podcast_engine.common.queue import Stage
from podcast_engine.common.quota import DailyBudget
from tests.unit.api.fakes import (
    FakeAuthRepository,
    FakeEpisodeRepository,
    FakeMusicRepository,
    FakeObjectStore,
    FakeSecurityEventRepository,
    FakeShowRepository,
    FakeSourceRepository,
    FakeSpeechRepository,
    FakeUploadRepository,
    FakeVoiceRepository,
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

    def __init__(self, *, signed_in: bool = True, signup_open: bool = False) -> None:
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
            signup_open=signup_open,
        )
        self.shows = FakeShowRepository()
        self.episodes = FakeEpisodeRepository(self.shows)
        self.sources = FakeSourceRepository()
        self.uploads = FakeUploadRepository()
        self.store = FakeObjectStore()
        self.voices = FakeVoiceRepository(self.shows)
        self.speech = FakeSpeechRepository()
        self.music = FakeMusicRepository(self.shows)
        self.speech_settings = Settings(tts_backend="chatterbox", speech_clips_per_hour=30)
        self.speech_budget: DailyBudget | None = None
        self.speech_usage = MemoryAssistantUsage(clock=lambda: self.seconds)
        self.spoken: list[str] = []  # clip ids sent to the voice queue
        self.auth.on_delete.append(self.shows.drop_owner)
        self.enqueued: list[UUID] = []
        self.stages: list[tuple[UUID, Stage]] = []
        self.feeds_rebuilt: list[UUID] = []
        self.queue_down = False
        self.checks: dict[str, Check] = {"database": lambda: None, "queue": lambda: None}
        app = create_app()
        overrides = app.dependency_overrides
        overrides[dependencies.get_show_controller] = lambda: ShowController(
            ShowService(self.shows, self.voices, self.music)
        )
        overrides[dependencies.get_speech_controller] = lambda: SpeechController(
            SpeechService(
                self.speech,
                self.voices,
                self.store,
                self.speech_usage,
                self._enqueue_speech,
                self.speech_settings,
                self.speech_budget,
            )
        )
        overrides[dependencies.get_music_controller] = lambda: MusicController(
            MusicService(self.music, self.store)
        )
        overrides[dependencies.get_voice_controller] = lambda: VoiceController(
            VoiceService(self.voices, self.store)
        )
        overrides[dependencies.get_episode_controller] = lambda: EpisodeController(
            EpisodeService(
                self.episodes, self.shows, self._enqueue, self.store, self.feeds_rebuilt.append
            )
        )
        # The bot's model: None (the built-in help) unless a test gives it one.
        self.assistant_llm: LlmClient | None = None
        self.assistant_usage = MemoryAssistantUsage(clock=lambda: self.seconds)
        self.assistant_per_hour = 20
        overrides[dependencies.get_assistant_controller] = lambda: AssistantController(
            AssistantService(
                EpisodeService(
                    self.episodes, self.shows, self._enqueue, self.store, self.feeds_rebuilt.append
                ),
                ShowService(self.shows, self.voices),
                self.assistant_usage,
                lambda: self.assistant_llm,
                self.assistant_per_hour,
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
        overrides[dependencies.get_session] = _no_database
        overrides[dependencies.get_episode_loader] = lambda: self.episodes.get
        # The progress stream polls through this; tests replace sleep to move the episode on.
        self.pacing = ProgressPacing(poll_s=1.0, heartbeat_s=15.0, max_s=3600.0,
                                     sleep=self._advance, clock=lambda: self.seconds)  # fmt: skip
        self.on_poll: list[Callable[[], None]] = []
        overrides[dependencies.get_progress_pacing] = lambda: self.pacing
        overrides[dependencies.get_auth_service] = lambda: self.auth_service
        overrides[dependencies.get_auth_controller] = lambda: AuthController(
            self.auth_service, self.mailer
        )
        if signed_in:
            overrides[dependencies.get_current_user] = lambda: ADMIN
        self.client = TestClient(app)

    async def _advance(self, seconds: float) -> None:
        """The stream's sleep: time moves on, and the next scripted change happens."""
        self.seconds += seconds
        if self.on_poll:
            self.on_poll.pop(0)()

    def _enqueue_speech(self, clip_id: str) -> str:
        if self.queue_down:
            raise ConnectionError("redis unreachable")
        self.spoken.append(clip_id)
        return clip_id

    def _enqueue(self, episode_id: UUID, stage: Stage) -> None:
        if self.queue_down:
            raise ConnectionError("redis unreachable")
        self.enqueued.append(episode_id)
        self.stages.append((episode_id, stage))


@pytest.fixture
def harness() -> Harness:
    return Harness()


class _UnusedSession:
    """Stands in for the request's database session; routes under test never query it."""

    def close(self) -> None:
        pass


def _no_database() -> Iterator[_UnusedSession]:
    yield _UnusedSession()
