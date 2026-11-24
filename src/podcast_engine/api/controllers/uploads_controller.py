from uuid import UUID

from podcast_engine.api.errors import http_errors
from podcast_engine.api.models.pagination_model import Paged
from podcast_engine.api.models.uploads_model import UploadContent, UploadRead
from podcast_engine.api.services.uploads_service import UploadService


class UploadController:
    """HTTP-facing entry point for uploads: calls the service and maps its errors to HTTP."""

    def __init__(self, service: UploadService) -> None:
        """Create the controller.

        Args:
            service: The upload service holding the rules for source files.
        """
        self._service = service

    @property
    def max_bytes(self) -> int:
        """Largest upload accepted, in bytes."""
        return self._service.max_bytes

    def add(self, show_id: UUID, owner: UUID, *, filename: str, data: bytes) -> UploadRead:
        """Store a file as a source of one of the caller's shows.

        Args:
            show_id: The show the file belongs to.
            owner: The signed-in user.
            filename: The name the file was uploaded with.
            data: The file's bytes.

        Returns:
            The stored upload.

        Raises:
            HTTPException: The service's domain errors, mapped to HTTP status codes.
        """
        return http_errors(lambda: self._service.add(show_id, owner, filename=filename, data=data))

    def get(self, show_id: UUID, upload_id: UUID, owner: UUID) -> UploadRead:
        """Return one upload's details.

        Args:
            show_id: The show it belongs to.
            upload_id: The upload to return.
            owner: The signed-in user.

        Returns:
            The upload's name, type, size and links.

        Raises:
            HTTPException: The service's domain errors, mapped to HTTP status codes.
        """
        return http_errors(lambda: self._service.get(show_id, upload_id, owner))

    def get_file(self, show_id: UUID, upload_id: UUID) -> UploadContent:
        """Return an upload's bytes, for downloading.

        Public, because show notes cite it, so not scoped to an owner: the ids are the secret.

        Args:
            show_id: The show it belongs to.
            upload_id: The upload to return.

        Returns:
            The file's name, media type and bytes.

        Raises:
            HTTPException: The service's domain errors, mapped to HTTP status codes.
        """
        return http_errors(lambda: self._service.get_file(show_id, upload_id))

    def list_for_show(
        self, show_id: UUID, owner: UUID, *, limit: int, offset: int
    ) -> Paged[UploadRead]:
        """Return one page of a show's uploads.

        Args:
            show_id: The show whose uploads to list.
            owner: The signed-in user.
            limit: Most uploads to return.
            offset: Uploads to skip before this page.

        Returns:
            The page of uploads and the total across all pages.

        Raises:
            HTTPException: The service's domain errors, mapped to HTTP status codes.
        """
        return http_errors(
            lambda: self._service.list_for_show(show_id, owner, limit=limit, offset=offset)
        )

    def delete(self, show_id: UUID, upload_id: UUID, owner: UUID) -> None:
        """Delete an upload and its file.

        Args:
            show_id: The show it belongs to.
            upload_id: The upload to delete.
            owner: The signed-in user.

        Raises:
            HTTPException: The service's domain errors, mapped to HTTP status codes.
        """
        http_errors(lambda: self._service.delete(show_id, upload_id, owner))
