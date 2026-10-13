"""Readiness: whether the API's dependencies answer. No HTTP in here."""

import time
from collections.abc import Callable, Mapping

from podcast_engine.api.models.ops_model import Readiness
from podcast_engine.common.logging import get_logger

# A check returns normally when its dependency answers and raises otherwise.
Check = Callable[[], None]

log = get_logger("api.ops")


class OpsService:
    def __init__(self, checks: Mapping[str, Check]) -> None:
        self._checks = checks

    def readiness(self) -> Readiness:
        results: dict[str, str] = {}
        for name, check in self._checks.items():
            started = time.perf_counter()
            try:
                check()
                results[name] = "ok"
            except Exception as error:  # any failure means not ready; say which and why
                results[name] = f"failed: {type(error).__name__}: {str(error)[:200]}"
                log.warning("readiness_check_failed", check=name, error=results[name])
            log.debug(
                "readiness_check", check=name, seconds=round(time.perf_counter() - started, 3)
            )
        ready = all(value == "ok" for value in results.values())
        return Readiness(status="ready" if ready else "not ready", checks=results)
