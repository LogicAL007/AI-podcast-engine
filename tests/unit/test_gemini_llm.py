"""The Gemini planning and writing client under rate limits, daily caps and network blips.

The real SDK's error classes are used with a fake client, so nothing touches the network.
"""

from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest
from pydantic import BaseModel

errors = pytest.importorskip("google.genai.errors")
httpx = pytest.importorskip("httpx")

from podcast_engine.common.llm import GeminiClient, GeminiQuotaError  # noqa: E402
from podcast_engine.common.models import EpisodeStatus  # noqa: E402
from podcast_engine.common.queue import Stage  # noqa: E402
from podcast_engine.common.runner import run_stage  # noqa: E402

PER_MINUTE = "GenerateRequestsPerMinutePerProjectPerModel-FreeTier"
PER_DAY = "GenerateRequestsPerDayPerProjectPerModel-FreeTier"


class Answer(BaseModel):
    title: str


ANSWER = SimpleNamespace(
    text='{"title": "Tides"}',
    candidates=[SimpleNamespace(finish_reason=SimpleNamespace(name="STOP"))],
    usage_metadata=SimpleNamespace(
        prompt_token_count=10, candidates_token_count=5, thoughts_token_count=0
    ),
)


def quota_error(quota_id: str, delay: str = "10s") -> Any:
    return errors.ClientError(
        429,
        {
            "error": {
                "code": 429,
                "message": "You exceeded your current quota.",
                "status": "RESOURCE_EXHAUSTED",
                "details": [
                    {
                        "@type": "type.googleapis.com/google.rpc.QuotaFailure",
                        "violations": [{"quotaId": quota_id}],
                    },
                    {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": delay},
                ],
            }
        },
    )


class FakeModels:
    def __init__(self, outcomes: list[Any]) -> None:
        self.outcomes = outcomes
        self.models: list[str] = []

    def generate_content(self, *, model: str, **_: Any) -> Any:
        self.models.append(model)
        outcome = self.outcomes.pop(0) if self.outcomes else ANSWER
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def client(outcomes: list[Any], fallback: str = "") -> tuple[GeminiClient, FakeModels, list[float]]:
    waits: list[float] = []
    llm = GeminiClient(
        "test-key", "gemini-3.8-flash", seed=1, fallback=fallback, sleep=waits.append
    )
    models = FakeModels(outcomes)
    llm.client = SimpleNamespace(models=models)  # type: ignore[assignment]
    return llm, models, waits


def ask(llm: GeminiClient) -> Answer:
    return llm.parse(system="Plan.", user="Tides", output_format=Answer)


def test_a_rate_limit_waits_as_long_as_gemini_asks() -> None:
    llm, models, waits = client([quota_error(PER_MINUTE)])
    assert ask(llm).title == "Tides"
    assert len(models.models) == 2
    assert waits == [11.0]  # the asked-for 10 s, plus a second's margin


def test_a_used_up_daily_quota_fails_at_once_with_a_plain_message() -> None:
    llm, models, waits = client([quota_error(PER_DAY)])
    with pytest.raises(GeminiQuotaError, match=r"daily quota for gemini-3\.8-flash is used up"):
        ask(llm)
    assert len(models.models) == 1
    assert waits == []


def test_a_used_up_daily_quota_moves_to_the_fallback_model() -> None:
    llm, models, _ = client([quota_error(PER_DAY)], fallback="gemini-3.8-flash-lite")
    assert ask(llm).title == "Tides"
    assert models.models == ["gemini-3.8-flash", "gemini-3.8-flash-lite"]


@pytest.mark.parametrize(
    "blip",
    [
        httpx.ConnectError("[Errno -2] Name or service not known"),
        httpx.ReadTimeout("timed out"),
    ],
)
def test_network_blips_are_retried(blip: Exception) -> None:
    llm, models, waits = client([blip, blip])
    assert ask(llm).title == "Tides"
    assert len(models.models) == 3
    assert len(waits) == 2


def test_other_client_errors_are_not_retried() -> None:
    llm, models, waits = client([errors.ClientError(403, {"error": {"message": "bad key"}})])
    with pytest.raises(errors.ClientError):
        ask(llm)
    assert len(models.models) == 1
    assert waits == []


def test_the_stage_fails_on_its_first_attempt_when_the_daily_quota_is_used_up() -> None:
    updates: list[dict[str, Any]] = []
    episode = SimpleNamespace(status=EpisodeStatus.QUEUED)
    repo = SimpleNamespace(
        get_episode=lambda _: episode,
        update_episode=lambda _, **fields: updates.append(fields),
    )
    ctx: Any = SimpleNamespace(repo=repo, settings=SimpleNamespace())

    def plan(episode_id: UUID, ctx: Any = None) -> Stage | None:
        raise GeminiQuotaError("Gemini's daily quota for gemini-3.8-flash is used up.")

    # Not the last attempt, yet nothing is raised for Celery to retry: the episode fails now.
    assert run_stage(Stage.RETRIEVE_PLAN, plan, uuid4(), ctx, last_attempt=False) is None
    assert updates[-1]["status"] is EpisodeStatus.FAILED
    assert updates[-1]["error"].startswith("retrieve_plan: Gemini's daily quota")


def test_a_request_gemini_rejects_fails_the_stage_without_retries() -> None:
    updates: list[dict[str, Any]] = []
    episode = SimpleNamespace(status=EpisodeStatus.QUEUED)
    repo = SimpleNamespace(
        get_episode=lambda _: episode,
        update_episode=lambda _, **fields: updates.append(fields),
    )
    ctx: Any = SimpleNamespace(repo=repo, settings=SimpleNamespace())
    rejected = errors.ClientError(400, {"error": {"message": "speaker missing"}})

    def stage(episode_id: UUID, ctx: Any = None) -> Stage | None:
        raise rejected

    assert run_stage(Stage.VOICE, stage, uuid4(), ctx, last_attempt=False) is None
    assert updates[-1]["status"] is EpisodeStatus.FAILED
    assert "speaker missing" in updates[-1]["error"]
