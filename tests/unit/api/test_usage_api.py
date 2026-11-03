"""Today's Gemini usage: what is spent and left, for the sidebar's budget card."""

from typing import Any

from podcast_engine.api import dependencies
from podcast_engine.api.controllers.usage_controller import UsageController
from podcast_engine.api.services.usage_service import UsageService
from podcast_engine.common.config import Settings
from podcast_engine.common.quota import DailyBudget, MemoryCounter
from tests.unit.api.conftest import Harness

TEXT, VOICE = "gemini-3.8-flash", "gemini-3.8-flash-tts"


def _usage(harness: Harness, budget: DailyBudget | None, **settings: object) -> dict[str, Any]:
    config = Settings(llm_model=TEXT, tts_model=VOICE, **settings)  # type: ignore[arg-type]
    harness.client.app.dependency_overrides[dependencies.get_usage_controller] = (  # type: ignore[attr-defined]
        lambda: UsageController(UsageService(config, budget))
    )
    response = harness.client.get("/v1/usage")
    assert response.status_code == 200, response.text
    usage: dict[str, Any] = response.json()
    return usage


def test_reports_requests_used_and_left_for_each_model_in_use(harness: Harness) -> None:
    budget = DailyBudget(MemoryCounter(), {TEXT: 18, VOICE: 12})
    budget.spend(TEXT, 5)
    usage = _usage(harness, budget, llm_enabled=True, llm_provider="gemini", tts_backend="gemini")
    assert usage["writer"] == "gemini"
    assert usage["voice_engine"] == "gemini"
    assert usage["models"] == [
        {"model": TEXT, "kind": "text", "used": 5, "limit": 18, "left": 13},
        {"model": VOICE, "kind": "voice", "used": 0, "limit": 12, "left": 12},
    ]
    assert 0 < usage["resets_in_seconds"] <= 24 * 3600


def test_cloned_voices_and_the_offline_writer_use_no_gemini(harness: Harness) -> None:
    usage = _usage(harness, None, llm_enabled=False, tts_backend="chatterbox")
    assert (usage["writer"], usage["voice_engine"], usage["models"]) == (
        "offline",
        "chatterbox",
        [],
    )


def test_a_model_without_a_cap_is_listed_without_a_limit(harness: Harness) -> None:
    usage = _usage(harness, None, llm_enabled=True, llm_provider="gemini", tts_backend="say")
    assert usage["models"] == [
        {"model": TEXT, "kind": "text", "used": 0, "limit": None, "left": None}
    ]
