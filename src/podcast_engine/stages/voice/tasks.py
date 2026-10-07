"""Queue entrypoint for the voice stage."""

from uuid import UUID

from podcast_engine.common.queue import Stage
from podcast_engine.common.runner import stage_task
from podcast_engine.stages.voice.service import synthesise_voices


@stage_task(Stage.VOICE)
def run(episode_id: UUID) -> Stage | None:
    return synthesise_voices(episode_id)
