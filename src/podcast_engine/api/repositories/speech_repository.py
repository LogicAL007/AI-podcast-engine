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
    """Stores type-to-speech clips.

    Every method is scoped to one owner: another user's clip does not exist for them.
    """

    def add(self, owner_id: UUID, values: dict[str, Any]) -> SpeechClipRead:
        """Record a new clip, queued.

        Args:
            owner_id: The user making the clip.
            values: The clip's id, voice, text, delivery and effects.

        Returns:
            The queued clip.
        """
        ...

    def get(self, clip_id: UUID, owner_id: UUID) -> SpeechClipRead | None:
        """Return one of the user's clips.

        Args:
            clip_id: The clip.
            owner_id: The user asking.

        Returns:
            The clip, or None when the user has no such clip.
        """
        ...

    def recent(self, owner_id: UUID, limit: int) -> list[SpeechClipRead]:
        """Return the user's most recent clips.

        Args:
            owner_id: The user asking.
            limit: Most clips to return.

        Returns:
            The clips, newest first.
        """
        ...

    def object_key(self, clip_id: UUID, owner_id: UUID) -> str | None:
        """Return where a clip's audio is stored.

        Args:
            clip_id: The clip.
            owner_id: The user asking.

        Returns:
            Where the clip's audio is stored, or None when it has none yet.
        """
        ...

    def fail(self, clip_id: UUID, error: str) -> None:
        """Mark a still-queued clip as failed, such as when it could not be queued.

        Args:
            clip_id: The clip.
            error: Why it could not be queued.
        """
        ...

    def delete(self, clip_id: UUID, owner_id: UUID) -> bool:
        """Delete one of the user's clips.

        Args:
            clip_id: The clip.
            owner_id: The user asking.

        Returns:
            True if a clip was deleted.
        """
        ...

    def object_keys(self, owner_id: UUID) -> list[str]:
        """Return where every one of the user's clips is stored, to delete them all.

        Args:
            owner_id: The user.

        Returns:
            Where each of the user's clips' audio is stored.
        """
        ...


class PostgresSpeechRepository:
    """Clips in the ``speech_clips`` table, the only API code that knows it.

    Each write commits on its own.
    """

    def __init__(self, session: Session) -> None:
        """Create the repository.

        Args:
            session: The database session for this request.
        """
        self._session = session

    def add(self, owner_id: UUID, values: dict[str, Any]) -> SpeechClipRead:
        """Record a new clip, queued.

        Args:
            owner_id: The user making the clip.
            values: The clip's id, voice, text, delivery and effects.

        Returns:
            The queued clip.
        """
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
        """Return one of the user's clips.

        Args:
            clip_id: The clip.
            owner_id: The user asking.

        Returns:
            The clip, or None when the user has no such clip.
        """
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
        """Return the user's most recent clips.

        Args:
            owner_id: The user asking.
            limit: Most clips to return.

        Returns:
            The clips, newest first.
        """
        rows = self._session.execute(
            text(
                f"SELECT {_COLUMNS} FROM speech_clips WHERE owner_id = :owner_id"  # noqa: S608
                " ORDER BY created_at DESC, clip_id LIMIT :limit"
            ),
            {"owner_id": owner_id, "limit": limit},
        ).mappings()
        return [SpeechClipRead.model_validate(row) for row in rows]

    def object_key(self, clip_id: UUID, owner_id: UUID) -> str | None:
        """Return where a clip's audio is stored.

        Args:
            clip_id: The clip.
            owner_id: The user asking.

        Returns:
            Where the clip's audio is stored, or None when it has none yet.
        """
        return self._session.execute(
            text(
                "SELECT object_key FROM speech_clips WHERE clip_id = :id AND owner_id = :owner_id"
            ),
            {"id": clip_id, "owner_id": owner_id},
        ).scalar_one_or_none()

    def fail(self, clip_id: UUID, error: str) -> None:
        """Mark a still-queued clip as failed, such as when it could not be queued.

        Args:
            clip_id: The clip.
            error: Why it could not be queued.
        """
        self._session.execute(
            text(
                "UPDATE speech_clips SET status = 'failed', error = :error, finished_at = now()"
                " WHERE clip_id = :id AND status = 'queued'"
            ),
            {"id": clip_id, "error": error},
        )
        self._session.commit()

    def delete(self, clip_id: UUID, owner_id: UUID) -> bool:
        """Delete one of the user's clips.

        Args:
            clip_id: The clip.
            owner_id: The user asking.

        Returns:
            True if a clip was deleted.
        """
        result = self._session.execute(
            text("DELETE FROM speech_clips WHERE clip_id = :id AND owner_id = :owner_id"),
            {"id": clip_id, "owner_id": owner_id},
        )
        self._session.commit()
        return bool(result.rowcount)  # type: ignore[attr-defined]

    def object_keys(self, owner_id: UUID) -> list[str]:
        """Return where every one of the user's clips is stored, to delete them all.

        Args:
            owner_id: The user.

        Returns:
            Where each of the user's clips' audio is stored.
        """
        rows = self._session.execute(
            text(
                "SELECT object_key FROM speech_clips"
                " WHERE owner_id = :owner_id AND object_key IS NOT NULL"
            ),
            {"owner_id": owner_id},
        ).scalars()
        return list(rows)
