from pathlib import PurePosixPath
from uuid import UUID, uuid4

from podcast_engine.api.errors import (
    NotFoundError,
    PayloadTooLargeError,
    UnsupportedMediaTypeError,
)
from podcast_engine.api.models.pagination_model import Paged
from podcast_engine.api.models.uploads_model import PDF_MEDIA_TYPE, UploadContent, UploadRead
from podcast_engine.api.repositories.shows_repository import ShowRepository
from podcast_engine.api.repositories.uploads_repository import UploadRepository
from podcast_engine.common.storage import ObjectStore

PDF_MAGIC = b"%PDF-"


def safe_filename(filename: str) -> str:
    """Clean an uploaded file's name for storage and headers.

    Keeps the base name only, without path parts, control characters, quotes, backslashes or
    semicolons, cut to 255 characters.

    Args:
        filename: The name the client sent.

    Returns:
        The cleaned name, or ``upload.pdf`` when nothing is left.
    """
    base = PurePosixPath(filename.replace("\\", "/")).name
    cleaned = "".join(ch for ch in base if ch.isprintable() and ch not in '"\\;')
    return cleaned.strip()[:255] or "upload.pdf"


def upload_key(show_id: UUID, upload_id: UUID) -> str:
    """Return the object key of an uploaded file.

    Uploads are private: only the API serves them.

    Args:
        show_id: The show it belongs to.
        upload_id: The upload.

    Returns:
        The file's key in object storage.
    """
    return f"uploads/{show_id}/{upload_id}.pdf"


class UploadService:
    """Business rules for uploaded sources. No HTTP and no SQL in here."""

    def __init__(
        self,
        uploads: UploadRepository,
        shows: ShowRepository,
        store: ObjectStore,
        *,
        max_bytes: int,
    ) -> None:
        """Create the service.

        Args:
            uploads: Where upload details are stored.
            shows: Where shows are stored, to check ownership.
            store: Where the files are stored.
            max_bytes: The largest file accepted.
        """
        self._uploads = uploads
        self._shows = shows
        self._store = store
        self.max_bytes = max_bytes

    def add(self, show_id: UUID, owner: UUID, *, filename: str, data: bytes) -> UploadRead:
        """Store a PDF as a source for the show's next episode.

        The type is checked from the file's first bytes, not from the name or the type the client
        claims. Files larger than the limit are refused before anything is stored.

        Args:
            show_id: The show to add it to.
            owner: The user uploading.
            filename: The name it was uploaded with.
            data: The file's bytes.

        Returns:
            The stored upload.

        Raises:
            NotFoundError: The show is not the owner's.
            PayloadTooLargeError: The file is larger than the limit.
            UnsupportedMediaTypeError: The file is not a PDF.
        """
        self._show(show_id, owner)
        if len(data) > self.max_bytes:
            raise PayloadTooLargeError(
                f"the file is larger than {self.max_bytes // (1024 * 1024)} MB"
            )
        if not data.startswith(PDF_MAGIC):
            raise UnsupportedMediaTypeError("only PDF files can be uploaded")
        upload_id = uuid4()
        key = upload_key(show_id, upload_id)
        self._store.put(key, data, PDF_MEDIA_TYPE)
        name = safe_filename(filename)
        return self._uploads.add(
            upload_id=upload_id,
            show_id=show_id,
            filename=name,
            content_type=PDF_MEDIA_TYPE,
            size_bytes=len(data),
            object_key=key,
        )

    def get(self, show_id: UUID, upload_id: UUID, owner: UUID) -> UploadRead:
        """Return one of the owner's uploads.

        Args:
            show_id: The show it belongs to.
            upload_id: The upload to return.
            owner: The user asking.

        Returns:
            The upload.

        Raises:
            NotFoundError: The show is not the owner's, or has no such upload.
        """
        self._show(show_id, owner)
        return self._find(show_id, upload_id)

    def _find(self, show_id: UUID, upload_id: UUID) -> UploadRead:
        """Return one of a show's uploads, whoever owns the show.

        Args:
            show_id: The show it belongs to.
            upload_id: The upload to return.

        Returns:
            The upload.

        Raises:
            NotFoundError: The show has no such upload.
        """
        upload = self._uploads.get(show_id, upload_id)
        if upload is None:
            raise NotFoundError("upload", upload_id)
        return upload

    def get_file(self, show_id: UUID, upload_id: UUID) -> UploadContent:
        """Return an upload's file for downloading.

        Public, because show notes cite it, so not scoped to an owner: the ids are the secret.

        Args:
            show_id: The show it belongs to.
            upload_id: The upload.

        Returns:
            The file's name, media type and bytes.

        Raises:
            NotFoundError: There is no such upload, or its file is missing from storage.
        """
        upload = self._find(show_id, upload_id)
        if not self._store.exists(upload.object_key):
            raise NotFoundError("file of upload", upload_id)
        return UploadContent(
            filename=upload.filename,
            content_type=upload.content_type,
            data=self._store.get(upload.object_key),
        )

    def list_for_show(
        self, show_id: UUID, owner: UUID, *, limit: int, offset: int
    ) -> Paged[UploadRead]:
        """Return one page of the owner's uploads for a show.

        Args:
            show_id: The show whose uploads to list.
            owner: The user asking.
            limit: Most uploads to return.
            offset: Uploads to skip before this page.

        Returns:
            The page of uploads, newest first, and the total.

        Raises:
            NotFoundError: The show is not the owner's.
        """
        self._show(show_id, owner)
        return self._uploads.list_page(show_id, limit=limit, offset=offset)

    def delete(self, show_id: UUID, upload_id: UUID, owner: UUID) -> None:
        """Remove an upload and its file.

        Its sections leave the show at the next ingest.

        Args:
            show_id: The show it belongs to.
            upload_id: The upload to delete.
            owner: The user asking.

        Raises:
            NotFoundError: The show is not the owner's, or has no such upload.
        """
        upload = self.get(show_id, upload_id, owner)
        self._uploads.delete(show_id, upload_id)
        self._store.delete(upload.object_key)

    def _show(self, show_id: UUID, owner: UUID) -> None:
        """Check that the show exists and belongs to the owner.

        Args:
            show_id: The show.
            owner: The user asking.

        Raises:
            NotFoundError: The show is not the owner's or does not exist.
        """
        if self._shows.get(show_id, owner) is None:
            raise NotFoundError("show", show_id)
