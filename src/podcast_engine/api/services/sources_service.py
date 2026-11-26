from uuid import UUID

from podcast_engine.api.errors import NotFoundError
from podcast_engine.api.models.pagination_model import Paged
from podcast_engine.api.models.sources_model import SourceRead
from podcast_engine.api.repositories.shows_repository import ShowRepository
from podcast_engine.api.repositories.sources_repository import SourceRepository


class SourceService:
    """Business rules for a show's sources. No HTTP and no SQL in here."""

    def __init__(self, sources: SourceRepository, shows: ShowRepository) -> None:
        """Create the service.

        Args:
            sources: Where ingested sources are read from.
            shows: Where shows are stored, to check ownership.
        """
        self._sources = sources
        self._shows = shows

    def list_for_show(
        self, show_id: UUID, owner: UUID, *, limit: int, offset: int
    ) -> Paged[SourceRead]:
        """Return one page of the owner's show's source sections.

        Args:
            show_id: The show whose sources to list.
            owner: The user asking.
            limit: Most sections to return.
            offset: Sections to skip before this page.

        Returns:
            The page of sections, in source order, and the total.

        Raises:
            NotFoundError: The show is not the owner's or does not exist.
        """
        if self._shows.get(show_id, owner) is None:
            raise NotFoundError("show", show_id)
        return self._sources.list_page(show_id, limit=limit, offset=offset)
