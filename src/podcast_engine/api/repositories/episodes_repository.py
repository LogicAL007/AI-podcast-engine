"""Persistence for episodes: the only module that knows the ``episodes`` table."""

import json
from collections.abc import Iterable
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from podcast_engine.api.models.episodes_model import (
    ClaimDetail,
    ClaimRead,
    EpisodeFiles,
    EpisodeRead,
    EpisodeScript,
    LineRead,
    SegmentScript,
    StageRunRead,
)
from podcast_engine.api.models.pagination_model import Paged
from podcast_engine.common.models import EpisodeStatus

_COLUMNS = (
    "episode_id, show_id, status, stage, error, revision, rewrite_count, created_at, published_at,"
    " approved_at, audio_key IS NOT NULL AS has_audio, notes_key IS NOT NULL AS has_notes,"
    " manifest->>'tts_provider' AS voice_provider"
)
# An episode is someone's through its show.
_OWNED = "show_id IN (SELECT show_id FROM shows WHERE owner_id = :owner_id)"
# Episode columns the API may change, mostly to move an episode through its lifecycle.
_UPDATABLE = frozenset({"status", "stage", "error", "approved_at", "rewrite_count"})


class EpisodeRepository(Protocol):
    def add(self, show_id: UUID) -> EpisodeRead: ...

    def get(self, episode_id: UUID, owner_id: UUID) -> EpisodeRead | None: ...

    def list_page(
        self,
        owner_id: UUID,
        *,
        show_id: UUID | None,
        status: EpisodeStatus | None,
        limit: int,
        offset: int,
    ) -> Paged[EpisodeRead]: ...

    def set_status(self, episode_id: UUID, status: EpisodeStatus) -> None: ...

    def update(self, episode_id: UUID, **fields: Any) -> None: ...

    def delete(self, episode_id: UUID) -> bool: ...

    def get_script(self, episode_id: UUID) -> EpisodeScript | None: ...

    def get_raw_script(self, episode_id: UUID) -> dict[str, Any] | None: ...

    def save_script(self, episode_id: UUID, script: dict[str, Any]) -> None: ...

    def segment_positions(self, episode_id: UUID) -> list[int]: ...

    def chunks_in_show(self, show_id: UUID, chunk_ids: Iterable[UUID]) -> set[UUID]: ...

    def list_runs(self, episode_id: UUID, *, limit: int, offset: int) -> Paged[StageRunRead]: ...

    def list_claims(
        self,
        episode_id: UUID,
        *,
        supported: bool | None,
        segment: int | None,
        limit: int,
        offset: int,
    ) -> Paged[ClaimDetail]: ...

    def get_files(self, episode_id: UUID) -> EpisodeFiles | None: ...


