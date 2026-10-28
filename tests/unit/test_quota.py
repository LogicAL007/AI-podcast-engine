"""The daily Gemini request budget: counted per Pacific day, checked before every request."""

from datetime import datetime
from types import SimpleNamespace
from typing import Any

import pytest

from podcast_engine.common.config import Settings
from podcast_engine.common.llm import GeminiQuotaError
from podcast_engine.common.quota import PACIFIC, DailyBudget, MemoryCounter, episode_needs

errors = pytest.importorskip("google.genai.errors")

from podcast_engine.stages.voice.backends import GeminiTtsBackend  # noqa: E402
from tests.unit.test_gemini_llm import (  # noqa: E402
    PER_MINUTE,
    FakeModels,
    ask,
    client,
    quota_error,
)

TEXT = "gemini-3.8-flash"
VOICE = "gemini-3.8-flash-tts"


def at(text: str) -> float:
    return datetime.fromisoformat(text).replace(tzinfo=PACIFIC).timestamp()


def test_counts_are_kept_per_model_and_start_again_at_midnight_pacific() -> None:
    now = [at("2026-10-27 23:30")]
    budget = DailyBudget(MemoryCounter(), {TEXT: 20, VOICE: 12}, clock=lambda: now[0])
    budget.spend(TEXT, 3)
    budget.spend("some-unlimited-model", 50)
    assert (budget.left(TEXT), budget.left(VOICE), budget.left("other")) == (17, 12, None)
    assert budget.resets_in().total_seconds() == 30 * 60

    now[0] = at("2026-10-28 00:01")
    assert budget.left(TEXT) == 20


def test_require_says_what_is_short_before_anything_is_sent() -> None:
    budget = DailyBudget(MemoryCounter(), {TEXT: 20, VOICE: 12})
    budget.spend(VOICE, 10)
    budget.require({TEXT: 8, VOICE: 2}, "a whole episode")
    with pytest.raises(GeminiQuotaError, match=r"needs 3 gemini-3\.8-flash-tts requests \(2 of"):
        budget.require({TEXT: 8, VOICE: 3}, "a whole episode")
    # A reserve keeps part of the day for others: 20 - 10 kept leaves room for 10.
    assert budget.shortfall({TEXT: 10}, reserve=10) is None
    assert budget.shortfall({TEXT: 11}, reserve=10) is not None


def test_an_episode_needs_one_request_per_part() -> None:
    settings = Settings(_env_file=None, llm_enabled=True, tts_backend="gemini")
    assert episode_needs(settings, 2) == {TEXT: 4, VOICE: 5}
    assert episode_needs(settings, 2, plan=False) == {TEXT: 3, VOICE: 5}
    offline = Settings(_env_file=None, llm_enabled=False, tts_backend="placeholder")
    assert episode_needs(offline, 6) == {}


def test_the_text_client_stops_at_the_budget_and_counts_only_requests_that_went_through() -> None:
    llm, models, _ = client([quota_error(PER_MINUTE)])
    llm.budget = DailyBudget(MemoryCounter(), {TEXT: 2})
    ask(llm)  # refused once for the minute's rate, then answered
    assert len(models.models) == 2
    assert llm.budget.used(TEXT) == 1  # a refused request is not counted
    ask(llm)
    with pytest.raises(GeminiQuotaError, match="Today's Gemini budget cannot cover"):
        ask(llm)
    assert len(models.models) == 3  # the third question was never sent


def test_with_the_budget_spent_the_text_client_moves_to_the_fallback() -> None:
    llm, models, _ = client([], fallback="gemini-3.8-flash-lite")
    llm.budget = DailyBudget(MemoryCounter(), {TEXT: 1, "gemini-3.8-flash-lite": 5})
    llm.budget.spend(TEXT)
    assert ask(llm).title == "Tides"
    assert models.models == ["gemini-3.8-flash-lite"]


def test_the_assistant_leaves_its_reserve_to_the_pipeline() -> None:
    llm, models, _ = client([])
    llm.budget = DailyBudget(MemoryCounter(), {TEXT: 20})
    llm.reserve = 10
    llm.budget.spend(TEXT, 10)
    with pytest.raises(GeminiQuotaError):
        ask(llm)
    assert models.models == []


AUDIO = SimpleNamespace(
    candidates=[
        SimpleNamespace(
            content=SimpleNamespace(
                parts=[SimpleNamespace(inline_data=SimpleNamespace(data=b"\x00\x00" * 10))]
            )
        )
    ]
)


def test_the_voice_backend_stops_at_the_budget() -> None:
    budget = DailyBudget(MemoryCounter(), {VOICE: 1})
    tts = GeminiTtsBackend("test-key", VOICE, budget=budget, sleep=lambda _: None)
    models: Any = FakeModels([AUDIO])
    tts.client = SimpleNamespace(models=models)  # type: ignore[assignment]
    tts.synthesise("Alex", "Hello there.")
    with pytest.raises(GeminiQuotaError, match=r"another gemini-3\.8-flash-tts request"):
        tts.synthesise("Alex", "And again.")
    assert len(models.models) == 1
    assert budget.used(VOICE) == 1
