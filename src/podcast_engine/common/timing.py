"""Per-stage timing, feeding the end-to-end generation-time benchmark."""

import time
from collections.abc import Iterator
from contextlib import contextmanager
from uuid import UUID

from podcast_engine.common.logging import get_logger
from podcast_engine.common.metrics import STAGE_DURATION, STAGE_RUNS
from podcast_engine.common.queue import Stage


@contextmanager
def stage_timer(stage: Stage, episode_id: UUID) -> Iterator[None]:
    """Log start, duration and failure of one stage run for an episode."""
    log = get_logger(stage.value).bind(episode_id=str(episode_id), stage=stage.value)
    started = time.perf_counter()
    log.info("stage_started")
    try:
        yield
    except Exception:
        seconds = time.perf_counter() - started
        STAGE_RUNS.labels(stage.value, "failure").inc()
        STAGE_DURATION.labels(stage.value).observe(seconds)
        log.exception("stage_failed", seconds=round(seconds, 3))
        raise
    seconds = time.perf_counter() - started
    STAGE_RUNS.labels(stage.value, "success").inc()
    STAGE_DURATION.labels(stage.value).observe(seconds)
    log.info("stage_finished", seconds=round(seconds, 3))
