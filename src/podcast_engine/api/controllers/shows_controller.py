"""HTTP-facing orchestration for shows: calls the service, maps its errors to HTTP."""

from uuid import UUID

from podcast_engine.api.errors import NotFoundError, to_http
from podcast_engine.api.models.pagination_model import Paged
from podcast_engine.api.models.shows_model import ShowCreate, ShowRead, ShowUpdate
from podcast_engine.api.services.shows_service import ShowService


class ShowController:
    def __init__(self, service: ShowService) -> None:
        self._service = service

    def create(self, data: ShowCreate) -> ShowRead:
        return self._service.create(data)

    def get(self, show_id: UUID) -> ShowRead:
        try:
            return self._service.get(show_id)
        except NotFoundError as error:
            raise to_http(error) from error

    def list_page(self, *, limit: int, offset: int) -> Paged[ShowRead]:
        return self._service.list_page(limit=limit, offset=offset)

    def update(self, show_id: UUID, data: ShowUpdate) -> ShowRead:
        try:
            return self._service.update(show_id, data)
        except NotFoundError as error:
            raise to_http(error) from error

    def delete(self, show_id: UUID) -> None:
        try:
            self._service.delete(show_id)
        except NotFoundError as error:
            raise to_http(error) from error
