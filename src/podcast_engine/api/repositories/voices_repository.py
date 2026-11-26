import json
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from podcast_engine.api.models.pagination_model import Paged
from podcast_engine.api.models.voices_model import VoiceRead
from podcast_engine.stages.voice.registry import clips_voiced_with
from podcast_engine.stages.voice.speech_text import raw_speech_keys

_COLUMNS = (
    "voice_id, name, speaker, license, source, duration_seconds, consent, object_key, created_at"
)


class VoiceRepository(Protocol):
    """Stores cloned voices and their consent records.

    Every method is scoped to one owner: another user's voice does not exist for them.
    """

    def add(self, owner_id: UUID, values: dict[str, Any]) -> VoiceRead:
        """Record a registered voice.

        Args:
            owner_id: The user registering the voice.
            values: The voice's id, name, speaker, licence, source, consent record, storage key,
                size, length and checksum.

        Returns:
            The registered voice.
        """
        ...

    def get(self, voice_id: UUID, owner_id: UUID) -> VoiceRead | None:
        """Return one of the user's voices.

        Args:
            voice_id: The voice.
            owner_id: The user asking.

        Returns:
            The voice, or None when the user has no such voice.
        """
        ...

    def list_page(self, owner_id: UUID, *, limit: int, offset: int) -> Paged[VoiceRead]:
        """Return one page of the user's voices, newest first.

        Args:
            owner_id: The user asking.
            limit: Most voices to return.
            offset: Voices to skip before this page.

        Returns:
            The page of voices, newest first, and the total.
        """
        ...

    def count(self, owner_id: UUID) -> int:
        """Count the user's voices, for the per-account limit.

        Args:
            owner_id: The user.

        Returns:
            How many voices the user has registered.
        """
        ...

    def owned(self, voice_ids: set[UUID], owner_id: UUID) -> set[UUID]:
        """Return which of some voice ids are the user's.

        Args:
            voice_ids: Voice ids to check.
            owner_id: The user.

        Returns:
            The ids among them that are the user's voices.
        """
        ...

    def delete(self, voice_id: UUID, owner_id: UUID) -> bool:
        """Delete a voice and take it off the user's show hosts.

        Args:
            voice_id: The voice.
            owner_id: The user asking.

        Returns:
            True if a voice was deleted.
        """
        ...

    def object_keys(self, owner_id: UUID) -> list[str]:
        """Return where every one of the user's recordings is stored, to delete them all.

        Args:
            owner_id: The user.

        Returns:
            Where each of the user's recordings is stored.
        """
        ...

    def clip_keys(self, voice_id: UUID, owner_id: UUID) -> list[str]:
        """Return the stored speech made with a voice, to delete when it is withdrawn.

        Args:
            voice_id: The voice being withdrawn.
            owner_id: The user.

        Returns:
            The object keys to delete.
        """
        ...


