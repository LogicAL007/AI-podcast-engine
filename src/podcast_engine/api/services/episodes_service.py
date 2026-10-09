"""Business rules for episodes. No HTTP and no SQL in here."""

from collections.abc import Callable
from uuid import UUID

from podcast_engine.api.errors import NotFoundError, PipelineUnavailableError
from podcast_engine.api.models.episodes_model import EpisodeRead, EpisodeScript, StageRunRead
from podcast_engine.api.repositories.episodes_repository import EpisodeRepository
from podcast_engine.api.repositories.shows_repository import ShowRepository
from podcast_engine.common.logging import get_logger
from podcast_engine.common.models import EpisodeStatus
from podcast_engine.common.storage import ObjectStore

# Starts the pipeline for an episode id (enqueues the first stage).
EnqueueEpisode = Callable[[UUID], None]

log = get_logger("api.episodes")


class EpisodeService:
    def __init__(
        self,
        episodes: EpisodeRepository,
        shows: ShowRepository,
        enqueue: EnqueueEpisode,
        store: ObjectStore | None = None,
    ) -> None:
        self._episodes = episodes
        self._shows = shows
        self._enqueue = enqueue
        self._store = store

    def start(self, show_id: UUID) -> EpisodeRead:
        """Create an episode for a show and hand it to the pipeline.

        The first episode builds everything. A later one is a refresh: only segments whose
        sources changed are regenerated, and if none changed the episode ends as ``unchanged``.

        The row is committed before the job is enqueued, so a worker can always read it. If the
        queue is unreachable the episode is marked failed rather than left queued forever.
        """
        if self._shows.get(show_id) is None:
            raise NotFoundError("show", show_id)
        episode = self._episodes.add(show_id)
        try:
            self._enqueue(episode.episode_id)
        except Exception as error:
            log.exception("enqueue_failed", episode_id=str(episode.episode_id))
            self._episodes.set_status(episode.episode_id, EpisodeStatus.FAILED)
            raise PipelineUnavailableError(
                "The job queue is unavailable; try again later"
            ) from error
        return episode

    def get(self, episode_id: UUID) -> EpisodeRead:
        episode = self._episodes.get(episode_id)
        if episode is None:
            raise NotFoundError("episode", episode_id)
        return episode

    def list_for_show(self, show_id: UUID, *, limit: int, offset: int) -> list[EpisodeRead]:
        if self._shows.get(show_id) is None:
            raise NotFoundError("show", show_id)
        return self._episodes.list_for_show(show_id, limit=limit, offset=offset)

    def get_script(self, episode_id: UUID) -> EpisodeScript:
        script = self._episodes.get_script(episode_id)
        if script is None:
            raise NotFoundError("episode", episode_id)
        return script

    def list_runs(self, episode_id: UUID) -> list[StageRunRead]:
        self.get(episode_id)
        return self._episodes.list_runs(episode_id)

    def get_audio(self, episode_id: UUID) -> bytes:
        files = self._episodes.get_files(episode_id)
        if files is None:
            raise NotFoundError("episode", episode_id)
        return self._read(files.audio_key, "audio for episode", episode_id)

    def get_notes(self, episode_id: UUID) -> str:
        files = self._episodes.get_files(episode_id)
        if files is None:
            raise NotFoundError("episode", episode_id)
        return self._read(files.notes_key, "show notes for episode", episode_id).decode("utf-8")

    def _read(self, key: str | None, what: str, episode_id: UUID) -> bytes:
        if key is None or self._store is None or not self._store.exists(key):
            raise NotFoundError(what, episode_id)
        return self._store.get(key)
