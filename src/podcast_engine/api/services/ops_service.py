import time
from collections.abc import Callable, Mapping

from podcast_engine.api.models.ops_model import Readiness
from podcast_engine.common.logging import get_logger

Check = Callable[[], None]

log = get_logger("api.ops")


class OpsService:
    """Readiness: whether the API's dependencies answer. No HTTP in here.

    Each check is a function that returns normally when its dependency answers and raises otherwise.
    """

    def __init__(self, checks: Mapping[str, Check]) -> None:
        """Create the service.

        Args:
            checks: Each dependency's name and the function that checks it.
        """
        self._checks = checks

    def readiness(self) -> Readiness:
        """Run every check and report whether the API is ready.

        Any exception from a check means not ready; the report says which check failed and why, with
        the error cut to 200 characters. Failures are logged as warnings.

        Returns:
            ``ready`` when every check passed, else ``not ready``, with each check's result.
        """
        results: dict[str, str] = {}
        for name, check in self._checks.items():
            started = time.perf_counter()
            try:
                check()
                results[name] = "ok"
            except Exception as error:
                results[name] = f"failed: {type(error).__name__}: {str(error)[:200]}"
                log.warning("readiness_check_failed", check=name, error=results[name])
            log.debug(
                "readiness_check", check=name, seconds=round(time.perf_counter() - started, 3)
            )
        ready = all(value == "ok" for value in results.values())
        return Readiness(status="ready" if ready else "not ready", checks=results)
