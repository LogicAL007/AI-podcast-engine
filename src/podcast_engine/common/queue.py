"""Job queue wiring: one queue per stage, stages chained by id.

Workers never import each other. A stage enqueues the next one with ``dispatch``, which sends
the task by name, so the voice image does not need the embedding libraries and vice versa.
"""

from enum import StrEnum
from typing import Any

from celery import Celery

from podcast_engine.common.config import get_settings


class Stage(StrEnum):
    INGEST = "ingest"
    INDEX = "index"
    RETRIEVE_PLAN = "retrieve_plan"
    SCRIPT = "script"
    FACTCHECK = "factcheck"
    VOICE = "voice"
    ASSEMBLE = "assemble"
    PUBLISH = "publish"


PIPELINE_ORDER: tuple[Stage, ...] = tuple(Stage)


def task_name(stage: Stage) -> str:
    """Stable Celery task name for a stage."""
    return f"podcast_engine.{stage.value}.run"


def next_stage(stage: Stage) -> Stage | None:
    """Return the stage that follows ``stage``, or None after publish."""
    index = PIPELINE_ORDER.index(stage)
    return PIPELINE_ORDER[index + 1] if index + 1 < len(PIPELINE_ORDER) else None


def create_celery_app() -> Celery:
    settings = get_settings()
    app = Celery("podcast_engine", broker=settings.redis_url, backend=settings.redis_url)
    app.conf.update(
        task_acks_late=True,  # a crashed worker's job is redelivered, not lost
        task_reject_on_worker_lost=True,
        worker_prefetch_multiplier=1,  # long jobs: do not hoard messages
        task_track_started=True,
        task_serializer="json",
        accept_content=["json"],
        task_default_queue=Stage.INGEST.value,
        task_routes={task_name(stage): {"queue": stage.value} for stage in Stage},
    )
    return app


celery_app = create_celery_app()


def dispatch(stage: Stage, **kwargs: Any) -> str:
    """Enqueue ``stage`` and return the Celery task id."""
    result = celery_app.send_task(task_name(stage), kwargs=kwargs, queue=stage.value)
    return str(result.id)
