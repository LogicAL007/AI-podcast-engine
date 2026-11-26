from typing import Any, Protocol
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from podcast_engine.api.models.music_model import MusicTrackRead

_COLUMNS = (
    "CAST(track_id AS text) AS track_id, name, role, false AS builtin, credit,"
    " duration_seconds, created_at, object_key"
)


class MusicRepository(Protocol):
    """Stores uploaded music tracks.

    Every method is scoped to one owner: another user's track does not exist for them.
    """

    def add(self, owner_id: UUID, values: dict[str, Any]) -> MusicTrackRead:
        """Record an uploaded track.

        Args:
            owner_id: The user uploading.
            values: The track's id, name, role, credit, storage key, size, length, checksum and when
                its rights were confirmed.

        Returns:
            The stored track.
        """
        ...

    def get(self, track_id: UUID, owner_id: UUID) -> MusicTrackRead | None:
        """Return one of the user's tracks.

        Args:
            track_id: The track.
            owner_id: The user asking.

        Returns:
            The track, or None when the user has no such track.
        """
        ...

    def list_all(self, owner_id: UUID) -> list[MusicTrackRead]:
        """Return all of the user's tracks.

        Args:
            owner_id: The user asking.

        Returns:
            The user's tracks, newest first.
        """
        ...

    def count(self, owner_id: UUID) -> int:
        """Count the user's tracks, for the per-account limit.

        Args:
            owner_id: The user.

        Returns:
            How many tracks the user has uploaded.
        """
        ...

    def owned(self, track_ids: set[str], owner_id: UUID) -> set[str]:
        """Return which of some track ids are the user's uploads.

        Args:
            track_ids: Upload ids to check.
            owner_id: The user.

        Returns:
            The ids among them that are the user's uploads.
        """
        ...

    def delete(self, track_id: UUID, owner_id: UUID) -> bool:
        """Delete a track and take it out of the user's shows.

        Args:
            track_id: The track to delete.
            owner_id: The user asking.

        Returns:
            True if a track was deleted.
        """
        ...

    def object_keys(self, owner_id: UUID) -> list[str]:
        """Return where every one of the user's tracks is stored, to delete them all.

        Args:
            owner_id: The user.

        Returns:
            Where each of the user's tracks is stored.
        """
        ...


class PostgresMusicRepository:
    """Tracks in the ``music_tracks`` table, the only API code that knows it.

    Each write commits on its own.
    """

    def __init__(self, session: Session) -> None:
        """Create the repository.

        Args:
            session: The database session for this request.
        """
        self._session = session

    def add(self, owner_id: UUID, values: dict[str, Any]) -> MusicTrackRead:
        """Record an uploaded track.

        Args:
            owner_id: The user uploading.
            values: The track's id, name, role, credit, storage key, size, length, checksum and when
                its rights were confirmed.

        Returns:
            The stored track.
        """
        row = (
            self._session.execute(
                text(
                    "INSERT INTO music_tracks (track_id, owner_id, name, role, credit,"  # noqa: S608
                    " object_key, size_bytes, duration_seconds, sha256, rights_confirmed_at)"
                    " VALUES (:track_id, :owner_id, :name, :role, :credit, :object_key,"
                    " :size_bytes, :duration_seconds, :sha256, :rights_confirmed_at)"
                    f" RETURNING {_COLUMNS}"
                ),
                {**values, "owner_id": owner_id},
            )
            .mappings()
            .one()
        )
        self._session.commit()
        return MusicTrackRead.model_validate(row)

    def get(self, track_id: UUID, owner_id: UUID) -> MusicTrackRead | None:
        """Return one of the user's tracks.

        Args:
            track_id: The track.
            owner_id: The user asking.

        Returns:
            The track, or None when the user has no such track.
        """
        row = (
            self._session.execute(
                text(
                    f"SELECT {_COLUMNS} FROM music_tracks"  # noqa: S608 - constant column list
                    " WHERE track_id = :id AND owner_id = :owner_id"
                ),
                {"id": track_id, "owner_id": owner_id},
            )
            .mappings()
            .one_or_none()
        )
        return MusicTrackRead.model_validate(row) if row else None

    def list_all(self, owner_id: UUID) -> list[MusicTrackRead]:
        """Return all of the user's tracks.

        Args:
            owner_id: The user asking.

        Returns:
            The user's tracks, newest first.
        """
        rows = self._session.execute(
            text(
                f"SELECT {_COLUMNS} FROM music_tracks WHERE owner_id = :owner_id"  # noqa: S608
                " ORDER BY created_at DESC, track_id"
            ),
            {"owner_id": owner_id},
        ).mappings()
        return [MusicTrackRead.model_validate(row) for row in rows]

    def count(self, owner_id: UUID) -> int:
        """Count the user's tracks, for the per-account limit.

        Args:
            owner_id: The user.

        Returns:
            How many tracks the user has uploaded.
        """
        return int(
            self._session.execute(
                text("SELECT count(*) FROM music_tracks WHERE owner_id = :owner_id"),
                {"owner_id": owner_id},
            ).scalar_one()
        )

    def owned(self, track_ids: set[str], owner_id: UUID) -> set[str]:
        """Return which of some track ids are the user's uploads.

        Args:
            track_ids: Upload ids to check.
            owner_id: The user.

        Returns:
            The ids among them that are the user's uploads.
        """
        if not track_ids:
            return set()
        rows = self._session.execute(
            text(
                "SELECT CAST(track_id AS text) FROM music_tracks"
                " WHERE owner_id = :owner_id AND CAST(track_id AS text) = ANY(:ids)"
            ),
            {"owner_id": owner_id, "ids": sorted(track_ids)},
        ).scalars()
        return set(rows)

    def delete(self, track_id: UUID, owner_id: UUID) -> bool:
        """Remove the track, and take it out of every show of the owner's that used it.

        Args:
            track_id: The track to delete.
            owner_id: The user asking.

        Returns:
            True if a track was deleted.
        """
        self._session.execute(
            text(
                "UPDATE shows SET music = (SELECT coalesce(jsonb_object_agg(k, v), '{}')"
                " FROM jsonb_each(music) AS e(k, v) WHERE v <> to_jsonb(CAST(:id AS text)))"
                " WHERE owner_id = :owner_id"
            ),
            {"id": str(track_id), "owner_id": owner_id},
        )
        result = self._session.execute(
            text("DELETE FROM music_tracks WHERE track_id = :id AND owner_id = :owner_id"),
            {"id": track_id, "owner_id": owner_id},
        )
        self._session.commit()
        return bool(result.rowcount)  # type: ignore[attr-defined]

    def object_keys(self, owner_id: UUID) -> list[str]:
        """Return where every one of the user's tracks is stored, to delete them all.

        Args:
            owner_id: The user.

        Returns:
            Where each of the user's tracks is stored.
        """
        rows = self._session.execute(
            text("SELECT object_key FROM music_tracks WHERE owner_id = :owner_id"),
            {"owner_id": owner_id},
        ).scalars()
        return list(rows)
