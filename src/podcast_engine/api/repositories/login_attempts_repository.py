import hashlib
import time
from collections.abc import Callable
from typing import Any, Protocol

from podcast_engine.common.logging import get_logger

log = get_logger("api.login_attempts")


def account_key(email: str) -> str:
    """Key an account by a hash of its lower-cased email.

    Redis never holds the address, and an unknown email is counted the same as a real one, so a lock
    never reveals whether an account exists.

    Args:
        email: The email typed at sign-in.

    Returns:
        The SHA-256 hex digest.
    """
    return hashlib.sha256(email.strip().lower().encode()).hexdigest()


class LoginAttempts(Protocol):
    """Failed-login and reset-request counters.

    Following OWASP's authentication guidance, failures are counted per account (so spreading
    guesses over many addresses does not help) and per address (so one address cannot sweep many
    accounts). An account's lock is temporary.
    """

    def account_locked(self, account: str) -> bool:
        """Tell whether an account is locked.

        Args:
            account: The account's key, from ``account_key``.

        Returns:
            True while the account is locked.
        """
        ...

    def address_retry_after(self, address: str) -> int:
        """Seconds until an address may try to sign in again.

        Args:
            address: The client's IP address.

        Returns:
            Seconds until the address may try again; 0 if it may now.
        """
        ...

    def record_failure(self, account: str | None, address: str) -> bool:
        """Count a failed sign-in.

        Args:
            account: The account's key, or None when the email matched nothing worth counting.
            address: The client's IP address.

        Returns:
            True if this failure just locked the account.
        """
        ...

    def clear(self, account: str) -> None:
        """Forget an account's failures and lock, after a successful sign-in or reset.

        Args:
            account: The account's key, from ``account_key``.
        """
        ...

    def reset_requests(self, account: str) -> int:
        """Count one more password reset request for the account this hour.

        Args:
            account: The account's key, from ``account_key``.

        Returns:
            The number of reset requests this hour, this one included.
        """
        ...


class LimitsConfig:
    """The sign-in limits: failures allowed, the counting window and the lockout."""

    def __init__(
        self,
        *,
        max_failures: int,
        address_max_failures: int,
        window_s: int,
        lockout_s: int,
        reset_max: int,
    ) -> None:
        """Create the limits.

        Args:
            max_failures: Failures that lock an account.
            address_max_failures: Failures after which an address must wait.
            window_s: How long failures are counted, in seconds.
            lockout_s: How long a locked account stays locked.
            reset_max: Password reset requests allowed per account per hour.
        """
        self.max_failures = max_failures
        self.address_max_failures = address_max_failures
        self.window_s = window_s
        self.lockout_s = lockout_s
        self.reset_max = reset_max


class RedisLoginAttempts:
    """Fixed-window counters with expiry in Redis, shared by every API process.

    If Redis is unreachable, logins are not limited (and the failure is logged): an outage of the
    counters should not lock everyone out.
    """

    def __init__(self, client: Any, limits: LimitsConfig) -> None:
        """Create the counters.

        Args:
            client: A Redis client.
            limits: The sign-in limits.
        """
        self._redis = client
        self.limits = limits

    def _safe[T](self, default: T, call: Callable[[], T]) -> T:
        """Run a Redis call, failing open (and loudly) when Redis errs.

        Args:
            default: What to return when Redis is unavailable.
            call: The Redis call.

        Returns:
            The call's result, or the default.
        """
        try:
            return call()
        except Exception:
            log.exception("login_limits_unavailable")
            return default

    def account_locked(self, account: str) -> bool:
        """Tell whether an account is locked.

        Args:
            account: The account's key, from ``account_key``.

        Returns:
            True while the account is locked.
        """
        return self._safe(False, lambda: bool(self._redis.exists(f"login:lock:{account}")))

    def address_retry_after(self, address: str) -> int:
        """Seconds until an address may try to sign in again.

        Args:
            address: The client's IP address.

        Returns:
            Seconds until the address may try again; 0 if it may now.
        """

        def check() -> int:
            """Read the address's failure count and, when over the limit, its window's time left.

            Returns:
                The seconds to wait, or 0.
            """
            count = int(self._redis.get(f"login:fail:addr:{address}") or 0)
            if count < self.limits.address_max_failures:
                return 0
            return max(int(self._redis.ttl(f"login:fail:addr:{address}")), 1)

        return self._safe(0, check)

    def record_failure(self, account: str | None, address: str) -> bool:
        """Count a failed sign-in for the address and the account.

        When the account reaches the limit it is locked for the lockout time and its count starts
        again.

        Args:
            account: The account's key, or None when the email matched nothing worth counting.
            address: The client's IP address.

        Returns:
            True if this failure just locked the account.
        """

        def record() -> bool:
            """Increment both counters in one pipeline and lock the account when needed.

            Returns:
                True if the account was just locked.
            """
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
        """Forget an account's failures and lock.

        Args:
            account: The account's key, from ``account_key``.
        """
        self._safe(
            None, lambda: self._redis.delete(f"login:fail:acct:{account}", f"login:lock:{account}")
        )

    def reset_requests(self, account: str) -> int:
        """Count one more password reset request for the account this hour.

        Args:
            account: The account's key, from ``account_key``.

        Returns:
            The number of reset requests this hour, this one included.
        """

        def count() -> int:
            """Increment the account's hourly reset counter.

            Returns:
                The count this hour.
            """
            pipe = self._redis.pipeline()
            pipe.incr(f"reset:req:{account}")
            pipe.expire(f"reset:req:{account}", 3600, nx=True)
            return int(pipe.execute()[0])

        return self._safe(0, count)


