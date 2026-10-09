"""Database engine shared by the API and the pipeline stages."""

from functools import lru_cache

from sqlalchemy import Engine, create_engine

from podcast_engine.common.config import get_settings


@lru_cache
def get_engine() -> Engine:
    """Return the process-wide engine (a connection pool, created on first use)."""
    return create_engine(get_settings().database_url, pool_pre_ping=True)
