"""How many questions each person has asked the assistant this hour (Redis, so the limit holds
across every API process)."""

import time
from collections.abc import Callable
from typing import Any, Protocol
from uuid import UUID

HOUR_S = 3600


class AssistantUsage(Protocol):
    def take(self, user_id: UUID, per_hour: int) -> int | None:
        """Count one question. Returns how many are left this hour, or None if none were."""
        ...

    def retry_after(self) -> int:
        """Seconds until the hour's count starts again."""
        ...


class RedisAssistantUsage:
    def __init__(self, client: Any, clock: Callable[[], float] = time.time) -> None:
        self._redis = client
        self._clock = clock

    def take(self, user_id: UUID, per_hour: int) -> int | None:
        key = f"assistant:{user_id}:{int(self._clock() // HOUR_S)}"
        used = int(self._redis.incr(key))
        if used == 1:
            self._redis.expire(key, HOUR_S)
        return per_hour - used if used <= per_hour else None

    def retry_after(self) -> int:
        return HOUR_S - int(self._clock() % HOUR_S)


class MemoryAssistantUsage:
    """The same counts, in one process (tests, or a single API worker without Redis)."""

    def __init__(self, clock: Callable[[], float] = time.time) -> None:
        self._clock = clock
        self._used: dict[tuple[UUID, int], int] = {}

    def take(self, user_id: UUID, per_hour: int) -> int | None:
        key = (user_id, int(self._clock() // HOUR_S))
        self._used[key] = self._used.get(key, 0) + 1
        used = self._used[key]
        return per_hour - used if used <= per_hour else None

    def retry_after(self) -> int:
        return HOUR_S - int(self._clock() % HOUR_S)
