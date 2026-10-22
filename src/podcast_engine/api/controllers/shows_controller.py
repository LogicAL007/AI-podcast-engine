"""HTTP-facing orchestration for shows: calls the service, maps its errors to HTTP."""

from uuid import UUID

from podcast_engine.api.errors import http_errors
from podcast_engine.api.models.pagination_model import Paged
from podcast_engine.api.models.shows_model import ShowCreate, ShowRead, ShowUpdate
from podcast_engine.api.services.shows_service import ShowService


class ShowController:
    def __init__(self, service: ShowService) -> None:
        self._service = service

    def create(self, data: ShowCreate, owner: UUID) -> ShowRead:
        return http_errors(lambda: self._service.create(data, owner))

    def get(self, show_id: UUID, owner: UUID) -> ShowRead:
        return http_errors(lambda: self._service.get(show_id, owner))

    def list_page(self, owner: UUID, *, limit: int, offset: int) -> Paged[ShowRead]:
        return http_errors(lambda: self._service.list_page(owner, limit=limit, offset=offset))

    def update(self, show_id: UUID, owner: UUID, data: ShowUpdate) -> ShowRead:
        return http_errors(lambda: self._service.update(show_id, owner, data))

    def delete(self, show_id: UUID, owner: UUID) -> None:
        http_errors(lambda: self._service.delete(show_id, owner))
