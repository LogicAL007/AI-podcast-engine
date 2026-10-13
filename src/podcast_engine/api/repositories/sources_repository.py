"""Persistence for a show's ingested sources: reads ``source_items`` (the pipeline writes it)."""

from typing import Protocol
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from podcast_engine.api.models.pagination_model import Paged
from podcast_engine.api.models.sources_model import SourceRead


class SourceRepository(Protocol):
    def list_page(self, show_id: UUID, *, limit: int, offset: int) -> Paged[SourceRead]: ...


class PostgresSourceRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_page(self, show_id: UUID, *, limit: int, offset: int) -> Paged[SourceRead]:
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
