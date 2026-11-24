import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timedelta
from typing import Any, Protocol
from zoneinfo import ZoneInfo

from podcast_engine.common.config import Settings
from podcast_engine.common.llm import GeminiQuotaError

PACIFIC = ZoneInfo("America/Los_Angeles")  # where Google's daily quotas reset
KEEP_S = 2 * 24 * 3600  # a day's count is kept a little past its day, then Redis drops it

# The episode whose stage is running in this thread, if any: its requests use its reservation.
_SPENDING_FOR: ContextVar[str | None] = ContextVar("gemini_spending_for", default=None)


@contextmanager
def spending_for(owner: str) -> Iterator[None]:
    """Make requests inside the block belong to an episode, so they use its reservation.

    The stage runner sets it around each stage.

    Args:
        owner: The episode's id.

    Yields:
        Nothing; requests made inside the ``with`` block are the episode's.
    """
    token = _SPENDING_FOR.set(owner)
    try:
        yield
    finally:
        _SPENDING_FOR.reset(token)


class Counter(Protocol):
    """The few Redis commands the budget uses."""

    def get(self, key: str) -> Any:
        """Read a counter.

        Args:
            key: The key.

        Returns:
            Its value, or None when it is not set.
        """
        ...

    def incrby(self, key: str, amount: int) -> Any:
        """Add to a counter.

        Args:
            key: The key.
            amount: How much to add; negative to take away.

        Returns:
            The new value.
        """
        ...

    def expire(self, key: str, seconds: int) -> Any:
        """Set a key to expire.

        Args:
            key: The key.
            seconds: Seconds until it expires.

        Returns:
            Whether the key exists.
        """
        ...

    def hincrby(self, name: str, key: str, amount: int = 1) -> Any:
        """Add to a field of a hash.

        Args:
            name: The hash.
            key: The field.
            amount: How much to add.

        Returns:
            The field's new value.
        """
        ...

    def hgetall(self, name: str) -> Any:
        """Read every field of a hash.

        Args:
            name: The hash.

        Returns:
            The fields and their values.
        """
        ...

    def hdel(self, name: str, *keys: str) -> Any:
        """Remove fields from a hash.

        Args:
            name: The hash.
            *keys: The fields to remove.

        Returns:
            How many fields were removed.
        """
        ...


class MemoryCounter:
    """The same counts in one process (tests, or a run without Redis)."""

    def __init__(self) -> None:
        """Create empty counters."""
        self.counts: dict[str, int] = {}
        self.hashes: dict[str, dict[str, int]] = {}

    def get(self, key: str) -> int | None:
        """Read a counter.

        Args:
            key: The key.

        Returns:
            Its value, or None when it is not set.
        """
        return self.counts.get(key)

    def incrby(self, key: str, amount: int) -> int:
        """Add to a counter.

        Args:
            key: The key.
            amount: How much to add.

        Returns:
            The new value.
        """
        self.counts[key] = self.counts.get(key, 0) + amount
        return self.counts[key]

    def expire(self, key: str, seconds: int) -> bool:  # noqa: ARG002 - one process never expires
        """Accept an expiry; memory counters never expire.

        Args:
            key: The key.
            seconds: Ignored.

        Returns:
            Whether the key exists.
        """
        return key in self.counts or key in self.hashes

    def hincrby(self, name: str, key: str, amount: int = 1) -> int:
        """Add to a field of a hash.

        Args:
            name: The hash.
            key: The field.
            amount: How much to add.

        Returns:
            The field's new value.
        """
        fields = self.hashes.setdefault(name, {})
        fields[key] = fields.get(key, 0) + amount
        return fields[key]

    def hgetall(self, name: str) -> dict[str, int]:
        """Read every field of a hash.

        Args:
            name: The hash.

        Returns:
            A copy of the fields and their values.
        """
        return dict(self.hashes.get(name, {}))

    def hdel(self, name: str, *keys: str) -> int:
        """Remove fields from a hash.

        Args:
            name: The hash.
            *keys: The fields to remove.

        Returns:
            How many fields were removed.
        """
        held = self.hashes.get(name, {})
        return sum(held.pop(key, None) is not None for key in keys)


