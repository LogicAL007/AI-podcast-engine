"""Persistence for cloned voices: the only module that knows the ``voices`` table."""

import json
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from podcast_engine.api.models.pagination_model import Paged
from podcast_engine.api.models.voices_model import VoiceRead

_COLUMNS = (
    "voice_id, name, speaker, license, source, duration_seconds, consent, object_key, created_at"
)


class VoiceRepository(Protocol):
    """Every method is scoped to one owner: another user's voice does not exist for them."""

    def add(self, owner_id: UUID, values: dict[str, Any]) -> VoiceRead: ...

    def get(self, voice_id: UUID, owner_id: UUID) -> VoiceRead | None: ...

    def list_page(self, owner_id: UUID, *, limit: int, offset: int) -> Paged[VoiceRead]: ...

    def count(self, owner_id: UUID) -> int: ...

    def owned(self, voice_ids: set[UUID], owner_id: UUID) -> set[UUID]: ...

    def delete(self, voice_id: UUID, owner_id: UUID) -> bool: ...

    def object_keys(self, owner_id: UUID) -> list[str]: ...


class PostgresVoiceRepository:
    """Each write commits on its own."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, owner_id: UUID, values: dict[str, Any]) -> VoiceRead:
        row = (
            self._session.execute(
                text(
                    "INSERT INTO voices (voice_id, owner_id, name, speaker, license, source,"  # noqa: S608
                    " consent, object_key, size_bytes, duration_seconds, sha256) VALUES"
                    " (:voice_id, :owner_id, :name, :speaker, :license, :source,"
                    " CAST(:consent AS jsonb), :object_key, :size_bytes, :duration_seconds,"
                    f" :sha256) RETURNING {_COLUMNS}"
                ),
                {**values, "owner_id": owner_id, "consent": json.dumps(values["consent"])},
            )
            .mappings()
            .one()
        )
        self._session.commit()
        return VoiceRead.model_validate(row)

    def get(self, voice_id: UUID, owner_id: UUID) -> VoiceRead | None:
        row = (
            self._session.execute(
                text(
                    f"SELECT {_COLUMNS} FROM voices"  # noqa: S608 - constant column list
                    " WHERE voice_id = :id AND owner_id = :owner_id"
                ),
                {"id": voice_id, "owner_id": owner_id},
            )
            .mappings()
            .one_or_none()
        )
        return VoiceRead.model_validate(row) if row else None

    def list_page(self, owner_id: UUID, *, limit: int, offset: int) -> Paged[VoiceRead]:
        rows = self._session.execute(
            text(
                f"SELECT {_COLUMNS} FROM voices WHERE owner_id = :owner_id"  # noqa: S608
                " ORDER BY created_at DESC, voice_id LIMIT :limit OFFSET :offset"
            ),
            {"owner_id": owner_id, "limit": limit, "offset": offset},
        ).mappings()
        items = [VoiceRead.model_validate(row) for row in rows]
        return Paged(items, self.count(owner_id))

    def count(self, owner_id: UUID) -> int:
        return int(
            self._session.execute(
                text("SELECT count(*) FROM voices WHERE owner_id = :owner_id"),
                {"owner_id": owner_id},
            ).scalar_one()
        )

    def owned(self, voice_ids: set[UUID], owner_id: UUID) -> set[UUID]:
        if not voice_ids:
            return set()
        rows = self._session.execute(
            text("SELECT voice_id FROM voices WHERE owner_id = :owner_id AND voice_id = ANY(:ids)"),
            {"owner_id": owner_id, "ids": list(voice_ids)},
        ).scalars()
        return set(rows)

    def delete(self, voice_id: UUID, owner_id: UUID) -> bool:
        """Remove the voice, and take it off every host of the owner's shows that used it."""
        self._session.execute(
            text(
                "UPDATE shows SET host_voices = (SELECT coalesce(jsonb_object_agg(k, v), '{}')"
                " FROM jsonb_each(host_voices) AS e(k, v) WHERE v <> to_jsonb(CAST(:id AS text)))"
                " WHERE owner_id = :owner_id"
            ),
            {"id": str(voice_id), "owner_id": owner_id},
        )
        result = self._session.execute(
            text("DELETE FROM voices WHERE voice_id = :id AND owner_id = :owner_id"),
            {"id": voice_id, "owner_id": owner_id},
        )
        self._session.commit()
        return bool(result.rowcount)  # type: ignore[attr-defined]

    def object_keys(self, owner_id: UUID) -> list[str]:
        rows = self._session.execute(
            text("SELECT object_key FROM voices WHERE owner_id = :owner_id"),
            {"owner_id": owner_id},
        ).scalars()
        return list(rows)
