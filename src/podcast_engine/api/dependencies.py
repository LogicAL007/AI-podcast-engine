"""FastAPI dependency providers: the one place that wires layers together.

Tests replace these with ``app.dependency_overrides`` to swap in fakes.
"""

from collections.abc import Iterator
from functools import lru_cache
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import text
from sqlalchemy.orm import Session

from podcast_engine.api.controllers.auth_controller import AuthController
from podcast_engine.api.controllers.episodes_controller import EpisodeController
from podcast_engine.api.controllers.feeds_controller import FeedController
from podcast_engine.api.controllers.home_controller import HomeController
from podcast_engine.api.controllers.ops_controller import OpsController
from podcast_engine.api.controllers.shows_controller import ShowController
from podcast_engine.api.controllers.sources_controller import SourceController
from podcast_engine.api.controllers.uploads_controller import UploadController
from podcast_engine.api.errors import (
    AuthNotConfiguredError,
    UnauthenticatedError,
    http_errors,
    to_http,
)
from podcast_engine.api.models.auth_model import CurrentUser
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
from podcast_engine.api.services.auth_service import AuthService
from podcast_engine.api.services.episodes_service import EnqueueStage, EpisodeService, RebuildFeed
from podcast_engine.api.services.feeds_service import FeedService
from podcast_engine.api.services.ops_service import Check, OpsService
from podcast_engine.api.services.shows_service import ShowService
from podcast_engine.api.services.sources_service import SourceService
from podcast_engine.api.services.uploads_service import UploadService
from podcast_engine.common.config import get_settings
from podcast_engine.common.db import get_engine
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
            PostgresShowRepository(session).stored_files(owner_id=user_id), get_object_store()
        ),
        reset_minutes=settings.password_reset_minutes,
        reset_max_requests=settings.password_reset_max_requests,
        web_url=settings.public_web_url,
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


def get_current_user(credentials: Credentials, service: AuthServiceDep) -> CurrentUser:
    """The authenticated caller; 401 with ``WWW-Authenticate: Bearer`` otherwise."""
    if credentials is None:
        return http_errors(lambda: _missing())
    return http_errors(lambda: service.authenticate(credentials.credentials))


CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]


def get_optional_user(credentials: Credentials, service: AuthServiceDep) -> CurrentUser | None:
    """The caller if a token was sent (and is valid), else None. For registration."""
    if credentials is None:
        return None
    return http_errors(lambda: service.authenticate(credentials.credentials))


def _missing() -> CurrentUser:
    raise UnauthenticatedError("send a bearer token: a login token or an API key")


def get_auth_controller(
    service: AuthServiceDep, mailer: Annotated[Mailer, Depends(get_mailer)]
) -> AuthController:
    return AuthController(service, mailer)
