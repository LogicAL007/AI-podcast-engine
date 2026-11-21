"""Persistence for type-to-speech clips: the only API module that knows ``speech_clips``."""

import json
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from podcast_engine.api.models.speech_model import SpeechClipRead

_COLUMNS = (
    "clip_id, voice, text, delivery, effects, status, duration_s, error, created_at, finished_at"
)


class SpeechRepository(Protocol):
    """Every method is scoped to one owner: another user's clip does not exist for them."""

    def add(self, owner_id: UUID, values: dict[str, Any]) -> SpeechClipRead: ...

    def get(self, clip_id: UUID, owner_id: UUID) -> SpeechClipRead | None: ...

    def recent(self, owner_id: UUID, limit: int) -> list[SpeechClipRead]: ...

    def object_key(self, clip_id: UUID, owner_id: UUID) -> str | None: ...

    def fail(self, clip_id: UUID, error: str) -> None: ...

    def delete(self, clip_id: UUID, owner_id: UUID) -> bool: ...

    def object_keys(self, owner_id: UUID) -> list[str]: ...


class PostgresSpeechRepository:
    """Each write commits on its own."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, owner_id: UUID, values: dict[str, Any]) -> SpeechClipRead:
        row = (
            self._session.execute(
                text(
                    "INSERT INTO speech_clips (clip_id, owner_id, voice, text, delivery, effects)"  # noqa: S608
                    " VALUES (:clip_id, :owner_id, CAST(:voice AS jsonb), :text, :delivery,"
                    f" CAST(:effects AS jsonb)) RETURNING {_COLUMNS}"
                ),
                {
                    **values,
                    "owner_id": owner_id,
                    "voice": json.dumps(values["voice"]),
                    "effects": json.dumps(values["effects"]),
                },
            )
            .mappings()
            .one()
        )
        self._session.commit()
        return SpeechClipRead.model_validate(row)

    def get(self, clip_id: UUID, owner_id: UUID) -> SpeechClipRead | None:
        row = (
            self._session.execute(
                text(
                    f"SELECT {_COLUMNS} FROM speech_clips"  # noqa: S608 - constant column list
                    " WHERE clip_id = :id AND owner_id = :owner_id"
                ),
                {"id": clip_id, "owner_id": owner_id},
            )
            .mappings()
            .one_or_none()
        )
        return SpeechClipRead.model_validate(row) if row else None

    def recent(self, owner_id: UUID, limit: int) -> list[SpeechClipRead]:
        rows = self._session.execute(
            text(
                f"SELECT {_COLUMNS} FROM speech_clips WHERE owner_id = :owner_id"  # noqa: S608
                " ORDER BY created_at DESC, clip_id LIMIT :limit"
            ),
            {"owner_id": owner_id, "limit": limit},
        ).mappings()
        return [SpeechClipRead.model_validate(row) for row in rows]

    def object_key(self, clip_id: UUID, owner_id: UUID) -> str | None:
        return self._session.execute(
            text(
                "SELECT object_key FROM speech_clips WHERE clip_id = :id AND owner_id = :owner_id"
            ),
            {"id": clip_id, "owner_id": owner_id},
        ).scalar_one_or_none()

    def fail(self, clip_id: UUID, error: str) -> None:
        self._session.execute(
            text(
                "UPDATE speech_clips SET status = 'failed', error = :error, finished_at = now()"
                " WHERE clip_id = :id AND status = 'queued'"
            ),
            {"id": clip_id, "error": error},
        )
        self._session.commit()

    def delete(self, clip_id: UUID, owner_id: UUID) -> bool:
        result = self._session.execute(
            text("DELETE FROM speech_clips WHERE clip_id = :id AND owner_id = :owner_id"),
            {"id": clip_id, "owner_id": owner_id},
        )
        self._session.commit()
        return bool(result.rowcount)  # type: ignore[attr-defined]

    def object_keys(self, owner_id: UUID) -> list[str]:
        rows = self._session.execute(
            text(
                "SELECT object_key FROM speech_clips"
                " WHERE owner_id = :owner_id AND object_key IS NOT NULL"
            ),
            {"owner_id": owner_id},
        ).scalars()
        return list(rows)
