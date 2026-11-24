from typing import Literal

from podcast_engine.api.models.usage_model import ModelUsage, UsageRead
from podcast_engine.common.config import Settings
from podcast_engine.common.quota import DailyBudget, MemoryCounter


class UsageService:
    """Today's Gemini budget, read from the counters the pipeline and the bot spend."""

    def __init__(self, settings: Settings, budget: DailyBudget | None) -> None:
        """Create the service.

        Args:
            settings: The app settings: which models and voice backend are in use.
            budget: The shared daily budget, or None when no daily cap is set; then nothing is
                counted, but the day and its reset are still reported.
        """
        self._settings = settings
        self._budget = budget or DailyBudget(MemoryCounter(), {})

    def today(self) -> UsageRead:
        """Report today's use of each Gemini model in use.

        Lists the text model when the LLM is on and Gemini writes, and the TTS model when Gemini
        voices episodes.

        Returns:
            The day, the time until the quota resets, who writes and voices, and each model's
            budget.
        """
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
