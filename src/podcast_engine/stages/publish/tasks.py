"""Queue entrypoint for the publish stage."""

from uuid import UUID

from podcast_engine.common.queue import Stage
from podcast_engine.common.runner import stage_task
from podcast_engine.stages.publish.service import publish_episode


@stage_task(Stage.PUBLISH)
def run(episode_id: UUID) -> Stage | None:
    return publish_episode(episode_id)
