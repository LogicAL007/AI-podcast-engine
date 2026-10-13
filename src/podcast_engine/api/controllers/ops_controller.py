"""HTTP-facing orchestration for liveness and readiness."""

from podcast_engine import __version__
from podcast_engine.api.models.ops_model import Health, Readiness
from podcast_engine.api.services.ops_service import OpsService


class OpsController:
    def __init__(self, service: OpsService) -> None:
        self._service = service

    def health(self) -> Health:
        return Health(status="ok", version=__version__)

    def readiness(self) -> Readiness:
        return self._service.readiness()
