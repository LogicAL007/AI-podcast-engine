"""A daily request budget per Gemini model, so the pipeline stops before the free tier's cap.

Gemini's free tier allows a fixed number of requests per model per day, reset at midnight Pacific
time. Once that is used up every further call fails until the reset, often halfway through an
episode. The budget counts the requests actually sent (rate-limited ones are refused before they
count) in Redis, so every worker and the API share one count. Each call checks the budget first,
and the stages check that a whole step fits before they spend anything on it.

``python -m podcast_engine.common.quota`` prints today's counts.
"""

import time
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any, Protocol
from zoneinfo import ZoneInfo

from podcast_engine.common.config import Settings
from podcast_engine.common.llm import GeminiQuotaError

PACIFIC = ZoneInfo("America/Los_Angeles")  # where Google's daily quotas reset
KEEP_S = 2 * 24 * 3600  # a day's count is kept a little past its day, then Redis drops it


class Counter(Protocol):
    """The few Redis commands the budget uses."""

    def get(self, key: str) -> Any: ...

    def incrby(self, key: str, amount: int) -> Any: ...

    def expire(self, key: str, seconds: int) -> Any: ...


class MemoryCounter:
    """The same counts in one process (tests, or a run without Redis)."""

    def __init__(self) -> None:
        self.counts: dict[str, int] = {}

    def get(self, key: str) -> int | None:
        return self.counts.get(key)

    def incrby(self, key: str, amount: int) -> int:
        self.counts[key] = self.counts.get(key, 0) + amount
        return self.counts[key]

    def expire(self, key: str, seconds: int) -> bool:  # noqa: ARG002 - one process never expires
        return key in self.counts


class DailyBudget:
    """How many requests each model may still take today. Models without a limit are not counted."""

    def __init__(
        self, counter: Counter, limits: dict[str, int], clock: Callable[[], float] = time.time
    ) -> None:
        self.counter = counter
        self.limits = {model: limit for model, limit in limits.items() if model and limit > 0}
        self.clock = clock

    def _now(self) -> datetime:
        return datetime.fromtimestamp(self.clock(), PACIFIC)

    def day(self) -> str:
        """Today's Pacific date, which the counts are kept under."""
        return f"{self._now():%Y-%m-%d}"

    def _key(self, model: str) -> str:
        return f"gemini-requests:{self.day()}:{model}"

    def used(self, model: str) -> int:
        return int(self.counter.get(self._key(model)) or 0)

    def left(self, model: str) -> int | None:
        """Requests left today, or None when the model has no limit."""
        limit = self.limits.get(model)
        return None if limit is None else max(limit - self.used(model), 0)

    def spend(self, model: str, requests: int = 1) -> None:
        if model not in self.limits:
            return
        key = self._key(model)
        self.counter.incrby(key, requests)
        self.counter.expire(key, KEEP_S)

    def resets_in(self) -> timedelta:
        now = self._now()
        midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        return midnight - now

    def shortfall(self, needs: dict[str, int], *, reserve: int = 0) -> str | None:
        """Why ``needs`` (requests per model) does not fit in today's budget, or None if it does.

        ``reserve`` requests of each limit stay unused, kept for something more important.
        """
        short = []
        for model, wanted in needs.items():
            left = self.left(model)
            if left is not None and wanted > left - reserve:
                usable = max(left - reserve, 0)
                short.append(
                    f"{wanted} {model} request{'s' if wanted != 1 else ''} "
                    f"({usable} of today's {self.limits[model]} left)"
                )
        return "; ".join(short) or None

    def require(self, needs: dict[str, int], purpose: str, *, reserve: int = 0) -> None:
        """Raise GeminiQuotaError, before anything is sent, if ``needs`` would pass the budget."""
        short = self.shortfall(needs, reserve=reserve)
        if short:
            hours = self.resets_in().total_seconds() / 3600
            raise GeminiQuotaError(
                f"Today's Gemini budget cannot cover {purpose}: it needs {short}. The free "
                f"quota resets at midnight Pacific time, in about {hours:.0f} h; raise "
                "LLM_REQUESTS_PER_DAY or TTS_REQUESTS_PER_DAY if your quota is larger."
            )


def episode_needs(settings: Settings, segments: int, *, plan: bool = True) -> dict[str, int]:
    """Gemini requests a whole episode takes without rewrites, per model.

    Text: the outline (``plan``), one script request per segment and one fact-check. Voice: one
    request per part read aloud: the disclosure, the opening, each segment and the closing.
    """
    needs: dict[str, int] = {}
    if settings.llm_enabled and settings.llm_provider == "gemini":
        needs[settings.llm_model] = int(plan) + segments + 1
    if settings.tts_backend == "gemini":
        needs[settings.tts_model] = segments + 3
    return needs


def make_budget(settings: Settings) -> DailyBudget | None:
    """The budget for the configured models, or None when no daily limit is set."""
    limits = {
        settings.llm_model: settings.llm_requests_per_day,
        # A fallback model has its own quota; it gets the same budget.
        settings.llm_fallback_model: settings.llm_requests_per_day,
        settings.tts_model: settings.tts_requests_per_day,
    }
    if settings.llm_provider != "gemini":
        limits = {settings.tts_model: settings.tts_requests_per_day}
    if not any(limit > 0 for limit in limits.values()):
        return None
    import redis

    return DailyBudget(redis.Redis.from_url(settings.redis_url, socket_timeout=2), limits)


def main() -> None:
    from podcast_engine.common.config import get_settings

    budget = make_budget(get_settings())
    if budget is None:
        lines = ["No daily limit is set (LLM_REQUESTS_PER_DAY and TTS_REQUESTS_PER_DAY are 0)."]
    else:
        hours = budget.resets_in().total_seconds() / 3600
        lines = [f"Pacific day {budget.day()}, resets in about {hours:.1f} h"] + [
            f"  {model}: {budget.used(model)} used, {budget.left(model)} left of {limit}"
            for model, limit in budget.limits.items()
        ]
    print("\n".join(lines))  # noqa: T201 - the command's output


if __name__ == "__main__":
    main()
