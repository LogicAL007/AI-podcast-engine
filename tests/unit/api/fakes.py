"""In-memory stand-ins for the repositories and object store, used by API tests."""

from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from podcast_engine.api.models.episodes_model import (
    ClaimDetail,
    EpisodeFiles,
    EpisodeRead,
    EpisodeScript,
    StageRunRead,
)
from podcast_engine.api.models.pagination_model import Paged
from podcast_engine.api.models.shows_model import ShowCreate, ShowRead
from podcast_engine.api.models.sources_model import SourceRead
from podcast_engine.api.models.uploads_model import UploadRead
from podcast_engine.common.models import EpisodeStatus


def page[T](items: list[T], limit: int, offset: int) -> Paged[T]:
    return Paged(items[offset : offset + limit], len(items))


class FakeShowRepository:
    def __init__(self) -> None:
        self.rows: dict[UUID, ShowRead] = {}

    def add(self, data: ShowCreate) -> ShowRead:
        show = ShowRead(
            show_id=uuid4(),
            created_at=datetime.now(UTC),
            **{**data.model_dump(), "sources": [str(url) for url in data.sources]},
        )
        self.rows[show.show_id] = show
        return show

    def get(self, show_id: UUID) -> ShowRead | None:
        return self.rows.get(show_id)

    def list_page(self, *, limit: int, offset: int) -> Paged[ShowRead]:
        shows = sorted(self.rows.values(), key=lambda show: show.created_at, reverse=True)
        return page(shows, limit, offset)

    def update(self, show_id: UUID, changes: Mapping[str, Any]) -> ShowRead | None:
        show = self.rows.get(show_id)
        if show is None:
            return None
        updated = show.model_copy(update=dict(changes))
        self.rows[show_id] = updated
        return updated

    def delete(self, show_id: UUID) -> bool:
        return self.rows.pop(show_id, None) is not None


class FakeEpisodeRepository:
    def __init__(self) -> None:
        self.rows: dict[UUID, EpisodeRead] = {}
        self.scripts: dict[UUID, EpisodeScript] = {}
        self.raw_scripts: dict[UUID, dict[str, Any]] = {}
        self.positions: dict[UUID, list[int]] = {}
        self.show_chunks: dict[UUID, set[UUID]] = {}
        self.runs: dict[UUID, list[StageRunRead]] = {}
        self.claims: dict[UUID, list[ClaimDetail]] = {}
        self.files: dict[UUID, EpisodeFiles] = {}

    def add(self, show_id: UUID) -> EpisodeRead:
        episode = EpisodeRead(
            episode_id=uuid4(),
            show_id=show_id,
            status=EpisodeStatus.QUEUED,
            rewrite_count=0,
            created_at=datetime.now(UTC),
            published_at=None,
        )
        self.rows[episode.episode_id] = episode
        return episode

    def get(self, episode_id: UUID) -> EpisodeRead | None:
        return self.rows.get(episode_id)

    def list_page(
        self, *, show_id: UUID | None, status: EpisodeStatus | None, limit: int, offset: int
    ) -> Paged[EpisodeRead]:
        rows = [
            row
            for row in sorted(self.rows.values(), key=lambda e: e.created_at, reverse=True)
            if (show_id is None or row.show_id == show_id)
            and (status is None or row.status is status)
        ]
        return page(rows, limit, offset)

    def set_status(self, episode_id: UUID, status: EpisodeStatus) -> None:
        self.update(episode_id, status=status)

    def update(self, episode_id: UUID, **fields: Any) -> None:
        self.rows[episode_id] = self.rows[episode_id].model_copy(update=fields)

    def delete(self, episode_id: UUID) -> bool:
        return self.rows.pop(episode_id, None) is not None

    def get_script(self, episode_id: UUID) -> EpisodeScript | None:
        if episode_id not in self.rows:
            return None
        return self.scripts.get(episode_id, EpisodeScript(episode_id=episode_id, segments=[]))

    def get_raw_script(self, episode_id: UUID) -> dict[str, Any] | None:
        if episode_id not in self.rows:
            return None
        return self.raw_scripts.get(episode_id, {})

    def save_script(self, episode_id: UUID, script: dict[str, Any]) -> None:
        self.raw_scripts[episode_id] = script

    def segment_positions(self, episode_id: UUID) -> list[int]:
        return self.positions.get(episode_id, [])

    def chunks_in_show(self, show_id: UUID, chunk_ids: Iterable[UUID]) -> set[UUID]:
        return set(chunk_ids) & self.show_chunks.get(show_id, set())

    def list_runs(self, episode_id: UUID, *, limit: int, offset: int) -> Paged[StageRunRead]:
        return page(self.runs.get(episode_id, []), limit, offset)

    def list_claims(
        self,
        episode_id: UUID,
        *,
        supported: bool | None,
        segment: int | None,
        limit: int,
        offset: int,
    ) -> Paged[ClaimDetail]:
        rows = [
            c
            for c in self.claims.get(episode_id, [])
            if (supported is None or c.supported is supported)
            and (segment is None or c.segment == segment)
        ]
        return page(rows, limit, offset)

    def get_files(self, episode_id: UUID) -> EpisodeFiles | None:
        if episode_id not in self.rows:
            return None
        return self.files.get(episode_id, EpisodeFiles(audio_key=None, notes_key=None))


class FakeSourceRepository:
    def __init__(self) -> None:
        self.rows: dict[UUID, list[SourceRead]] = {}

    def list_page(self, show_id: UUID, *, limit: int, offset: int) -> Paged[SourceRead]:
        return page(self.rows.get(show_id, []), limit, offset)


class FakeUploadRepository:
    def __init__(self) -> None:
        self.rows: dict[UUID, UploadRead] = {}

    def add(self, **fields: Any) -> UploadRead:
        upload = UploadRead(created_at=datetime.now(UTC), **fields)
        self.rows[upload.upload_id] = upload
        return upload

    def get(self, show_id: UUID, upload_id: UUID) -> UploadRead | None:
        upload = self.rows.get(upload_id)
        return upload if upload is not None and upload.show_id == show_id else None

    def list_page(self, show_id: UUID, *, limit: int, offset: int) -> Paged[UploadRead]:
        rows = sorted(
            (u for u in self.rows.values() if u.show_id == show_id),
            key=lambda u: u.created_at,
            reverse=True,
        )
        return page(rows, limit, offset)

    def delete(self, show_id: UUID, upload_id: UUID) -> bool:
        if self.get(show_id, upload_id) is None:
            return False
        del self.rows[upload_id]
        return True


class FakeObjectStore:
    def __init__(self, objects: dict[str, bytes] | None = None) -> None:
        self.objects = objects or {}

    def put(self, key: str, data: bytes, content_type: str) -> None:
        self.objects[key] = data

    def get(self, key: str) -> bytes:
        return self.objects[key]

    def exists(self, key: str) -> bool:
        return key in self.objects

    def delete(self, key: str) -> None:
        self.objects.pop(key, None)
