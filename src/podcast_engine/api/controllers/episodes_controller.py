"""HTTP-facing orchestration for episodes: calls the service, maps its errors to HTTP."""

from uuid import UUID

from podcast_engine.api.errors import DomainError, to_http
from podcast_engine.api.models.episodes_model import EpisodeRead
from podcast_engine.api.services.episodes_service import EpisodeService


class EpisodeController:
    def __init__(self, service: EpisodeService) -> None:
        self._service = service

    def start(self, show_id: UUID) -> EpisodeRead:
        try:
            return self._service.start(show_id)
        except DomainError as error:
            raise to_http(error) from error

    def get(self, episode_id: UUID) -> EpisodeRead:
        try:
            return self._service.get(episode_id)
        except DomainError as error:
            raise to_http(error) from error

    def list_for_show(self, show_id: UUID, *, limit: int, offset: int) -> list[EpisodeRead]:
        try:
            return self._service.list_for_show(show_id, limit=limit, offset=offset)
        except DomainError as error:
            raise to_http(error) from error
