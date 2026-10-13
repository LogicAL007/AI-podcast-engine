"""Queue entrypoints for the publish stage, and for rebuilding a show's feed on its own."""

from uuid import UUID

from podcast_engine.common.config import get_settings
from podcast_engine.common.context import PipelineContext
from podcast_engine.common.logging import configure_logging
from podcast_engine.common.queue import REBUILD_FEED_TASK, Stage, celery_app
from podcast_engine.common.runner import stage_task
from podcast_engine.stages.publish.service import publish_episode, rebuild_feed


@stage_task(Stage.PUBLISH)
def run(episode_id: UUID, ctx: PipelineContext | None = None) -> Stage | None:
    return publish_episode(episode_id, ctx)


@celery_app.task(  # type: ignore[untyped-decorator]
    name=REBUILD_FEED_TASK, autoretry_for=(Exception,), retry_backoff=True, max_retries=3
)
def rebuild_show_feed(show_id: str) -> None:
    """After a published episode is deleted: rewrite the feed without it."""
    configure_logging(get_settings().log_level)
    rebuild_feed(UUID(show_id))
