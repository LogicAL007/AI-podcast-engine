"""Failed-login and reset-request counters, shared by every API process through Redis.

Following OWASP's authentication guidance, failures are counted per account (so spreading guesses
over many addresses does not help) and per address (so one address cannot sweep many accounts).
An account's lock is temporary. Accounts are keyed by a hash of the lower-cased email: Redis never
holds the address, and an unknown email is counted the same as a real one, so a lock never reveals
whether an account exists.
"""

import hashlib
import time
from collections.abc import Callable
from typing import Any, Protocol

from podcast_engine.common.logging import get_logger

log = get_logger("api.login_attempts")


def account_key(email: str) -> str:
    return hashlib.sha256(email.strip().lower().encode()).hexdigest()


class LoginAttempts(Protocol):
    def account_locked(self, account: str) -> bool: ...

    def address_retry_after(self, address: str) -> int:
        """Seconds until the address may try again; 0 if it may now."""
        ...

    def record_failure(self, account: str | None, address: str) -> bool:
        """Count a failure; True if it just locked the account."""
        ...

    def clear(self, account: str) -> None: ...

    def reset_requests(self, account: str) -> int:
        """Count one more reset request for the account this hour; returns the count."""
        ...


class LimitsConfig:
    def __init__(
        self,
        *,
        max_failures: int,
        address_max_failures: int,
        window_s: int,
        lockout_s: int,
        reset_max: int,
    ) -> None:
        self.max_failures = max_failures
        self.address_max_failures = address_max_failures
        self.window_s = window_s
        self.lockout_s = lockout_s
        self.reset_max = reset_max


class RedisLoginAttempts:
    """Fixed-window counters with expiry. If Redis is unreachable, logins are not limited (and
    the failure is logged): an outage of the counters should not lock everyone out."""

    def __init__(self, client: Any, limits: LimitsConfig) -> None:
        self._redis = client
        self.limits = limits

    def _safe[T](self, default: T, call: Callable[[], T]) -> T:
        try:
            return call()
        except Exception:  # redis errors: fail open, loudly
            log.exception("login_limits_unavailable")
            return default

    def account_locked(self, account: str) -> bool:
        return self._safe(False, lambda: bool(self._redis.exists(f"login:lock:{account}")))

    def address_retry_after(self, address: str) -> int:
        def check() -> int:
            count = int(self._redis.get(f"login:fail:addr:{address}") or 0)
            if count < self.limits.address_max_failures:
                return 0
            return max(int(self._redis.ttl(f"login:fail:addr:{address}")), 1)

        return self._safe(0, check)

    def record_failure(self, account: str | None, address: str) -> bool:
        def record() -> bool:
            limits = self.limits
            pipe = self._redis.pipeline()
            pipe.incr(f"login:fail:addr:{address}")
            pipe.expire(f"login:fail:addr:{address}", limits.window_s, nx=True)
            if account is not None:
                pipe.incr(f"login:fail:acct:{account}")
                pipe.expire(f"login:fail:acct:{account}", limits.window_s, nx=True)
            results = pipe.execute()
            if account is not None and int(results[2]) >= limits.max_failures:
                self._redis.set(f"login:lock:{account}", 1, ex=limits.lockout_s)
                self._redis.delete(f"login:fail:acct:{account}")
                log.warning("account_locked", minutes=limits.lockout_s // 60)
                return True
            return False

        return self._safe(False, record)

    def clear(self, account: str) -> None:
        self._safe(
            None, lambda: self._redis.delete(f"login:fail:acct:{account}", f"login:lock:{account}")
        )

    def reset_requests(self, account: str) -> int:
        def count() -> int:
            pipe = self._redis.pipeline()
            pipe.incr(f"reset:req:{account}")
            pipe.expire(f"reset:req:{account}", 3600, nx=True)
            return int(pipe.execute()[0])

        return self._safe(0, count)


class MemoryLoginAttempts:
    """The same rules in memory, with a clock tests control."""

    def __init__(self, limits: LimitsConfig, clock: Callable[[], float] = time.monotonic) -> None:
        self.limits = limits
        self._clock = clock
        self._counts: dict[str, tuple[int, float]] = {}  # key -> (count, expires at)
        self._locks: dict[str, float] = {}

    def _get(self, key: str) -> tuple[int, float]:
        count, expires = self._counts.get(key, (0, 0.0))
        return (count, expires) if expires > self._clock() else (0, 0.0)

    def _incr(self, key: str, ttl: float) -> int:
        count, expires = self._get(key)
        self._counts[key] = (count + 1, expires or self._clock() + ttl)
        return count + 1

    def account_locked(self, account: str) -> bool:
        return self._locks.get(account, 0.0) > self._clock()

    def address_retry_after(self, address: str) -> int:
        count, expires = self._get(f"addr:{address}")
        if count < self.limits.address_max_failures:
            return 0
        return max(int(expires - self._clock()), 1)

    def record_failure(self, account: str | None, address: str) -> bool:
        self._incr(f"addr:{address}", self.limits.window_s)
        failures = self._incr(f"acct:{account}", self.limits.window_s) if account else 0
        if account is not None and failures >= self.limits.max_failures:
            self._locks[account] = self._clock() + self.limits.lockout_s
            self._counts.pop(f"acct:{account}", None)
            return True
        return False

    def clear(self, account: str) -> None:
        self._counts.pop(f"acct:{account}", None)
        self._locks.pop(account, None)

    def reset_requests(self, account: str) -> int:
        return self._incr(f"reset:{account}", 3600)
