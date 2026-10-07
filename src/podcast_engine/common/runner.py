"""Decorator that turns a stage function into a retryable, timed, chained queue task."""

from collections.abc import Callable
from functools import wraps
from uuid import UUID

from podcast_engine.common.config import get_settings
from podcast_engine.common.logging import configure_logging
from podcast_engine.common.queue import Stage, celery_app, dispatch, task_name
from podcast_engine.common.timing import stage_timer

# A stage takes an episode id and returns the stage to run next (None ends the job).
StageFunction = Callable[[UUID], Stage | None]


def stage_task(stage: Stage, *, max_retries: int = 3) -> Callable[[StageFunction], StageFunction]:
    """Register ``stage``'s function as the Celery task for its queue.

    Each stage retries on its own with backoff, so a failure never restarts the whole job.
    The undecorated function is returned unchanged, which keeps it directly callable in tests.
    """

    def decorator(function: StageFunction) -> StageFunction:
        @wraps(function)
        def task(episode_id: str) -> None:
            configure_logging(get_settings().log_level)
            episode = UUID(episode_id)
            with stage_timer(stage, episode):
                following = function(episode)
            if following is not None:
                dispatch(following, episode_id=episode_id)

        celery_app.task(
            name=task_name(stage),
            autoretry_for=(Exception,),
            retry_backoff=True,
            retry_jitter=True,
            max_retries=max_retries,
        )(task)
        return function

    return decorator
