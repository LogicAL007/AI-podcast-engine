import logging
import sys

import structlog


def configure_logging(level: str = "INFO") -> None:
    """Send stdlib and structlog output to stdout as one JSON object per line.

    Structured logs let per-episode logs be queried by field (episode, stage, event).

    Args:
        level: The lowest level to log, such as ``INFO`` or ``debug`` (any case).
    """
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
    """Return a structured logger bound to a module or stage name.

    Args:
        name: The module or stage the log lines come from.

    Returns:
        A structlog logger that filters by the configured level.
    """
    logger: structlog.typing.FilteringBoundLogger = structlog.get_logger(name)
    return logger
