"""Queue entrypoint for the index stage."""

from uuid import UUID

from podcast_engine.common.context import PipelineContext
from podcast_engine.common.queue import Stage
from podcast_engine.common.runner import stage_task
from podcast_engine.stages.index.service import index_items


@stage_task(Stage.INDEX)
def run(episode_id: UUID, ctx: PipelineContext | None = None) -> Stage | None:
    return index_items(episode_id, ctx)
