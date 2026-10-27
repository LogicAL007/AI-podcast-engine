"""FastAPI dependency providers: the one place that wires layers together.

Tests replace these with ``app.dependency_overrides`` to swap in fakes.
"""

from collections.abc import Callable, Iterator
from functools import lru_cache
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request, Security
from fastapi.security import APIKeyCookie, HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import text
from sqlalchemy.orm import Session

from podcast_engine.api.controllers.assistant_controller import AssistantController
from podcast_engine.api.controllers.auth_controller import AuthController
from podcast_engine.api.controllers.episodes_controller import EpisodeController
from podcast_engine.api.controllers.feeds_controller import FeedController
from podcast_engine.api.controllers.home_controller import HomeController
from podcast_engine.api.controllers.ops_controller import OpsController
from podcast_engine.api.controllers.shows_controller import ShowController
from podcast_engine.api.controllers.sources_controller import SourceController
from podcast_engine.api.controllers.uploads_controller import UploadController
from podcast_engine.api.controllers.voices_controller import VoiceController
from podcast_engine.api.cookies import CSRF_COOKIE, CSRF_HEADER, SAFE_METHODS, SESSION_COOKIE
from podcast_engine.api.errors import (
    AuthNotConfiguredError,
    UnauthenticatedError,
    http_errors,
    to_http,
)
from podcast_engine.api.models.auth_model import CurrentUser
from podcast_engine.api.models.episodes_model import EpisodeRead
from podcast_engine.api.repositories.assistant_usage_repository import (
    AssistantUsage,
    RedisAssistantUsage,
)
from podcast_engine.api.repositories.auth_repository import PostgresAuthRepository
from podcast_engine.api.repositories.episodes_repository import PostgresEpisodeRepository
from podcast_engine.api.repositories.login_attempts_repository import (
    LimitsConfig,
    LoginAttempts,
    RedisLoginAttempts,
)
from podcast_engine.api.repositories.security_events_repository import (
    PostgresSecurityEventRepository,
)
from podcast_engine.api.repositories.shows_repository import PostgresShowRepository
from podcast_engine.api.repositories.sources_repository import PostgresSourceRepository
from podcast_engine.api.repositories.uploads_repository import PostgresUploadRepository
from podcast_engine.api.repositories.voices_repository import PostgresVoiceRepository
from podcast_engine.api.services.assistant_service import AssistantService
from podcast_engine.api.services.auth_service import AuthService
from podcast_engine.api.services.episodes_service import (
    EnqueueStage,
    EpisodeLoader,
    EpisodeService,
    ProgressPacing,
    RebuildFeed,
)
from podcast_engine.api.services.feeds_service import FeedService
from podcast_engine.api.services.ops_service import Check, OpsService
from podcast_engine.api.services.shows_service import ShowService
from podcast_engine.api.services.sources_service import SourceService
from podcast_engine.api.services.uploads_service import UploadService
from podcast_engine.api.services.voices_service import VoiceService
from podcast_engine.common.config import get_settings
from podcast_engine.common.db import get_engine
from podcast_engine.common.llm import LlmClient, make_llm
from podcast_engine.common.logging import get_logger
from podcast_engine.common.mailer import Mailer, make_mailer
from podcast_engine.common.queue import Stage, celery_app, dispatch, dispatch_feed_rebuild
from podcast_engine.common.storage import ObjectStore, S3ObjectStore

log = get_logger("api.dependencies")


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
    return ShowController(
        ShowService(PostgresShowRepository(session), PostgresVoiceRepository(session))
    )


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


@lru_cache
def get_assistant_usage() -> AssistantUsage:
    """Question counts shared by every API process (Redis), so the hourly limit holds."""
    import redis

    return RedisAssistantUsage(redis.Redis.from_url(get_settings().redis_url, socket_timeout=2))


@lru_cache
def _assistant_llm() -> LlmClient | None:
    """The model for the bot's answers, made on the first question; None when the LLM is off or
    cannot be set up (the built-in help answers then). A chat should not wait minutes on a busy
    model, so it retries briefly, then the help answers."""
    try:
        llm = make_llm(get_settings())
    except Exception:
        log.exception("assistant_llm_unavailable")
        return None
    if llm is not None:
        llm.RETRIES = 2  # type: ignore[attr-defined]
        llm.RETRIES_BEFORE_FALLBACK = 1  # type: ignore[attr-defined]
    return llm


def get_assistant_llm() -> Callable[[], LlmClient | None]:
    return _assistant_llm


def get_assistant_controller(
    session: SessionDep,
    enqueue: Annotated[EnqueueStage, Depends(get_enqueue_stage)],
    store: Annotated[ObjectStore, Depends(get_object_store)],
    rebuild_feed: Annotated[RebuildFeed, Depends(get_rebuild_feed)],
    usage: Annotated[AssistantUsage, Depends(get_assistant_usage)],
    llm: Annotated[Callable[[], LlmClient | None], Depends(get_assistant_llm)],
) -> AssistantController:
    episodes = EpisodeService(
        PostgresEpisodeRepository(session),
        PostgresShowRepository(session),
        enqueue,
        store,
        rebuild_feed,
    )
    shows = ShowService(PostgresShowRepository(session), PostgresVoiceRepository(session))
    per_hour = get_settings().assistant_questions_per_hour
    return AssistantController(AssistantService(episodes, shows, usage, llm, per_hour))


