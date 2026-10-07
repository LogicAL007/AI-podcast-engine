"""FastAPI application entrypoint."""

from fastapi import FastAPI

from podcast_engine import __version__
from podcast_engine.api.routers import episodes, feeds, shows
from podcast_engine.common.config import get_settings
from podcast_engine.common.logging import configure_logging


def create_app() -> FastAPI:
    configure_logging(get_settings().log_level)
    app = FastAPI(title="AI Podcast Engine", version=__version__)
    app.include_router(shows.router)
    app.include_router(episodes.router)
    app.include_router(feeds.router)

    @app.get("/health", tags=["ops"])
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    return app


app = create_app()
