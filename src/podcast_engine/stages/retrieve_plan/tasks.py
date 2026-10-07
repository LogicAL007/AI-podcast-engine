"""Queue entrypoint for the retrieve_plan stage."""

from uuid import UUID

from podcast_engine.common.queue import Stage
from podcast_engine.common.runner import stage_task
from podcast_engine.stages.retrieve_plan.service import retrieve_and_plan


@stage_task(Stage.RETRIEVE_PLAN)
def run(episode_id: UUID) -> Stage | None:
    return retrieve_and_plan(episode_id)