class PostgresEpisodeRepository:
    """Each write commits on its own, so a queued job can always find its row."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def _count(self, sql: str, params: dict[str, Any]) -> int:
        return int(self._session.execute(text(sql), params).scalar_one())

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

    def get(self, episode_id: UUID, owner_id: UUID) -> EpisodeRead | None:
        """The episode if its show belongs to ``owner_id``; otherwise None, as if it did not
        exist."""
        row = (
            self._session.execute(
                text(
                    f"SELECT {_COLUMNS} FROM episodes WHERE episode_id = :episode_id"  # noqa: S608
                    f" AND {_OWNED}"
                ),
                {"episode_id": episode_id, "owner_id": owner_id},
            )
            .mappings()
            .one_or_none()
        )
        return EpisodeRead.model_validate(row) if row else None

    def list_page(
        self,
        owner_id: UUID,
        *,
        show_id: UUID | None,
        status: EpisodeStatus | None,
        limit: int,
        offset: int,
    ) -> Paged[EpisodeRead]:
        """The owner's episodes, newest first. Filters are fixed SQL fragments; their values are
        bound parameters."""
        where = [_OWNED]
        params: dict[str, Any] = {"owner_id": owner_id, "limit": limit, "offset": offset}
        if show_id is not None:
            where.append("show_id = :show_id")
            params["show_id"] = show_id
        if status is not None:
            where.append("status = :status")
            params["status"] = status.value
        condition = " AND ".join(where)
        rows = self._session.execute(
            text(
                f"SELECT {_COLUMNS} FROM episodes WHERE {condition}"  # noqa: S608
                " ORDER BY created_at DESC, episode_id LIMIT :limit OFFSET :offset"
            ),
            params,
        ).mappings()
        items = [EpisodeRead.model_validate(row) for row in rows]
        total = self._count(f"SELECT count(*) FROM episodes WHERE {condition}", params)  # noqa: S608
        return Paged(items, total)

    def set_status(self, episode_id: UUID, status: EpisodeStatus) -> None:
        self.update(episode_id, status=status)

    def update(self, episode_id: UUID, **fields: Any) -> None:
        unknown = set(fields) - _UPDATABLE
        if unknown:
            raise ValueError(f"not updatable: {sorted(unknown)}")
        # Column names come from the whitelist above; values are always bound parameters.
        assignments = ", ".join(f"{name} = :{name}" for name in fields)
        params = {
            name: value.value if isinstance(value, EpisodeStatus) else value
            for name, value in fields.items()
        }
        self._session.execute(
            text(f"UPDATE episodes SET {assignments} WHERE episode_id = :episode_id"),  # noqa: S608
            {**params, "episode_id": episode_id},
        )
        self._session.commit()

    def delete(self, episode_id: UUID) -> bool:
        """Delete the episode; its segments, claims and stage runs go with it (cascade)."""
        result = self._session.execute(
            text("DELETE FROM episodes WHERE episode_id = :id"), {"id": episode_id}
        )
        self._session.commit()
        return bool(result.rowcount)  # type: ignore[attr-defined]

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

    def get_raw_script(self, episode_id: UUID) -> dict[str, Any] | None:
        row = self._session.execute(
            text("SELECT script FROM episodes WHERE episode_id = :id"), {"id": episode_id}
        ).one_or_none()
        if row is None:
            return None
        script: dict[str, Any] = row.script or {}
        return script

    def save_script(self, episode_id: UUID, script: dict[str, Any]) -> None:
        self._session.execute(
            text("UPDATE episodes SET script = CAST(:script AS jsonb) WHERE episode_id = :id"),
            {"script": json.dumps(script, default=str), "id": episode_id},
        )
        self._session.commit()

    def segment_positions(self, episode_id: UUID) -> list[int]:
        rows = self._session.execute(
            text("SELECT position FROM segments WHERE episode_id = :id ORDER BY position"),
            {"id": episode_id},
        )
        return [row.position for row in rows]

    def chunks_in_show(self, show_id: UUID, chunk_ids: Iterable[UUID]) -> set[UUID]:
        """Which of these chunks exist and belong to the show's sources."""
        ids = [str(chunk_id) for chunk_id in chunk_ids]
        if not ids:
            return set()
        rows = self._session.execute(
            text(
                "SELECT c.chunk_id FROM chunks c JOIN source_items i ON i.item_id = c.item_id"
                " WHERE i.show_id = :show_id AND c.chunk_id = ANY(CAST(:ids AS uuid[]))"
            ),
            {"show_id": show_id, "ids": ids},
        )
        return {row.chunk_id for row in rows}

    def list_runs(self, episode_id: UUID, *, limit: int, offset: int) -> Paged[StageRunRead]:
        params = {"id": episode_id, "limit": limit, "offset": offset}
        rows = self._session.execute(
            text(
                "SELECT stage, seconds, model, prompt_version, seed, started_at FROM stage_runs"
                " WHERE episode_id = :id ORDER BY started_at, run_id LIMIT :limit OFFSET :offset"
            ),
            params,
        ).mappings()
        items = [StageRunRead.model_validate(row) for row in rows]
        total = self._count("SELECT count(*) FROM stage_runs WHERE episode_id = :id", params)
        return Paged(items, total)

    def list_claims(
        self,
        episode_id: UUID,
        *,
        supported: bool | None,
        segment: int | None,
        limit: int,
        offset: int,
    ) -> Paged[ClaimDetail]:
        """In script order. ``supported=False`` matches only claims judged unsupported; claims not
        yet judged have ``supported`` null and match neither filter value."""
        where = ["episode_id = :id"]
        params: dict[str, Any] = {"id": episode_id, "limit": limit, "offset": offset}
        if supported is not None:
            where.append("supported = :supported")
            params["supported"] = supported
        if segment is not None:
            where.append("position = :segment")
            params["segment"] = segment
        condition = " AND ".join(where)
        rows = self._session.execute(
            text(
                "SELECT claim_id, position AS segment, text, chunk_ids, supported, reason"  # noqa: S608
                f" FROM claims WHERE {condition}"
                " ORDER BY position, claim_id LIMIT :limit OFFSET :offset"
            ),
            params,
        ).mappings()
        items = [ClaimDetail.model_validate(row) for row in rows]
        total = self._count(f"SELECT count(*) FROM claims WHERE {condition}", params)  # noqa: S608
        return Paged(items, total)

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
