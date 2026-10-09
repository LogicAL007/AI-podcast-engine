"""Persistence for episodes: the only module that knows the ``episodes`` table."""

from typing import Protocol
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from podcast_engine.api.models.episodes_model import EpisodeRead
from podcast_engine.common.models import EpisodeStatus

_COLUMNS = "episode_id, show_id, status, rewrite_count, created_at, published_at"


class EpisodeRepository(Protocol):
    def add(self, show_id: UUID) -> EpisodeRead: ...

    def get(self, episode_id: UUID) -> EpisodeRead | None: ...

    def list_for_show(self, show_id: UUID, *, limit: int, offset: int) -> list[EpisodeRead]: ...

    def set_status(self, episode_id: UUID, status: EpisodeStatus) -> None: ...


class PostgresEpisodeRepository:
    """Each write commits on its own, so a queued job can always find its row."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, show_id: UUID) -> EpisodeRead:
        row = (
            self._session.execute(
                text(f"INSERT INTO episodes (show_id) VALUES (:show_id) RETURNING {_COLUMNS}"),  # noqa: S608
                {"show_id": show_id},
            )
            .mappings()
            .one()
        )
        self._session.commit()
        return EpisodeRead.model_validate(row)

    def get(self, episode_id: UUID) -> EpisodeRead | None:
        row = (
            self._session.execute(
                text(f"SELECT {_COLUMNS} FROM episodes WHERE episode_id = :episode_id"),  # noqa: S608
                {"episode_id": episode_id},
            )
            .mappings()
            .one_or_none()
        )
        return EpisodeRead.model_validate(row) if row else None

    def list_for_show(self, show_id: UUID, *, limit: int, offset: int) -> list[EpisodeRead]:
        rows = self._session.execute(
            text(
                f"SELECT {_COLUMNS} FROM episodes WHERE show_id = :show_id"  # noqa: S608
                " ORDER BY created_at DESC, episode_id LIMIT :limit OFFSET :offset"
            ),
            {"show_id": show_id, "limit": limit, "offset": offset},
        ).mappings()
        return [EpisodeRead.model_validate(row) for row in rows]

    def set_status(self, episode_id: UUID, status: EpisodeStatus) -> None:
        self._session.execute(
            text("UPDATE episodes SET status = :status WHERE episode_id = :episode_id"),
            {"status": status.value, "episode_id": episode_id},
        )
        self._session.commit()
