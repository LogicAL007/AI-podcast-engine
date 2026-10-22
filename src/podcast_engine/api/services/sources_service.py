"""Business rules for a show's sources. No HTTP and no SQL in here."""

from uuid import UUID

from podcast_engine.api.errors import NotFoundError
from podcast_engine.api.models.pagination_model import Paged
from podcast_engine.api.models.sources_model import SourceRead
from podcast_engine.api.repositories.shows_repository import ShowRepository
from podcast_engine.api.repositories.sources_repository import SourceRepository


class SourceService:
    def __init__(self, sources: SourceRepository, shows: ShowRepository) -> None:
        self._sources = sources
        self._shows = shows

    def list_for_show(
        self, show_id: UUID, owner: UUID, *, limit: int, offset: int
    ) -> Paged[SourceRead]:
        if self._shows.get(show_id, owner) is None:
            raise NotFoundError("show", show_id)
        return self._sources.list_page(show_id, limit=limit, offset=offset)
