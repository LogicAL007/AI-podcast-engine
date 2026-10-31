"""FastAPI application entrypoint: ``uvicorn podcast_engine.api.main:app``."""

from fastapi import Depends, FastAPI

from podcast_engine import __version__
from podcast_engine.api.dependencies import get_current_user
from podcast_engine.api.observability import add_metrics
from podcast_engine.api.openapi import DESCRIPTION, TAGS, errors, operation_id
from podcast_engine.api.paths import V1
from podcast_engine.api.routers.assistant_router import router as assistant_router
from podcast_engine.api.routers.auth_router import router as auth_router
from podcast_engine.api.routers.episodes_router import router as episodes_router
from podcast_engine.api.routers.feeds_router import router as feeds_router
from podcast_engine.api.routers.home_router import router as home_router
from podcast_engine.api.routers.media_router import router as media_router
from podcast_engine.api.routers.ops_router import router as ops_router
from podcast_engine.api.routers.shows_router import router as shows_router
from podcast_engine.api.routers.sources_router import router as sources_router
from podcast_engine.api.routers.uploads_router import router as uploads_router
from podcast_engine.api.routers.usage_router import router as usage_router
from podcast_engine.api.routers.voices_router import router as voices_router
from podcast_engine.common.config import get_settings
from podcast_engine.common.logging import configure_logging

PROTECTED = errors(
    e401="Missing, invalid, expired or revoked token", e503="Login is not configured"
)


def create_app() -> FastAPI:
    configure_logging(get_settings().log_level)
    app = FastAPI(
        title="AI Podcast Engine",
        version=__version__,
        summary="Create shows, generate grounded episodes and fetch their audio, notes and feeds.",
        description=DESCRIPTION,
        openapi_tags=TAGS,
        license_info={"name": "MIT", "identifier": "MIT"},
        generate_unique_id_function=operation_id,
    )
    add_metrics(app)
    # Discovery and health stay at the root; the API itself is versioned under /v1.
    for root in (home_router, ops_router):
        app.include_router(root)
    # Open: login, and what podcast apps fetch (feeds, audio, notes, PDFs).
    for public in (auth_router, media_router, feeds_router):
        app.include_router(public, prefix=V1)
    # Everything else needs a login (cookie or token) or an API key.
    protected_routers = (
        shows_router,
        episodes_router,
        sources_router,
        uploads_router,
        voices_router,
        assistant_router,
        usage_router,
    )
    for protected in protected_routers:
        app.include_router(
            protected, prefix=V1, dependencies=[Depends(get_current_user)], responses=PROTECTED
        )
    # Feed and audio URLs published before /v1 existed are already in podcast apps: keep them.
    for legacy in (media_router, feeds_router):
        app.include_router(legacy, include_in_schema=False)

    return app


app = create_app()
