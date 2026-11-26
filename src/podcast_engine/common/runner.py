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
    """A stage's work: takes an episode id (and maybe a context), returns the next stage or None."""

    def __call__(self, episode_id: UUID, ctx: PipelineContext | None = None) -> Stage | None:
        """Run the stage for an episode.

        Args:
            episode_id: The episode.
            ctx: Shared clients; built from settings when omitted.

        Returns:
            The stage to run next, or None when the pipeline stops here.
        """
        ...


# Bad input or configuration (no sources, an unknown ranking profile, an unvoiced script) or a
# used-up daily quota: retrying cannot help, so the episode fails at once with the reason.
PERMANENT_ERRORS: tuple[type[Exception], ...] = (ValueError, LookupError, GeminiQuotaError)

log = get_logger("runner")

_PROMPT_OF = {Stage.RETRIEVE_PLAN: "outline", Stage.SCRIPT: "script", Stage.FACTCHECK: "factcheck"}


def _model_for(stage: Stage, ctx: PipelineContext) -> str | None:
    """Return the configured model behind a stage, for its run record.

    Args:
        stage: The stage.
        ctx: The pipeline context.

    Returns:
        ``provider:model`` (or ``offline``) for the LLM stages, the embedder for index, the TTS
        backend for voice, else None.
    """
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
    """Return the LLM's token counts so far in this process.

    Read only if this process already created an LLM client; one is never created here.

    Args:
        ctx: The pipeline context.

    Returns:
        Tokens used so far, by kind; empty when there is no client.
    """
    llm = ctx.__dict__.get("llm")
    return dict(llm.usage) if llm is not None else {}


def _llm_models(ctx: PipelineContext) -> dict[str, int]:
    """Return how many calls each model has answered so far in this process.

    With a fallback model, it is not always the configured one.

    Args:
        ctx: The pipeline context.

    Returns:
        Calls answered, by model; empty when there is no client.
    """
    llm = ctx.__dict__.get("llm")
    return dict(getattr(llm, "models_used", {})) if llm is not None else {}


def _answered_by(ctx: PipelineContext, before: dict[str, int]) -> str | None:
    """Return the model(s) that actually answered during a stage.

    Args:
        ctx: The pipeline context.
        before: Calls answered per model when the stage started.

    Returns:
        ``provider:model[+model]``, or None when no model answered.
    """
    answered = sorted(m for m, n in _llm_models(ctx).items() if n > before.get(m, 0))
    if not answered:
        return None
    return f"{ctx.settings.llm_provider}:{'+'.join(answered)}"


def _release_budget(ctx: PipelineContext, episode_id: UUID) -> None:
    """Give back the episode's unused daily-budget reservation, now it has stopped.

    Called when the episode ends, fails or pauses. Contexts in tests may have no budget, and an
    unreachable Redis is logged, never raised, so it cannot hide the stage's own outcome.

    Args:
        ctx: The pipeline context.
        episode_id: The episode that stopped.
    """
    try:
        budget = getattr(ctx, "budget", None)
        if budget is not None:
            budget.release(str(episode_id))
    except Exception:
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

    Bad input or configuration, or a used-up daily quota, fails the episode at once with the reason.
    A request the model refused also fails it at once, since each retry would spend a request and
    fail the same way. Other errors are re-raised so Celery retries, and fail the episode on the
    last attempt.

    The run record names the model that answered, not just the configured one: a fallback
    (``LLM_FALLBACK_MODEL``) may have written the stage, and every episode must say which (proposal
    slide 17). A one-host show's script stage records the narration prompt. Token use is added to
    the episode's manifest. The budget reservation is released whenever the pipeline stops:
    published, unchanged, held for review, cancelled or failed.

    Args:
        stage: The stage to run.
        function: The stage's work.
        episode_id: The episode.
        ctx: Shared clients.
        last_attempt: Whether a failure now is the final one, so the episode is marked failed.

    Returns:
        The stage to run next, or None when the pipeline stops.
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
        refused = is_refused(error)
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
    if prompt == "script" and ctx.settings.llm_enabled:
        prompt = script_prompt(
            ctx.repo.get_show(ctx.repo.get_episode(episode_id).show_id).host_count
        )
    ctx.repo.record_stage_run(
        episode_id,
        stage.value,
        seconds=seconds,
        model=_answered_by(ctx, models_before) or _model_for(stage, ctx),
        prompt_version=f"{prompt}.v{PROMPT_VERSIONS[prompt]}"
        if prompt and ctx.settings.llm_enabled
        else None,
        seed=ctx.settings.seed,
    )
    if following is not None and ctx.repo.get_episode(episode_id).status is EpisodeStatus.CANCELLED:
        log.info("pipeline_stopped", episode_id=str(episode_id), after=stage.value)
        following = None
    if following is None:
        _release_budget(ctx, episode_id)
    return following


def stage_task(stage: Stage, *, max_retries: int = 3) -> Callable[[StageFunction], StageFunction]:
    """Register a stage's function as the Celery task for its queue.

    Each stage retries on its own with backoff, so a failure never restarts the whole job. The
    undecorated function is returned unchanged, which keeps it directly callable in tests.

    Args:
        stage: The stage the function runs.
        max_retries: Retries before the episode is marked failed.

    Returns:
        The decorator.
    """

    def decorator(function: StageFunction) -> StageFunction:
        """Register the function's task and return the function unchanged.

        Args:
            function: The stage's work.

        Returns:
            The same function.
        """

        @wraps(function)
        def task(self: Any, episode_id: str) -> None:
            """Run the stage for an episode, then queue the next stage.

            Args:
                self: The bound Celery task, for its retry count.
                episode_id: The episode, as a string (Celery passes JSON).
            """
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
