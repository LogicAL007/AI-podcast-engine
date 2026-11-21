"""Decorator that turns a stage function into a retryable, timed, chained queue task."""

import time
from collections.abc import Callable
from functools import wraps
from typing import Any, Protocol
from uuid import UUID

from podcast_engine.common.config import get_settings
from podcast_engine.common.context import (
    PROMPT_VERSIONS,
    PipelineContext,
    get_context,
    script_prompt,
)
from podcast_engine.common.llm import GeminiQuotaError, is_refused
from podcast_engine.common.logging import configure_logging, get_logger
from podcast_engine.common.models import EpisodeStatus
from podcast_engine.common.queue import Stage, celery_app, dispatch, task_name
from podcast_engine.common.quota import spending_for
from podcast_engine.common.timing import stage_timer


class StageFunction(Protocol):
    """Takes an episode id (and optionally a context); returns the next stage, or None."""

    def __call__(self, episode_id: UUID, ctx: PipelineContext | None = None) -> Stage | None: ...


# Bad input or configuration (no sources, an unknown ranking profile, an unvoiced script) or a
# used-up daily quota: retrying cannot help, so the episode fails at once with the reason.
PERMANENT_ERRORS: tuple[type[Exception], ...] = (ValueError, LookupError, GeminiQuotaError)

log = get_logger("runner")

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


def _llm_models(ctx: PipelineContext) -> dict[str, int]:
    """Calls answered per model so far: with a fallback, not always the configured one."""
    llm = ctx.__dict__.get("llm")
    return dict(getattr(llm, "models_used", {})) if llm is not None else {}


def _answered_by(ctx: PipelineContext, before: dict[str, int]) -> str | None:
    """The model(s) that actually answered during a stage, as provider:model[+model]."""
    answered = sorted(m for m, n in _llm_models(ctx).items() if n > before.get(m, 0))
    if not answered:
        return None
    return f"{ctx.settings.llm_provider}:{'+'.join(answered)}"


def _release_budget(ctx: PipelineContext, episode_id: UUID) -> None:
    """The episode has stopped (ended, failed or paused): give back its unused reservation."""
    try:
        budget = getattr(ctx, "budget", None)  # test contexts may have none
        if budget is not None:
            budget.release(str(episode_id))
    except Exception:  # an unreachable Redis must not hide the stage's own outcome
        log.exception("budget_release_failed", episode_id=str(episode_id))


def run_stage(
    stage: Stage,
    function: StageFunction,
    episode_id: UUID,
    ctx: PipelineContext,
    *,
    last_attempt: bool = True,
) -> Stage | None:
    """Run one stage for an episode, recording progress, timing and failure on the episode row.

    A cancelled episode runs nothing. One cancelled while its stage runs finishes that stage, but
    nothing is queued after it.
    """
    if ctx.repo.get_episode(episode_id).status is EpisodeStatus.CANCELLED:
        log.info("stage_skipped", episode_id=str(episode_id), stage=stage.value, reason="cancelled")
        return None
    ctx.repo.update_episode(
        episode_id, status=EpisodeStatus.PROCESSING, stage=stage.value, error=None
    )
    usage_before = _llm_usage(ctx)
    models_before = _llm_models(ctx)
    started = time.perf_counter()
    try:
        with stage_timer(stage, episode_id), spending_for(str(episode_id)):
            following = function(episode_id, ctx)
    except PERMANENT_ERRORS as error:
        ctx.repo.update_episode(
            episode_id, status=EpisodeStatus.FAILED, error=f"{stage.value}: {error}"[:2000]
        )
        _release_budget(ctx, episode_id)
        return None
    except Exception as error:
        refused = is_refused(error)  # each retry would spend a request and fail the same way
        if last_attempt or refused:
            ctx.repo.update_episode(
                episode_id, status=EpisodeStatus.FAILED, error=f"{stage.value}: {error}"[:2000]
            )
            _release_budget(ctx, episode_id)
        if refused:
            return None
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
    if prompt == "script" and ctx.settings.llm_enabled:  # a narration for a one-host show
        prompt = script_prompt(
            ctx.repo.get_show(ctx.repo.get_episode(episode_id).show_id).host_count
        )
    ctx.repo.record_stage_run(
        episode_id,
        stage.value,
        seconds=seconds,
        # The model that answered, not just the configured one: a fallback (LLM_FALLBACK_MODEL)
        # may have written this stage, and every episode must say which (proposal slide 17).
        model=_answered_by(ctx, models_before) or _model_for(stage, ctx),
        prompt_version=f"{prompt}.v{PROMPT_VERSIONS[prompt]}"
        if prompt and ctx.settings.llm_enabled
        else None,
        seed=ctx.settings.seed,
    )
    if following is not None and ctx.repo.get_episode(episode_id).status is EpisodeStatus.CANCELLED:
        log.info("pipeline_stopped", episode_id=str(episode_id), after=stage.value)
        following = None
    if following is None:  # published, unchanged, held for review, or cancelled
        _release_budget(ctx, episode_id)
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
