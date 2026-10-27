"""HTTP-facing orchestration for the assistant: calls the service, maps its errors to HTTP."""

from podcast_engine.api.errors import http_errors
from podcast_engine.api.models.assistant_model import Answer, Question
from podcast_engine.api.models.auth_model import CurrentUser
from podcast_engine.api.services.assistant_service import AssistantService


class AssistantController:
    def __init__(self, service: AssistantService) -> None:
        self._service = service

    def ask(self, user: CurrentUser, question: Question) -> Answer:
        return http_errors(lambda: self._service.ask(user, question))
