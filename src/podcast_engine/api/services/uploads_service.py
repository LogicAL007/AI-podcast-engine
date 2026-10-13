"""Business rules for uploaded sources. No HTTP and no SQL in here."""

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
    """The base name without path parts, control characters or quotes (it ends up in headers)."""
    base = PurePosixPath(filename.replace("\\", "/")).name
    cleaned = "".join(ch for ch in base if ch.isprintable() and ch not in '"\\;')
    return cleaned.strip()[:255] or "upload.pdf"


def upload_key(show_id: UUID, upload_id: UUID) -> str:
    """Object key of an uploaded file. Uploads are private: only the API serves them."""
    return f"uploads/{show_id}/{upload_id}.pdf"


class UploadService:
    def __init__(
        self,
        uploads: UploadRepository,
        shows: ShowRepository,
        store: ObjectStore,
        *,
        max_bytes: int,
    ) -> None:
        self._uploads = uploads
        self._shows = shows
        self._store = store
        self.max_bytes = max_bytes

    def add(self, show_id: UUID, *, filename: str, data: bytes) -> UploadRead:
        """Store a PDF as a source for the show's next episode.

        The type is checked from the file's first bytes, not from the name or the type the client
        claims. Larger files than the limit are refused before anything is stored.
        """
        self._show(show_id)
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

    def get(self, show_id: UUID, upload_id: UUID) -> UploadRead:
        upload = self._uploads.get(show_id, upload_id)
        if upload is None:
            raise NotFoundError("upload", upload_id)
        return upload

    def get_file(self, show_id: UUID, upload_id: UUID) -> UploadContent:
        upload = self.get(show_id, upload_id)
        if not self._store.exists(upload.object_key):
            raise NotFoundError("file of upload", upload_id)
        return UploadContent(
            filename=upload.filename,
            content_type=upload.content_type,
            data=self._store.get(upload.object_key),
        )

    def list_for_show(self, show_id: UUID, *, limit: int, offset: int) -> Paged[UploadRead]:
        self._show(show_id)
        return self._uploads.list_page(show_id, limit=limit, offset=offset)

    def delete(self, show_id: UUID, upload_id: UUID) -> None:
        """Remove the upload and its file. Its sections leave the show at the next ingest."""
        upload = self.get(show_id, upload_id)
        self._uploads.delete(show_id, upload_id)
        self._store.delete(upload.object_key)

    def _show(self, show_id: UUID) -> None:
        if self._shows.get(show_id) is None:
            raise NotFoundError("show", show_id)