class DailyBudget:
    """A daily request budget per Gemini model, so the pipeline stops before the free tier cap.

    Gemini's free tier allows a fixed number of requests per model per day, reset at midnight
    Pacific time. Once that is used up every further call fails until the reset, often halfway
    through an episode. The budget counts, in Redis, the requests Gemini actually served or rejected
    as invalid, so every worker and the API share one count. Answers that did no work (overloaded
    503s, rate-limit 429s, network failures) are not counted. Each call checks the budget first.
    Models without a limit are not counted.

    An episode reserves the requests it needs when it is planned. Its own requests draw that
    reservation down; nothing else (the bot, other episodes) may spend it. The reservation is
    released when the episode ends, fails or pauses for review.
    """

    def __init__(
        self, counter: Counter, limits: dict[str, int], clock: Callable[[], float] = time.time
    ) -> None:
        """Create the budget.

        Args:
            counter: Where the counts are kept: Redis, or memory in tests.
            limits: Requests allowed per model per day; models with 0 are not counted.
            clock: Returns the current Unix time; replaced in tests.
        """
        self.counter = counter
        self.limits = {model: limit for model, limit in limits.items() if model and limit > 0}
        self.clock = clock

    def _now(self) -> datetime:
        """Return the current time in Pacific time, where Google's daily quotas reset.

        Returns:
            The current time.
        """
        return datetime.fromtimestamp(self.clock(), PACIFIC)

    def day(self) -> str:
        """Return today's Pacific date, which the counts are kept under.

        Returns:
            ``YYYY-MM-DD``.
        """
        return f"{self._now():%Y-%m-%d}"

    def _key(self, model: str) -> str:
        """Return the key of a model's count today.

        Args:
            model: The model.

        Returns:
            The Redis key.
        """
        return f"gemini-requests:{self.day()}:{model}"

    def _held_key(self, model: str) -> str:
        """Return the key of a model's reservations today.

        Args:
            model: The model.

        Returns:
            The Redis key of the hash of reservations by episode.
        """
        return f"gemini-reserved:{self.day()}:{model}"

    def used(self, model: str) -> int:
        """Return how many requests a model has taken today.

        Args:
            model: The model.

        Returns:
            The count.
        """
        return int(self.counter.get(self._key(model)) or 0)

    def left(self, model: str) -> int | None:
        """Return how many requests a model has left today.

        Args:
            model: The model.

        Returns:
            The requests left, or None when the model has no limit.
        """
        limit = self.limits.get(model)
        return None if limit is None else max(limit - self.used(model), 0)

    def holdings(self, model: str) -> dict[str, int]:
        """Return the requests each episode still has reserved for a model today.

        Args:
            model: The model.

        Returns:
            Each episode's reservation, leaving out empty ones.
        """
        raw = self.counter.hgetall(self._held_key(model)) or {}
        held = {(k.decode() if isinstance(k, bytes) else str(k)): int(v) for k, v in raw.items()}
        return {owner: n for owner, n in held.items() if n > 0}

    def available(self, model: str, owner: str | None = None) -> int | None:
        """Return what an episode may still spend today: what is left, less what others reserved.

        Args:
            model: The model.
            owner: The episode asking, whose own reservation counts as available, or None.

        Returns:
            The requests available, or None when the model has no limit.
        """
        left = self.left(model)
        if left is None:
            return None
        others = sum(n for who, n in self.holdings(model).items() if who != owner)
        return max(left - others, 0)

    def reserve(self, owner: str, needs: dict[str, int], purpose: str) -> None:
        """Set aside requests for an episode, after checking they fit.

        Args:
            owner: The episode.
            needs: Requests needed per model.
            purpose: What they are for, for the error message.

        Raises:
            GeminiQuotaError: The requests do not fit in what is available today.
        """
        with spending_for(owner):
            self.require(needs, purpose)
        for model, wanted in needs.items():
            if model not in self.limits:
                continue
            key = self._held_key(model)
            current = self.holdings(model).get(owner, 0)
            self.counter.hincrby(key, owner, wanted - current)
            self.counter.expire(key, KEEP_S)

    def release(self, owner: str) -> None:
        """Give back whatever an episode still has reserved.

        Args:
            owner: The episode.
        """
        for model in self.limits:
            self.counter.hdel(self._held_key(model), owner)

    def spend(self, model: str, requests: int = 1) -> None:
        """Count requests a model served, drawing down the running episode's reservation.

        The count is kept a little past its day, then Redis drops it.

        Args:
            model: The model.
            requests: How many requests to count.
        """
        if model not in self.limits:
            return
        key = self._key(model)
        self.counter.incrby(key, requests)
        self.counter.expire(key, KEEP_S)
        owner = _SPENDING_FOR.get()
        if owner is not None and (held := self.holdings(model).get(owner, 0)):
            self.counter.hincrby(self._held_key(model), owner, -min(held, requests))

    def resets_in(self) -> timedelta:
        """Return the time until the quota resets at midnight Pacific time.

        Returns:
            The time left today.
        """
        now = self._now()
        midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        return midnight - now

    def shortfall(self, needs: dict[str, int], *, reserve: int = 0) -> str | None:
        """Explain why some requests do not fit in today's budget.

        Requests other episodes have reserved are not available; the running episode's own are.

        Args:
            needs: Requests needed per model.
            reserve: Requests of each limit to leave unused, kept for something more important.

        Returns:
            What is short, per model, or None when everything fits.
        """
        owner = _SPENDING_FOR.get()
        short = []
        for model, wanted in needs.items():
            available = self.available(model, owner)
            if available is not None and wanted > available - reserve:
                usable = max(available - reserve, 0)
                held = sum(n for who, n in self.holdings(model).items() if who != owner)
                note = f", {held} reserved by other episodes" if held else ""
                short.append(
                    f"{wanted} {model} request{'s' if wanted != 1 else ''} "
                    f"({usable} of today's {self.limits[model]} left{note})"
                )
        return "; ".join(short) or None

    def require(self, needs: dict[str, int], purpose: str, *, reserve: int = 0) -> None:
        """Check, before anything is sent, that some requests fit in today's budget.

        Args:
            needs: Requests needed per model.
            purpose: What they are for, for the error message.
            reserve: Requests of each limit to leave unused.

        Raises:
            GeminiQuotaError: They do not fit; the message says what is short and when the quota
                resets.
        """
        short = self.shortfall(needs, reserve=reserve)
        if short:
            hours = self.resets_in().total_seconds() / 3600
            raise GeminiQuotaError(
                f"Today's Gemini budget cannot cover {purpose}: it needs {short}. The free "
                f"quota resets at midnight Pacific time, in about {hours:.0f} h; raise "
                "LLM_REQUESTS_PER_DAY or TTS_REQUESTS_PER_DAY if your quota is larger."
            )


