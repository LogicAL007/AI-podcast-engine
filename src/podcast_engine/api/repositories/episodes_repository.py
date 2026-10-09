"""Persistence for episodes: the only module that knows the ``episodes`` table."""

from typing import Any, Protocol
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from podcast_engine.api.models.episodes_model import (
    ClaimRead,
    EpisodeFiles,
    EpisodeRead,
    EpisodeScript,
    LineRead,
    SegmentScript,
    StageRunRead,
)
from podcast_engine.common.models import EpisodeStatus

_COLUMNS = (
    "episode_id, show_id, status, stage, error, revision, rewrite_count, created_at, published_at,"
    " audio_key IS NOT NULL AS has_audio, notes_key IS NOT NULL AS has_notes"
)


class EpisodeRepository(Protocol):
    def add(self, show_id: UUID) -> EpisodeRead: ...

    def get(self, episode_id: UUID) -> EpisodeRead | None: ...

    def list_for_show(self, show_id: UUID, *, limit: int, offset: int) -> list[EpisodeRead]: ...

    def set_status(self, episode_id: UUID, status: EpisodeStatus) -> None: ...

    def get_script(self, episode_id: UUID) -> EpisodeScript | None: ...

    def list_runs(self, episode_id: UUID) -> list[StageRunRead]: ...

    def get_files(self, episode_id: UUID) -> EpisodeFiles | None: ...


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

    def get_script(self, episode_id: UUID) -> EpisodeScript | None:
        """The stored script, with each claim's verdict from the fact-check."""
        row = (
            self._session.execute(
                text("SELECT script, fact_check FROM episodes WHERE episode_id = :id"),
                {"id": episode_id},
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            return None
        verdicts = {
            claim.claim_id: (claim.supported, claim.reason)
            for claim in self._session.execute(
                text("SELECT claim_id, supported, reason FROM claims WHERE episode_id = :id"),
                {"id": episode_id},
            )
        }
        lines_by_position: dict[str, list[dict[str, Any]]] = (row["script"] or {}).get(
            "segments", {}
        )
        segments = []
        for segment in self._session.execute(
            text(
                "SELECT position, title, source_item_ids FROM segments"
                " WHERE episode_id = :id ORDER BY position"
            ),
            {"id": episode_id},
        ):
            lines = []
            for line in lines_by_position.get(str(segment.position), []):
                claims = []
                for claim in line.get("claims", []):
                    supported, reason = verdicts.get(UUID(claim["claim_id"]), (None, None))
                    claims.append(
                        ClaimRead(
                            text=claim["text"],
                            chunk_ids=claim.get("chunk_ids", []),
                            supported=supported,
                            reason=reason,
                        )
                    )
                lines.append(LineRead(speaker=line["speaker"], text=line["text"], claims=claims))
            segments.append(
                SegmentScript(
                    position=segment.position,
                    title=segment.title,
                    source_item_ids=segment.source_item_ids,
                    lines=lines,
                )
            )
        return EpisodeScript(episode_id=episode_id, segments=segments, fact_check=row["fact_check"])

    def list_runs(self, episode_id: UUID) -> list[StageRunRead]:
        rows = self._session.execute(
            text(
                "SELECT stage, seconds, model, prompt_version, seed, started_at FROM stage_runs"
                " WHERE episode_id = :id ORDER BY started_at"
            ),
            {"id": episode_id},
        ).mappings()
        return [StageRunRead.model_validate(row) for row in rows]

    def get_files(self, episode_id: UUID) -> EpisodeFiles | None:
        row = (
            self._session.execute(
                text("SELECT audio_key, notes_key FROM episodes WHERE episode_id = :id"),
                {"id": episode_id},
            )
            .mappings()
            .one_or_none()
        )
        return EpisodeFiles.model_validate(dict(row)) if row else None
