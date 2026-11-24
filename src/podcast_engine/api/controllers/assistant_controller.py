from podcast_engine.api.errors import http_errors
from podcast_engine.api.models.assistant_model import Answer, Question
from podcast_engine.api.models.auth_model import CurrentUser
from podcast_engine.api.services.assistant_service import AssistantService


class AssistantController:
    """HTTP-facing entry point for the assistant: calls the service and maps its errors to HTTP."""

    def __init__(self, service: AssistantService) -> None:
        """Create the controller.

        Args:
            service: The assistant service that answers questions.
        """
        self._service = service

    def ask(self, user: CurrentUser, question: Question) -> Answer:
        """Answer a signed-in user's question about the app.

        Args:
            user: The signed-in user asking.
            question: The question and the page it was asked from.

        Returns:
            The assistant's answer.

        Raises:
            HTTPException: The service's domain errors, mapped to HTTP status codes.
        """
        return http_errors(lambda: self._service.ask(user, question))
