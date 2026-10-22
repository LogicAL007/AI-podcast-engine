"""HTTP-facing orchestration for uploads: calls the service, maps its errors to HTTP."""

from uuid import UUID

from podcast_engine.api.errors import http_errors
from podcast_engine.api.models.pagination_model import Paged
from podcast_engine.api.models.uploads_model import UploadContent, UploadRead
from podcast_engine.api.services.uploads_service import UploadService


class UploadController:
    def __init__(self, service: UploadService) -> None:
        self._service = service

    @property
    def max_bytes(self) -> int:
        return self._service.max_bytes

    def add(self, show_id: UUID, owner: UUID, *, filename: str, data: bytes) -> UploadRead:
        return http_errors(lambda: self._service.add(show_id, owner, filename=filename, data=data))

    def get(self, show_id: UUID, upload_id: UUID, owner: UUID) -> UploadRead:
        return http_errors(lambda: self._service.get(show_id, upload_id, owner))

    def get_file(self, show_id: UUID, upload_id: UUID) -> UploadContent:
        return http_errors(lambda: self._service.get_file(show_id, upload_id))

    def list_for_show(
        self, show_id: UUID, owner: UUID, *, limit: int, offset: int
    ) -> Paged[UploadRead]:
        return http_errors(
            lambda: self._service.list_for_show(show_id, owner, limit=limit, offset=offset)
        )

    def delete(self, show_id: UUID, upload_id: UUID, owner: UUID) -> None:
        http_errors(lambda: self._service.delete(show_id, upload_id, owner))
