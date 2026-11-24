from functools import lru_cache

from sqlalchemy import Engine, create_engine

from podcast_engine.common.config import get_settings


@lru_cache
def get_engine() -> Engine:
    """Return the database engine shared by the API and the pipeline stages.

    The engine is a connection pool, created on first use and cached for the life of the process.
    Connections are checked before use, so a restarted database is reconnected transparently.

    Returns:
        The process-wide SQLAlchemy engine for the configured database URL.
    """
    return create_engine(get_settings().database_url, pool_pre_ping=True)
