"""FastAPI application entrypoint: ``uvicorn podcast_engine.api.main:app``."""

from fastapi import FastAPI

from podcast_engine import __version__
from podcast_engine.api.observability import add_metrics
from podcast_engine.api.openapi import DESCRIPTION, TAGS, operation_id
from podcast_engine.api.routers.episodes_router import router as episodes_router
from podcast_engine.api.routers.feeds_router import router as feeds_router
from podcast_engine.api.routers.home_router import router as home_router
from podcast_engine.api.routers.ops_router import router as ops_router
from podcast_engine.api.routers.shows_router import router as shows_router
from podcast_engine.api.routers.sources_router import router as sources_router
from podcast_engine.api.routers.uploads_router import router as uploads_router
from podcast_engine.common.config import get_settings
from podcast_engine.common.logging import configure_logging


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
    app.include_router(home_router)
    app.include_router(shows_router)
    app.include_router(episodes_router)
    app.include_router(sources_router)
    app.include_router(uploads_router)
    app.include_router(feeds_router)
    app.include_router(ops_router)

    return app


app = create_app()
