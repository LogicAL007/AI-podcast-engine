from typing import Protocol
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from podcast_engine.api.models.pagination_model import Paged
from podcast_engine.api.models.sources_model import SourceRead


class SourceRepository(Protocol):
    """Reads a show's ingested sources; the pipeline writes them."""

    def list_page(self, show_id: UUID, *, limit: int, offset: int) -> Paged[SourceRead]:
        """Return one page of a show's source sections, in source order.

        Args:
            show_id: The show whose sources to list.
            limit: Most sections to return.
            offset: Sections to skip before this page.

        Returns:
            The page of sections and the total across all pages.
        """
        ...


class PostgresSourceRepository:
    """Source reads from the ``source_items`` and ``chunks`` tables."""

    def __init__(self, session: Session) -> None:
        """Create the repository.

        Args:
            session: The database session for this request.
        """
        self._session = session

    def list_page(self, show_id: UUID, *, limit: int, offset: int) -> Paged[SourceRead]:
        """Return one page of a show's source sections, in source order.

        Each section comes with its word count and the number of passages it was split into.

        Args:
            show_id: The show whose sources to list.
            limit: Most sections to return.
            offset: Sections to skip before this page.

        Returns:
            The page of sections and the total across all pages.
        """
        rows = self._session.execute(
            text(
                "SELECT i.item_id, i.url, i.title, i.position, i.reliability, i.content_hash,"
                " coalesce(array_length(regexp_split_to_array(trim(i.text), '\\s+'), 1), 0)"
                " AS words, (SELECT count(*) FROM chunks c WHERE c.item_id = i.item_id) AS chunks,"
                " i.published_at, i.fetched_at FROM source_items i WHERE i.show_id = :show_id"
                " ORDER BY i.position, i.item_id LIMIT :limit OFFSET :offset"
            ),
            {"show_id": show_id, "limit": limit, "offset": offset},
        ).mappings()
        items = [SourceRead.model_validate(row) for row in rows]
        total = self._session.execute(
            text("SELECT count(*) FROM source_items WHERE show_id = :show_id"), {"show_id": show_id}
        ).scalar_one()
        return Paged(items, int(total))
