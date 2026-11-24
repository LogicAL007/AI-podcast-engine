from uuid import UUID

from podcast_engine.common.config import get_settings
from podcast_engine.common.context import PipelineContext
from podcast_engine.common.logging import configure_logging
from podcast_engine.common.queue import SPEAK_TASK, Stage, celery_app
from podcast_engine.common.runner import stage_task
from podcast_engine.stages.voice.service import synthesise_voices
from podcast_engine.stages.voice.speak import speak_clip


@stage_task(Stage.VOICE)
def run(episode_id: UUID, ctx: PipelineContext | None = None) -> Stage | None:
    """Voice the episode's script: the queue entry point of the voice stage.

    Registered as a Celery task by ``stage_task``, which records the stage run, handles retries and
    queues the next stage.

    Args:
        episode_id: The episode to voice.
        ctx: Shared clients (database, storage, TTS); built from settings when omitted.

    Returns:
        The stage to queue next, or None when the pipeline stops here.
    """
    return synthesise_voices(episode_id, ctx)


@celery_app.task(name=SPEAK_TASK)  # type: ignore[untyped-decorator]
def speak(clip_id: str) -> None:
    """Voice one line typed in the voice studio.

    A Celery task on the voice queue, outside the episode pipeline: it renders a type-to-speech clip
    and stores it for the web app to play.

    Args:
        clip_id: The speech clip's id, as a string (Celery passes JSON).
    """
    configure_logging(get_settings().log_level)
    speak_clip(UUID(clip_id))
