"""Queue entrypoint for the ingest stage."""

from uuid import UUID

from podcast_engine.common.queue import Stage
from podcast_engine.common.runner import stage_task
from podcast_engine.stages.ingest.service import ingest_sources


@stage_task(Stage.INGEST)
def run(episode_id: UUID) -> Stage | None:
    return ingest_sources(episode_id)
