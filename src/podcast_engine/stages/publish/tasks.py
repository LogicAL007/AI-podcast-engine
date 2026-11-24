from uuid import UUID

from podcast_engine.common.config import get_settings
from podcast_engine.common.context import PipelineContext
from podcast_engine.common.logging import configure_logging
from podcast_engine.common.queue import REBUILD_FEED_TASK, Stage, celery_app
from podcast_engine.common.runner import stage_task
from podcast_engine.stages.publish.service import publish_episode, rebuild_feed


@stage_task(Stage.PUBLISH)
def run(episode_id: UUID, ctx: PipelineContext | None = None) -> Stage | None:
    """Publish the episode: the queue entry point of the publish stage.

    Registered as a Celery task by ``stage_task``, which records the stage run, handles retries and
    ends the pipeline.

    Args:
        episode_id: The episode to publish.
        ctx: Shared clients (database, storage); built from settings when omitted.

    Returns:
        The stage to queue next, or None when the pipeline stops here.
    """
    return publish_episode(episode_id, ctx)


@celery_app.task(  # type: ignore[untyped-decorator]
    name=REBUILD_FEED_TASK, autoretry_for=(Exception,), retry_backoff=True, max_retries=3
)
def rebuild_show_feed(show_id: str) -> None:
    """Rewrite a show's RSS feed, for example after a published episode is deleted.

    A Celery task outside the episode pipeline, retried up to three times with backoff.

    Args:
        show_id: The show whose feed to rebuild, as a string (Celery passes JSON).
    """
    configure_logging(get_settings().log_level)
    rebuild_feed(UUID(show_id))
