"""Queue entrypoint for the script stage."""

from uuid import UUID

from podcast_engine.common.queue import Stage
from podcast_engine.common.runner import stage_task
from podcast_engine.stages.script.service import write_script


@stage_task(Stage.SCRIPT)
def run(episode_id: UUID) -> Stage | None:
    return write_script(episode_id)
