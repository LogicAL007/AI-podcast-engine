"""Persistence for uploads: the only module that knows the ``uploads`` table."""

from typing import Protocol
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from podcast_engine.api.models.pagination_model import Paged
from podcast_engine.api.models.uploads_model import UploadRead

_COLUMNS = "upload_id, show_id, filename, content_type, size_bytes, object_key, created_at"


class UploadRepository(Protocol):
    def add(
        self,
        *,
        upload_id: UUID,
        show_id: UUID,
        filename: str,
        content_type: str,
        size_bytes: int,
        object_key: str,
    ) -> UploadRead: ...

    def get(self, show_id: UUID, upload_id: UUID) -> UploadRead | None: ...

    def list_page(self, show_id: UUID, *, limit: int, offset: int) -> Paged[UploadRead]: ...

    def delete(self, show_id: UUID, upload_id: UUID) -> bool: ...


class PostgresUploadRepository:
    """Each write commits on its own."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(
        self,
        *,
        upload_id: UUID,
        show_id: UUID,
        filename: str,
        content_type: str,
        size_bytes: int,
        object_key: str,
    ) -> UploadRead:
        row = (
            self._session.execute(
                text(
                    "INSERT INTO uploads (upload_id, show_id, filename, content_type, size_bytes,"  # noqa: S608
                    " object_key) VALUES (:upload_id, :show_id, :filename, :content_type,"
                    f" :size_bytes, :object_key) RETURNING {_COLUMNS}"
                ),
                {
                    "upload_id": upload_id,
                    "show_id": show_id,
                    "filename": filename,
                    "content_type": content_type,
                    "size_bytes": size_bytes,
                    "object_key": object_key,
                },
            )
            .mappings()
            .one()
        )
        self._session.commit()
        return UploadRead.model_validate(row)

    def get(self, show_id: UUID, upload_id: UUID) -> UploadRead | None:
        row = (
            self._session.execute(
                text(
                    f"SELECT {_COLUMNS} FROM uploads"  # noqa: S608 - constant column list
                    " WHERE show_id = :show_id AND upload_id = :upload_id"
                ),
                {"show_id": show_id, "upload_id": upload_id},
            )
            .mappings()
            .one_or_none()
        )
        return UploadRead.model_validate(row) if row else None

    def list_page(self, show_id: UUID, *, limit: int, offset: int) -> Paged[UploadRead]:
        rows = self._session.execute(
            text(
                f"SELECT {_COLUMNS} FROM uploads WHERE show_id = :show_id"  # noqa: S608
                " ORDER BY created_at DESC, upload_id LIMIT :limit OFFSET :offset"
            ),
            {"show_id": show_id, "limit": limit, "offset": offset},
        ).mappings()
        items = [UploadRead.model_validate(row) for row in rows]
        total = self._session.execute(
            text("SELECT count(*) FROM uploads WHERE show_id = :show_id"), {"show_id": show_id}
        ).scalar_one()
        return Paged(items, int(total))

    def delete(self, show_id: UUID, upload_id: UUID) -> bool:
        result = self._session.execute(
            text("DELETE FROM uploads WHERE show_id = :show_id AND upload_id = :upload_id"),
            {"show_id": show_id, "upload_id": upload_id},
        )
        self._session.commit()
        return bool(result.rowcount)  # type: ignore[attr-defined]