def episode_needs(settings: Settings, segments: int, *, plan: bool = True) -> dict[str, int]:
    """Count the Gemini requests a whole episode takes without rewrites, per model.

    Text: the outline (``plan``), one script request per segment and one fact-check. Voice: one
    request per part read aloud: the disclosure, the opening, each segment and the closing.

    Args:
        settings: Which models write and voice.
        segments: How many segments the episode has.
        plan: Whether the outline is planned afresh (not for a refresh).

    Returns:
        Requests needed per model.
    """
    needs: dict[str, int] = {}
    if settings.llm_enabled and settings.llm_provider == "gemini":
        needs[settings.llm_model] = int(plan) + segments + 1
    if settings.tts_backend == "gemini":
        needs[settings.tts_model] = segments + 3
    return needs


def reserve_episode(
    budget: DailyBudget, settings: Settings, owner: str, segments: int, *, plan: bool = True
) -> None:
    """Reserve a whole episode's requests, on the fallback model if the main one cannot.

    The text client moves to the fallback by itself once the main model's budget is spent, so the
    episode's text requests are then reserved there.

    Args:
        budget: Today's budget.
        settings: Which models write and voice, and the fallback.
        owner: The episode.
        segments: How many segments it has.
        plan: Whether the outline is planned afresh.

    Raises:
        GeminiQuotaError: Neither the main nor the fallback model can cover the episode.
    """
    needs = episode_needs(settings, segments, plan=plan)
    try:
        budget.reserve(owner, needs, "a whole episode")
    except GeminiQuotaError:
        fallback = settings.llm_fallback_model
        if not fallback or settings.llm_model not in needs:
            raise
        moved = {
            fallback if model == settings.llm_model else model: n for model, n in needs.items()
        }
        budget.reserve(owner, moved, "a whole episode")


def make_budget(settings: Settings) -> DailyBudget | None:
    """Return the budget for the configured models.

    A fallback model has its own quota and gets the same budget as the main one.

    Args:
        settings: The models and their daily limits.

    Returns:
        The budget, counted in Redis, or None when no daily limit is set.
    """
    limits = {
        settings.llm_model: settings.llm_requests_per_day,
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
    """Print today's counts: ``python -m podcast_engine.common.quota``."""
    from podcast_engine.common.config import get_settings

    budget = make_budget(get_settings())
    if budget is None:
        lines = ["No daily limit is set (LLM_REQUESTS_PER_DAY and TTS_REQUESTS_PER_DAY are 0)."]
    else:
        hours = budget.resets_in().total_seconds() / 3600
        lines = [f"Pacific day {budget.day()}, resets in about {hours:.1f} h"] + [
            f"  {model}: {budget.used(model)} used, {budget.left(model)} left of {limit}, "
            f"{sum(budget.holdings(model).values())} reserved"
            for model, limit in budget.limits.items()
        ]
    print("\n".join(lines))  # noqa: T201 - the command's output


if __name__ == "__main__":
    main()