def get_episode_loader() -> EpisodeLoader:
    """Reads an episode with its own short-lived session, for the progress stream."""

    def load(episode_id: UUID, owner: UUID) -> EpisodeRead | None:
        with Session(get_engine()) as session:
            return PostgresEpisodeRepository(session).get(episode_id, owner)

    return load


def get_progress_pacing() -> ProgressPacing:
    return ProgressPacing()


def get_feed_controller(store: Annotated[ObjectStore, Depends(get_object_store)]) -> FeedController:
    return FeedController(FeedService(store))


def get_source_controller(session: SessionDep) -> SourceController:
    return SourceController(
        SourceService(PostgresSourceRepository(session), PostgresShowRepository(session))
    )


def get_voice_controller(
    session: SessionDep, store: Annotated[ObjectStore, Depends(get_object_store)]
) -> VoiceController:
    return VoiceController(VoiceService(PostgresVoiceRepository(session), store))


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
    return HomeController(token_days=get_settings().auth_token_days)


# ---- login --------------------------------------------------------------------------------------
bearer = HTTPBearer(
    auto_error=False,
    scheme_name="BearerToken",
    description=(
        "A login token from `POST /auth/login`, or an API key from `POST /auth/api-keys`. "
        "Both last six months."
    ),
)
Credentials = Annotated[HTTPAuthorizationCredentials | None, Security(bearer)]
session_cookie = APIKeyCookie(
    name=SESSION_COOKIE,
    auto_error=False,
    scheme_name="SessionCookie",
    description=(
        "The web app's sign-in, set by `POST /v1/auth/browser-session` (HttpOnly). Requests that "
        f"change something must also send `{CSRF_HEADER}` with the value of the `{CSRF_COOKIE}` "
        "cookie."
    ),
)
SessionCookie = Annotated[str | None, Security(session_cookie)]


def get_auth_service(session: SessionDep) -> AuthService:
    settings = get_settings()
    key = settings.auth_token_key.get_secret_value()
    if not key:
        raise to_http(
            AuthNotConfiguredError(
                "login is not configured: the token key is missing (run vault-init, or set "
                "AUTH_TOKEN_KEY_FILE)"
            )
        )
    return AuthService(
        PostgresAuthRepository(session),
        token_key=key.encode(),
        token_days=settings.auth_token_days,
        claim_unowned=PostgresShowRepository(session).claim_unowned,
        attempts=get_login_attempts(),
        events=PostgresSecurityEventRepository(session),
        purge_files=lambda user_id: purge_stored_files(
            PostgresShowRepository(session).stored_files(owner_id=user_id)
            + PostgresVoiceRepository(session).object_keys(user_id),
            get_object_store(),
        ),
        reset_minutes=settings.password_reset_minutes,
        reset_max_requests=settings.password_reset_max_requests,
        web_url=settings.public_web_url,
        signup_open=settings.signup_open,
    )


def purge_stored_files(keys: list[str], store: ObjectStore) -> int:
    """Delete stored files, carrying on past failures (each is logged); returns how many went."""
    removed = 0
    for key in keys:
        try:
            store.delete(key)
            removed += 1
        except Exception:
            log.exception("stored_file_not_deleted", key=key)
    return removed


@lru_cache
def get_login_attempts() -> LoginAttempts:
    """Counters shared by every API process (Redis), so limits hold across uvicorn workers."""
    import redis

    s = get_settings()
    limits = LimitsConfig(
        max_failures=s.login_max_failures,
        address_max_failures=s.login_ip_max_failures,
        window_s=s.login_window_minutes * 60,
        lockout_s=s.login_lockout_minutes * 60,
        reset_max=s.password_reset_max_requests,
    )
    return RedisLoginAttempts(redis.Redis.from_url(s.redis_url, socket_timeout=2), limits)


@lru_cache
def get_mailer() -> Mailer:
    return make_mailer(get_settings())


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]


def _from_cookie(request: Request, cookie: str, service: AuthService) -> CurrentUser:
    """The browser's session. A request that changes something must carry the CSRF token."""
    current = http_errors(lambda: service.authenticate_session_cookie(cookie))
    if request.method not in SAFE_METHODS:
        http_errors(lambda: service.check_csrf(current, request.headers.get(CSRF_HEADER)))
    return current


def get_current_user(
    request: Request, credentials: Credentials, cookie: SessionCookie, service: AuthServiceDep
) -> CurrentUser:
    """The authenticated caller, by bearer token or the browser's session cookie; 401 otherwise."""
    if credentials is not None:
        return http_errors(lambda: service.authenticate(credentials.credentials))
    if cookie:
        return _from_cookie(request, cookie, service)
    return http_errors(lambda: _missing())


CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]


def get_optional_user(
    request: Request, credentials: Credentials, cookie: SessionCookie, service: AuthServiceDep
) -> CurrentUser | None:
    """The caller if a token or session cookie was sent (and is valid), else None."""
    if credentials is not None:
        return http_errors(lambda: service.authenticate(credentials.credentials))
    if cookie:
        return _from_cookie(request, cookie, service)
    return None


def _missing() -> CurrentUser:
    raise UnauthenticatedError("send a bearer token: a login token or an API key")


def get_auth_controller(
    service: AuthServiceDep, mailer: Annotated[Mailer, Depends(get_mailer)]
) -> AuthController:
    settings = get_settings()
    return AuthController(
        service,
        mailer,
        cookie_secure=settings.public_web_url.startswith("https://"),
        token_days=settings.auth_token_days,
    )
