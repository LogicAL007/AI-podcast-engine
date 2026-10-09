"""Decorator that turns a stage function into a retryable, timed, chained queue task."""

import time
from collections.abc import Callable
from functools import wraps
from typing import Any, Protocol
from uuid import UUID

from podcast_engine.common.config import get_settings
from podcast_engine.common.context import PROMPT_VERSIONS, PipelineContext, get_context
from podcast_engine.common.logging import configure_logging
from podcast_engine.common.models import EpisodeStatus
from podcast_engine.common.queue import Stage, celery_app, dispatch, task_name
from podcast_engine.common.timing import stage_timer


class StageFunction(Protocol):
    """Takes an episode id (and optionally a context); returns the next stage, or None."""

    def __call__(self, episode_id: UUID, ctx: PipelineContext | None = None) -> Stage | None: ...


# Bad input or configuration (no sources, an unknown ranking profile, an unvoiced script):
# retrying cannot help, so the episode fails at once with the reason.
PERMANENT_ERRORS: tuple[type[Exception], ...] = (ValueError, LookupError)

_PROMPT_OF = {Stage.RETRIEVE_PLAN: "outline", Stage.SCRIPT: "script", Stage.FACTCHECK: "factcheck"}


def _model_for(stage: Stage, ctx: PipelineContext) -> str | None:
    settings = ctx.settings
    if stage in _PROMPT_OF:
        return (
            f"{settings.llm_provider}:{settings.llm_model}" if settings.llm_enabled else "offline"
        )
    if stage is Stage.INDEX:
        return settings.embedding_model
    if stage is Stage.VOICE:
        return settings.tts_backend
    return None


def _llm_usage(ctx: PipelineContext) -> dict[str, int]:
    llm = ctx.__dict__.get("llm")  # only if this process created a client; never create one here
    return dict(llm.usage) if llm is not None else {}


def run_stage(
    stage: Stage,
    function: StageFunction,
    episode_id: UUID,
    ctx: PipelineContext,
    *,
    last_attempt: bool = True,
) -> Stage | None:
    """Run one stage for an episode, recording progress, timing and failure on the episode row."""
    ctx.repo.update_episode(
        episode_id, status=EpisodeStatus.PROCESSING, stage=stage.value, error=None
    )
    usage_before = _llm_usage(ctx)
    started = time.perf_counter()
    try:
        with stage_timer(stage, episode_id):
            following = function(episode_id, ctx)
    except PERMANENT_ERRORS as error:
        ctx.repo.update_episode(
            episode_id, status=EpisodeStatus.FAILED, error=f"{stage.value}: {error}"[:2000]
        )
        return None
    except Exception as error:
        if last_attempt:
            ctx.repo.update_episode(
                episode_id, status=EpisodeStatus.FAILED, error=f"{stage.value}: {error}"[:2000]
            )
        raise
    seconds = time.perf_counter() - started
    usage = {k: v - usage_before.get(k, 0) for k, v in _llm_usage(ctx).items()}
    if any(usage.values()):
        episode = ctx.repo.get_episode(episode_id)
        manifest: dict[str, Any] = dict(episode.manifest or {})
        totals = manifest.setdefault("llm_usage", {})
        for name, value in usage.items():
            totals[name] = totals.get(name, 0) + value
        ctx.repo.update_episode(episode_id, manifest=manifest)
    prompt = _PROMPT_OF.get(stage)
    ctx.repo.record_stage_run(
        episode_id,
        stage.value,
        seconds=seconds,
        model=_model_for(stage, ctx),
        prompt_version=f"{prompt}.v{PROMPT_VERSIONS[prompt]}"
        if prompt and ctx.settings.llm_enabled
        else None,
        seed=ctx.settings.seed,
    )
    return following


def stage_task(stage: Stage, *, max_retries: int = 3) -> Callable[[StageFunction], StageFunction]:
    """Register ``stage``'s function as the Celery task for its queue.

    Each stage retries on its own with backoff, so a failure never restarts the whole job.
    The undecorated function is returned unchanged, which keeps it directly callable in tests.
    """

    def decorator(function: StageFunction) -> StageFunction:
        @wraps(function)
        def task(self: Any, episode_id: str) -> None:
            configure_logging(get_settings().log_level)
            episode = UUID(episode_id)
            following = run_stage(
                stage,
                function,
                episode,
                get_context(),
                last_attempt=self.request.retries >= max_retries,
            )
            if following is not None:
                dispatch(following, episode_id=episode_id)

        celery_app.task(
            name=task_name(stage),
            bind=True,
            autoretry_for=(Exception,),
            retry_backoff=True,
            retry_jitter=True,
            max_retries=max_retries,
        )(task)
        return function

    return decorator
