"""In-memory stand-ins for the repositories and object store, used by API tests."""

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from podcast_engine.api.models.episodes_model import (
    EpisodeFiles,
    EpisodeRead,
    EpisodeScript,
    StageRunRead,
)
from podcast_engine.api.models.shows_model import ShowCreate, ShowRead
from podcast_engine.common.models import EpisodeStatus


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

    def list_page(self, *, limit: int, offset: int) -> list[ShowRead]:
        shows = sorted(self.rows.values(), key=lambda show: show.created_at, reverse=True)
        return shows[offset : offset + limit]

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
        self.runs: dict[UUID, list[StageRunRead]] = {}
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

    def list_for_show(self, show_id: UUID, *, limit: int, offset: int) -> list[EpisodeRead]:
        matching = [row for row in self.rows.values() if row.show_id == show_id]
        return matching[offset : offset + limit]

    def set_status(self, episode_id: UUID, status: EpisodeStatus) -> None:
        self.rows[episode_id] = self.rows[episode_id].model_copy(update={"status": status})

    def get_script(self, episode_id: UUID) -> EpisodeScript | None:
        if episode_id not in self.rows:
            return None
        return self.scripts.get(episode_id, EpisodeScript(episode_id=episode_id, segments=[]))

    def list_runs(self, episode_id: UUID) -> list[StageRunRead]:
        return self.runs.get(episode_id, [])

    def get_files(self, episode_id: UUID) -> EpisodeFiles | None:
        if episode_id not in self.rows:
            return None
        return self.files.get(episode_id, EpisodeFiles(audio_key=None, notes_key=None))


class FakeObjectStore:
    def __init__(self, objects: dict[str, bytes] | None = None) -> None:
        self.objects = objects or {}

    def put(self, key: str, data: bytes, content_type: str) -> None:
        self.objects[key] = data

    def get(self, key: str) -> bytes:
        return self.objects[key]

    def exists(self, key: str) -> bool:
        return key in self.objects
