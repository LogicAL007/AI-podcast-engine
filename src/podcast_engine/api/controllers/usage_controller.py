from podcast_engine.api.models.usage_model import UsageRead
from podcast_engine.api.services.usage_service import UsageService


class UsageController:
    """HTTP-facing entry point for today's Gemini usage."""

    def __init__(self, service: UsageService) -> None:
        """Create the controller.

        Args:
            service: The usage service that reads today's counters.
        """
        self._service = service

    def today(self) -> UsageRead:
        """Report today's Gemini usage.

        Returns:
            Requests used and left today, per model and kind.
        """
        return self._service.today()