class PostgresVoiceRepository:
    """Voices in the ``voices`` table, the only code that knows it.

    Each write commits on its own.
    """

    def __init__(self, session: Session) -> None:
        """Create the repository.

        Args:
            session: The database session for this request.
        """
        self._session = session

    def add(self, owner_id: UUID, values: dict[str, Any]) -> VoiceRead:
        """Record a registered voice.

        Args:
            owner_id: The user registering the voice.
            values: The voice's id, name, speaker, licence, source, consent record, storage key,
                size, length and checksum.

        Returns:
            The registered voice.
        """
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
        """Return one of the user's voices.

        Args:
            voice_id: The voice.
            owner_id: The user asking.

        Returns:
            The voice, or None when the user has no such voice.
        """
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
        """Return one page of the user's voices, newest first.

        Args:
            owner_id: The user asking.
            limit: Most voices to return.
            offset: Voices to skip before this page.

        Returns:
            The page of voices, newest first, and the total.
        """
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
        """Count the user's voices, for the per-account limit.

        Args:
            owner_id: The user.

        Returns:
            How many voices the user has registered.
        """
        return int(
            self._session.execute(
                text("SELECT count(*) FROM voices WHERE owner_id = :owner_id"),
                {"owner_id": owner_id},
            ).scalar_one()
        )

    def owned(self, voice_ids: set[UUID], owner_id: UUID) -> set[UUID]:
        """Return which of some voice ids are the user's.

        Args:
            voice_ids: Voice ids to check.
            owner_id: The user.

        Returns:
            The ids among them that are the user's voices.
        """
        if not voice_ids:
            return set()
        rows = self._session.execute(
            text("SELECT voice_id FROM voices WHERE owner_id = :owner_id AND voice_id = ANY(:ids)"),
            {"owner_id": owner_id, "ids": list(voice_ids)},
        ).scalars()
        return set(rows)

    def delete(self, voice_id: UUID, owner_id: UUID) -> bool:
        """Remove the voice, and take it off every host of the owner's shows that used it.

        Args:
            voice_id: The voice.
            owner_id: The user asking.

        Returns:
            True if a voice was deleted.
        """
        self._session.execute(
            text(
                "UPDATE shows SET host_voices = (SELECT coalesce(jsonb_object_agg(k, v), '{}')"
                " FROM jsonb_each(host_voices) AS e(k, v) WHERE v <> to_jsonb(CAST(:id AS text)))"
                " WHERE owner_id = :owner_id"
            ),
            {"id": str(voice_id), "owner_id": owner_id},
        )
        self._session.execute(
            text(
                "DELETE FROM speech_clips WHERE owner_id = :owner_id"
                " AND voice->>'voice_id' = CAST(:id AS text)"
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
        """Return where every one of the user's recordings is stored, to delete them all.

        Args:
            owner_id: The user.

        Returns:
            Where each of the user's recordings is stored.
        """
        rows = self._session.execute(
            text("SELECT object_key FROM voices WHERE owner_id = :owner_id"),
            {"owner_id": owner_id},
        ).scalars()
        return list(rows)

    def clip_keys(self, voice_id: UUID, owner_id: UUID) -> list[str]:
        """Return the stored speech made with this voice, to delete when it is withdrawn.

        Its type-to-speech clips always, and the clips (and cached raw speech) in the owner's
        episodes and studio, unless another registered voice has the same recording (then they are
        that voice's too).

        Args:
            voice_id: The voice being withdrawn.
            owner_id: The user.

        Returns:
            The object keys to delete.
        """
        sha256 = self._session.execute(
            text("SELECT sha256 FROM voices WHERE voice_id = :id AND owner_id = :owner_id"),
            {"id": voice_id, "owner_id": owner_id},
        ).scalar_one_or_none()
        if sha256 is None:
            return []
        studio = self._session.execute(
            text(
                "SELECT object_key, text, delivery FROM speech_clips"
                " WHERE owner_id = :owner_id AND voice->>'voice_id' = :id"
            ),
            {"id": str(voice_id), "owner_id": owner_id},
        ).all()
        keys = [row.object_key for row in studio if row.object_key]
        shared = self._session.execute(
            text("SELECT count(*) FROM voices WHERE sha256 = :sha256 AND voice_id <> :id"),
            {"sha256": sha256, "id": voice_id},
        ).scalar_one()
        if shared:
            return keys
        for row in studio:
            keys += raw_speech_keys(sha256, row.text, row.delivery)
        rows = self._session.execute(
            text(
                "SELECT e.voice_lines, e.manifest FROM episodes e JOIN shows s USING (show_id)"
                " WHERE s.owner_id = :owner_id AND e.voice_lines IS NOT NULL"
            ),
            {"owner_id": owner_id},
        ).all()
        episodes = clips_voiced_with(sha256, [(row.voice_lines, row.manifest) for row in rows])
        return list(dict.fromkeys(keys + episodes))
