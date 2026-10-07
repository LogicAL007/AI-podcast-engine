"""Queue entrypoint for the factcheck stage."""

from uuid import UUID

from podcast_engine.common.queue import Stage
from podcast_engine.common.runner import stage_task
from podcast_engine.stages.factcheck.service import check_script


@stage_task(Stage.FACTCHECK)
def run(episode_id: UUID) -> Stage | None:
    return check_script(episode_id)
