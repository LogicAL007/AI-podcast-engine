"""Queue entrypoints for the voice stage, and for type-to-speech clips."""

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
    return synthesise_voices(episode_id, ctx)


@celery_app.task(name=SPEAK_TASK)  # type: ignore[untyped-decorator]
def speak(clip_id: str) -> None:
    """Voice one line typed in the voice studio (not a pipeline stage)."""
    configure_logging(get_settings().log_level)
    speak_clip(UUID(clip_id))
