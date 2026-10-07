"""Queue entrypoint for the assemble stage."""

from uuid import UUID

from podcast_engine.common.queue import Stage
from podcast_engine.common.runner import stage_task
from podcast_engine.stages.assemble.service import assemble_episode


@stage_task(Stage.ASSEMBLE)
def run(episode_id: UUID) -> Stage | None:
    return assemble_episode(episode_id)
