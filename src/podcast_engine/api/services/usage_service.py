"""Today's Gemini budget, read from the counters the pipeline and the bot spend."""

from typing import Literal

from podcast_engine.api.models.usage_model import ModelUsage, UsageRead
from podcast_engine.common.config import Settings
from podcast_engine.common.quota import DailyBudget, MemoryCounter


class UsageService:
    def __init__(self, settings: Settings, budget: DailyBudget | None) -> None:
        self._settings = settings
        # No daily cap set: nothing is counted, but the day and its reset are still known.
        self._budget = budget or DailyBudget(MemoryCounter(), {})

    def today(self) -> UsageRead:
        settings, budget = self._settings, self._budget
        in_use: list[tuple[str, Literal["text", "voice"]]] = []
        if settings.llm_enabled and settings.llm_provider == "gemini":
            in_use.append((settings.llm_model, "text"))
        if settings.tts_backend == "gemini":
            in_use.append((settings.tts_model, "voice"))
        return UsageRead(
            day=budget.day(),
            resets_in_seconds=int(budget.resets_in().total_seconds()),
            writer="gemini" if settings.llm_enabled else "offline",
            voice_engine=settings.tts_backend,
            models=[
                ModelUsage(
                    model=model,
                    kind=kind,
                    used=budget.used(model),
                    limit=budget.limits.get(model),
                    left=budget.left(model),
                )
                for model, kind in in_use
            ],
        )
