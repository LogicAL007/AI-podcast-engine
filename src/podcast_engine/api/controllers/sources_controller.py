"""HTTP-facing orchestration for sources: calls the service, maps its errors to HTTP."""

from uuid import UUID

from podcast_engine.api.errors import DomainError, to_http
from podcast_engine.api.models.pagination_model import Paged
from podcast_engine.api.models.sources_model import SourceRead
from podcast_engine.api.services.sources_service import SourceService


class SourceController:
    def __init__(self, service: SourceService) -> None:
        self._service = service

    def list_for_show(self, show_id: UUID, *, limit: int, offset: int) -> Paged[SourceRead]:
        try:
            return self._service.list_for_show(show_id, limit=limit, offset=offset)
        except DomainError as error:
            raise to_http(error) from error
