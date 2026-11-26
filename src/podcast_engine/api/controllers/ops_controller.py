from podcast_engine import __version__
from podcast_engine.api.models.ops_model import Health, Readiness
from podcast_engine.api.services.ops_service import OpsService


class OpsController:
    """HTTP-facing entry point for liveness and readiness checks."""

    def __init__(self, service: OpsService) -> None:
        """Create the controller.

        Args:
            service: The service that checks the API's dependencies.
        """
        self._service = service

    def health(self) -> Health:
        """Report that the process is serving requests.

        Returns:
            Status ``ok`` and the API version.
        """
        return Health(status="ok", version=__version__)

    def readiness(self) -> Readiness:
        """Report whether every dependency the API needs is reachable.

        Returns:
            ``ready`` or ``not ready``, with the result of each check.
        """
        return self._service.readiness()
