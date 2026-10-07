"""Scheduler process: ``python -m podcast_engine.scheduler``."""

import time

from podcast_engine.common.config import get_settings
from podcast_engine.common.logging import configure_logging, get_logger

POLL_INTERVAL_SECONDS = 300


def tick() -> None:
    """Poll every show's sources, compare content hashes and dispatch only affected stages.

    FR8: not implemented yet; until it is, every tick says so instead of silently idling.
    """
    get_logger("scheduler").warning("tick_skipped", reason="change detection not implemented")


def main() -> None:
    configure_logging(get_settings().log_level)
    while True:
        tick()
        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
