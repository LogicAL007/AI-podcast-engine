"""Each stage run records the model that actually answered, so an episode written by the
fallback model says so (proposal slide 17: model versions logged for every episode)."""

from collections import Counter
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

from podcast_engine.common.models import EpisodeStatus
from podcast_engine.common.queue import Stage
from podcast_engine.common.runner import run_stage


def ctx_with(llm: Any) -> tuple[Any, list[dict[str, Any]]]:
    runs: list[dict[str, Any]] = []
    episode = SimpleNamespace(status=EpisodeStatus.PROCESSING, manifest={})
    repo = SimpleNamespace(
        get_episode=lambda _: episode,
        update_episode=lambda _, **fields: None,
        record_stage_run=lambda *_, **fields: runs.append(fields),
    )
    settings = SimpleNamespace(seed=1, llm_enabled=True, llm_provider="gemini",
                               llm_model="gemini-3.8-flash")  # fmt: skip
    return SimpleNamespace(repo=repo, settings=settings, budget=None, llm=llm), runs


def test_a_stage_written_by_the_fallback_model_is_logged_as_such() -> None:
    llm = SimpleNamespace(usage=Counter(), models_used=Counter({"gemini-3.8-flash": 4}))
    ctx, runs = ctx_with(llm)

    def factcheck(episode_id: UUID, ctx: Any = None) -> Stage | None:
        ctx.llm.models_used["gemini-3.6-flash"] += 1  # 3.8 was busy: the fallback answered
        ctx.llm.usage["input_tokens"] += 900
        return None

    run_stage(Stage.FACTCHECK, factcheck, uuid4(), ctx)
    assert runs[0]["model"] == "gemini:gemini-3.6-flash"


def test_without_a_model_call_the_configured_model_is_logged() -> None:
    ctx, runs = ctx_with(SimpleNamespace(usage=Counter(), models_used=Counter()))
    run_stage(Stage.FACTCHECK, lambda episode_id, ctx=None: None, uuid4(), ctx)
    assert runs[0]["model"] == "gemini:gemini-3.8-flash"
