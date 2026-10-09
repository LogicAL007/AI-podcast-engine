"""FastAPI application entrypoint: ``uvicorn podcast_engine.api.main:app``."""

from fastapi import FastAPI

from podcast_engine import __version__
from podcast_engine.api.observability import add_metrics
from podcast_engine.api.routers.episodes_router import router as episodes_router
from podcast_engine.api.routers.feeds_router import router as feeds_router
from podcast_engine.api.routers.shows_router import router as shows_router
from podcast_engine.common.config import get_settings
from podcast_engine.common.logging import configure_logging


def create_app() -> FastAPI:
    configure_logging(get_settings().log_level)
    app = FastAPI(
        title="AI Podcast Engine",
        version=__version__,
        description="Create shows, start episode generation and fetch RSS feeds.",
    )
    add_metrics(app)
    app.include_router(shows_router)
    app.include_router(episodes_router)
    app.include_router(feeds_router)

    @app.get("/health", tags=["ops"])
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    return app


app = create_app()
