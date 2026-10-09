"""Business rules for episodes. No HTTP and no SQL in here."""

from collections.abc import Callable
from uuid import UUID

from podcast_engine.api.errors import NotFoundError, PipelineUnavailableError
from podcast_engine.api.models.episodes_model import EpisodeRead
from podcast_engine.api.repositories.episodes_repository import EpisodeRepository
from podcast_engine.api.repositories.shows_repository import ShowRepository
from podcast_engine.common.logging import get_logger
from podcast_engine.common.models import EpisodeStatus

# Starts the pipeline for an episode id (enqueues the first stage).
EnqueueEpisode = Callable[[UUID], None]

log = get_logger("api.episodes")


class EpisodeService:
    def __init__(
        self,
        episodes: EpisodeRepository,
        shows: ShowRepository,
        enqueue: EnqueueEpisode,
    ) -> None:
        self._episodes = episodes
        self._shows = shows
        self._enqueue = enqueue

    def start(self, show_id: UUID) -> EpisodeRead:
        """Create an episode for a show and hand it to the pipeline.

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
