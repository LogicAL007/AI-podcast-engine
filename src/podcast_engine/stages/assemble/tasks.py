from uuid import UUID

from podcast_engine.common.context import PipelineContext
from podcast_engine.common.queue import Stage
from podcast_engine.common.runner import stage_task
from podcast_engine.stages.assemble.service import assemble_episode


@stage_task(Stage.ASSEMBLE)
def run(episode_id: UUID, ctx: PipelineContext | None = None) -> Stage | None:
    """Assemble the episode's audio: the queue entry point of the assemble stage.

    Registered as a Celery task by ``stage_task``, which records the stage run, handles retries and
    queues the next stage.

    Args:
        episode_id: The episode to work on.
        ctx: Shared clients (database, storage, LLM); built from settings when omitted.

    Returns:
        The stage to queue next, or None when the pipeline stops here.
    """
    return assemble_episode(episode_id, ctx)
