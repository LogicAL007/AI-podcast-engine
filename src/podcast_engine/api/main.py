"""FastAPI application entrypoint: ``uvicorn podcast_engine.api.main:app``."""

from fastapi import Depends, FastAPI

from podcast_engine import __version__
from podcast_engine.api.dependencies import get_current_user
from podcast_engine.api.observability import add_metrics
from podcast_engine.api.openapi import DESCRIPTION, TAGS, errors, operation_id
from podcast_engine.api.routers.auth_router import router as auth_router
from podcast_engine.api.routers.episodes_router import router as episodes_router
from podcast_engine.api.routers.feeds_router import router as feeds_router
from podcast_engine.api.routers.home_router import router as home_router
from podcast_engine.api.routers.media_router import router as media_router
from podcast_engine.api.routers.ops_router import router as ops_router
from podcast_engine.api.routers.shows_router import router as shows_router
from podcast_engine.api.routers.sources_router import router as sources_router
from podcast_engine.api.routers.uploads_router import router as uploads_router
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
    # Open: discovery, login, health, and what podcast apps fetch (feeds, audio, notes, PDFs).
    for public in (home_router, auth_router, media_router, feeds_router, ops_router):
        app.include_router(public)
    # Everything else needs a login token or an API key.
    for protected in (shows_router, episodes_router, sources_router, uploads_router):
        app.include_router(protected, dependencies=[Depends(get_current_user)], responses=PROTECTED)

    return app


app = create_app()