class MemoryLoginAttempts:
    """The same rules in memory, with a clock tests control.

    Each counter is stored as (count, expires at).
    """

    def __init__(self, limits: LimitsConfig, clock: Callable[[], float] = time.monotonic) -> None:
        """Create the counters.

        Args:
            limits: The sign-in limits.
            clock: Returns the current time in seconds; replaced in tests.
        """
        self.limits = limits
        self._clock = clock
        self._counts: dict[str, tuple[int, float]] = {}
        self._locks: dict[str, float] = {}

    def _get(self, key: str) -> tuple[int, float]:
        """Read a counter, treating an expired one as zero.

        Args:
            key: The counter's key.

        Returns:
            The count and when it expires.
        """
        count, expires = self._counts.get(key, (0, 0.0))
        return (count, expires) if expires > self._clock() else (0, 0.0)

    def _incr(self, key: str, ttl: float) -> int:
        """Add one to a counter, starting its window if it has none.

        Args:
            key: The counter's key.
            ttl: The window's length, in seconds.

        Returns:
            The new count.
        """
        count, expires = self._get(key)
        self._counts[key] = (count + 1, expires or self._clock() + ttl)
        return count + 1

    def account_locked(self, account: str) -> bool:
        """Tell whether an account is locked.

        Args:
            account: The account's key, from ``account_key``.

        Returns:
            True while the account is locked.
        """
        return self._locks.get(account, 0.0) > self._clock()

    def address_retry_after(self, address: str) -> int:
        """Seconds until an address may try to sign in again.

        Args:
            address: The client's IP address.

        Returns:
            Seconds until the address may try again; 0 if it may now.
        """
        count, expires = self._get(f"addr:{address}")
        if count < self.limits.address_max_failures:
            return 0
        return max(int(expires - self._clock()), 1)

    def record_failure(self, account: str | None, address: str) -> bool:
        """Count a failed sign-in for the address and the account.

        Args:
            account: The account's key, or None when the email matched nothing worth counting.
            address: The client's IP address.

        Returns:
            True if this failure just locked the account.
        """
        self._incr(f"addr:{address}", self.limits.window_s)
        failures = self._incr(f"acct:{account}", self.limits.window_s) if account else 0
        if account is not None and failures >= self.limits.max_failures:
            self._locks[account] = self._clock() + self.limits.lockout_s
            self._counts.pop(f"acct:{account}", None)
            return True
        return False

    def clear(self, account: str) -> None:
        """Forget an account's failures and lock.

        Args:
            account: The account's key, from ``account_key``.
        """
        self._counts.pop(f"acct:{account}", None)
        self._locks.pop(account, None)

    def reset_requests(self, account: str) -> int:
        """Count one more password reset request for the account this hour.

        Args:
            account: The account's key, from ``account_key``.

        Returns:
            The number of reset requests this hour, this one included.
        """
        return self._incr(f"reset:{account}", 3600)
