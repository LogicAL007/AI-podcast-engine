import time
from collections.abc import Callable
from typing import Any, Protocol
from uuid import UUID

HOUR_S = 3600


class AssistantUsage(Protocol):
    """How many questions each person has asked this hour."""

    def take(self, user_id: UUID, per_hour: int) -> int | None:
        """Count one question.

        Args:
            user_id: The person asking.
            per_hour: How many questions each person may ask per hour.

        Returns:
            How many questions are left this hour, or None if the limit was already reached.
        """
        ...

    def retry_after(self) -> int:
        """Seconds until the hour's count starts again.

        Returns:
            Seconds until the hour's count starts again.
        """
        ...


class RedisAssistantUsage:
    """Hourly counts in Redis, so the limit holds across every API process.

    Each count expires after an hour. ``prefix`` keeps separate counts per feature (the assistant's
    questions, speech clips).
    """

    def __init__(
        self, client: Any, clock: Callable[[], float] = time.time, prefix: str = "assistant"
    ) -> None:
        """Create the counter.

        Args:
            client: A Redis client.
            clock: Returns the current Unix time; replaced in tests.
            prefix: The feature counted, the first part of each Redis key.
        """
        self._redis = client
        self._clock = clock
        self._prefix = prefix

    def take(self, user_id: UUID, per_hour: int) -> int | None:
        """Count one question in this hour's Redis key.

        Args:
            user_id: The person asking.
            per_hour: How many questions each person may ask per hour.

        Returns:
            How many questions are left this hour, or None if the limit was already reached.
        """
        key = f"{self._prefix}:{user_id}:{int(self._clock() // HOUR_S)}"
        used = int(self._redis.incr(key))
        if used == 1:
            self._redis.expire(key, HOUR_S)
        return per_hour - used if used <= per_hour else None

    def retry_after(self) -> int:
        """Seconds until the hour's count starts again.

        Returns:
            Seconds until the hour's count starts again.
        """
        return HOUR_S - int(self._clock() % HOUR_S)


class MemoryAssistantUsage:
    """The same hourly counts, in one process (tests, or a single API worker without Redis)."""

    def __init__(self, clock: Callable[[], float] = time.time) -> None:
        """Create the counter.

        Args:
            clock: Returns the current Unix time; replaced in tests.
        """
        self._clock = clock
        self._used: dict[tuple[UUID, int], int] = {}

    def take(self, user_id: UUID, per_hour: int) -> int | None:
        """Count one question in this hour's count.

        Args:
            user_id: The person asking.
            per_hour: How many questions each person may ask per hour.

        Returns:
            How many questions are left this hour, or None if the limit was already reached.
        """
        key = (user_id, int(self._clock() // HOUR_S))
        self._used[key] = self._used.get(key, 0) + 1
        used = self._used[key]
        return per_hour - used if used <= per_hour else None

    def retry_after(self) -> int:
        """Seconds until the hour's count starts again.

        Returns:
            Seconds until the hour's count starts again.
        """
        return HOUR_S - int(self._clock() % HOUR_S)
