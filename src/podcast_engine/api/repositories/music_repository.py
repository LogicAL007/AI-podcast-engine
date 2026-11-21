"""Persistence for uploaded music: the only API module that knows ``music_tracks``."""

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
    """Every method is scoped to one owner: another user's track does not exist for them."""

    def add(self, owner_id: UUID, values: dict[str, Any]) -> MusicTrackRead: ...

    def get(self, track_id: UUID, owner_id: UUID) -> MusicTrackRead | None: ...

    def list_all(self, owner_id: UUID) -> list[MusicTrackRead]: ...

    def count(self, owner_id: UUID) -> int: ...

    def owned(self, track_ids: set[str], owner_id: UUID) -> set[str]: ...

    def delete(self, track_id: UUID, owner_id: UUID) -> bool: ...

    def object_keys(self, owner_id: UUID) -> list[str]: ...


class PostgresMusicRepository:
    """Each write commits on its own."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, owner_id: UUID, values: dict[str, Any]) -> MusicTrackRead:
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
        rows = self._session.execute(
            text(
                f"SELECT {_COLUMNS} FROM music_tracks WHERE owner_id = :owner_id"  # noqa: S608
                " ORDER BY created_at DESC, track_id"
            ),
            {"owner_id": owner_id},
        ).mappings()
        return [MusicTrackRead.model_validate(row) for row in rows]

    def count(self, owner_id: UUID) -> int:
        return int(
            self._session.execute(
                text("SELECT count(*) FROM music_tracks WHERE owner_id = :owner_id"),
                {"owner_id": owner_id},
            ).scalar_one()
        )

    def owned(self, track_ids: set[str], owner_id: UUID) -> set[str]:
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
        """Remove the track, and take it out of every show of the owner's that used it."""
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
        rows = self._session.execute(
            text("SELECT object_key FROM music_tracks WHERE owner_id = :owner_id"),
            {"owner_id": owner_id},
        ).scalars()
        return list(rows)
