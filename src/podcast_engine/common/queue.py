from enum import StrEnum
from typing import Any

from celery import Celery

from podcast_engine.common.config import get_settings


class Stage(StrEnum):
    """The pipeline's eight stages, in order; each has its own queue."""

    INGEST = "ingest"
    INDEX = "index"
    RETRIEVE_PLAN = "retrieve_plan"
    SCRIPT = "script"
    FACTCHECK = "factcheck"
    VOICE = "voice"
    ASSEMBLE = "assemble"
    PUBLISH = "publish"


PIPELINE_ORDER: tuple[Stage, ...] = tuple(Stage)

REBUILD_FEED_TASK = "podcast_engine.publish.rebuild_feed"
SPEAK_TASK = "podcast_engine.voice.speak"


def task_name(stage: Stage) -> str:
    """Return the stable Celery task name for a stage.

    Args:
        stage: The stage.

    Returns:
        Its task name, such as ``podcast_engine.voice.run``.
    """
    return f"podcast_engine.{stage.value}.run"


def next_stage(stage: Stage) -> Stage | None:
    """Return the stage that follows another.

    Args:
        stage: The stage just run.

    Returns:
        The next stage, or None after publish.
    """
    index = PIPELINE_ORDER.index(stage)
    return PIPELINE_ORDER[index + 1] if index + 1 < len(PIPELINE_ORDER) else None


def create_celery_app() -> Celery:
    """Create the Celery app that sends and runs every stage's tasks.

    Workers never import each other. A stage enqueues the next one with ``dispatch``, which sends
    the task by name, so the voice image does not need the embedding libraries and vice versa.

    - No result backend: episode state lives in Postgres, so nothing ever reads Celery results.
    - Late acknowledgement: a crashed worker's job is redelivered, not lost.
    - A prefetch of one: jobs are long, so a worker does not hoard messages.

    Returns:
        The configured app, with each task routed to its stage's queue.
    """
    settings = get_settings()
    app = Celery("podcast_engine", broker=settings.redis_url)
    app.conf.update(
        task_acks_late=True,
        task_reject_on_worker_lost=True,
        worker_prefetch_multiplier=1,
        task_ignore_result=True,
        task_serializer="json",
        accept_content=["json"],
        task_default_queue=Stage.INGEST.value,
        task_routes={
            **{task_name(stage): {"queue": stage.value} for stage in Stage},
            REBUILD_FEED_TASK: {"queue": Stage.PUBLISH.value},
            SPEAK_TASK: {"queue": Stage.VOICE.value},
        },
    )
    return app


celery_app = create_celery_app()


def dispatch_feed_rebuild(show_id: str) -> str:
    """Queue a rewrite of one show's feed, after a published episode is deleted.

    Not a pipeline stage: it runs on the publish queue, in the publish worker, which has the
    feed-writing library.

    Args:
        show_id: The show whose feed to rewrite.

    Returns:
        The Celery task id.
    """
    result = celery_app.send_task(
        REBUILD_FEED_TASK,
        kwargs={"show_id": show_id},
        queue=Stage.PUBLISH.value,
        ignore_result=True,
    )
    return str(result.id)


def dispatch_speech(clip_id: str) -> str:
    """Queue a line typed in the voice studio to be voiced.

    Not a pipeline stage either: it runs on the voice queue, so the worker that has the voices
    (Chatterbox on the Mac, or Gemini) makes it.

    Args:
        clip_id: The speech clip to voice.

    Returns:
        The Celery task id.
    """
    result = celery_app.send_task(
        SPEAK_TASK, kwargs={"clip_id": clip_id}, queue=Stage.VOICE.value, ignore_result=True
    )
    return str(result.id)


def dispatch(stage: Stage, **kwargs: Any) -> str:
    """Queue a stage for an episode.

    Args:
        stage: The stage to run.
        **kwargs: The task's arguments, such as ``episode_id``.

    Returns:
        The Celery task id.
    """
    result = celery_app.send_task(
        task_name(stage), kwargs=kwargs, queue=stage.value, ignore_result=True
    )
    return str(result.id)
