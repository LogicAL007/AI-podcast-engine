"""Structured JSON logging, so per-episode logs can be queried by field."""

import logging
import sys

import structlog


def configure_logging(level: str = "INFO") -> None:
    """Route stdlib and structlog output to stdout as one JSON object per line."""
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level.upper())
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(level.upper())),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.typing.FilteringBoundLogger:
    """Return a logger bound to a module or stage name."""
    logger: structlog.typing.FilteringBoundLogger = structlog.get_logger(name)
    return logger
