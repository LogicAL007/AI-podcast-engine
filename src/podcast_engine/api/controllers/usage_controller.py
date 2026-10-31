"""HTTP-facing orchestration for today's Gemini usage."""

from podcast_engine.api.models.usage_model import UsageRead
from podcast_engine.api.services.usage_service import UsageService


class UsageController:
    def __init__(self, service: UsageService) -> None:
        self._service = service

    def today(self) -> UsageRead:
        return self._service.today()
