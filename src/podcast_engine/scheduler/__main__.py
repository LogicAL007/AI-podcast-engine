import time

from podcast_engine.common.config import get_settings
from podcast_engine.common.context import get_context
from podcast_engine.common.logging import configure_logging, get_logger
from podcast_engine.common.queue import Stage, dispatch

POLL_INTERVAL_SECONDS = 300

log = get_logger("scheduler")


def tick() -> list[str]:
    """Start a refresh for every published show that is due (FR8).

    A refresh is an ordinary episode: ingest compares content hashes and either stops (nothing
    changed, status ``unchanged``) or regenerates only the segments whose sources changed. Nothing
    starts when ``REFRESH_INTERVAL_HOURS`` is 0.

    Returns:
        The ids of the episodes started.
    """
    ctx = get_context()
    hours = ctx.settings.refresh_interval_hours
    if hours <= 0:
        log.info("tick_skipped", reason="REFRESH_INTERVAL_HOURS is 0 (automatic refresh is off)")
        return []
    started = []
    for show_id in ctx.repo.shows_due_for_refresh(hours):
        episode_id = ctx.repo.create_episode(show_id)
        dispatch(Stage.INGEST, episode_id=str(episode_id))
        log.info("refresh_started", show_id=str(show_id), episode_id=str(episode_id))
        started.append(str(episode_id))
    return started


def main() -> None:
    """Run the scheduler: ``python -m podcast_engine.scheduler``.

    Checks for due shows every five minutes, forever. A failed check (a database or queue outage) is
    logged and retried on the next tick, so it never stops the scheduler.
    """
    configure_logging(get_settings().log_level)
    while True:
        try:
            tick()
        except Exception:
            log.exception("tick_failed")
        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
