"""Business rules for shows. No HTTP and no SQL in here."""

from uuid import UUID

from podcast_engine.api.errors import NotFoundError
from podcast_engine.api.models.pagination_model import Paged
from podcast_engine.api.models.shows_model import ShowCreate, ShowRead, ShowUpdate
from podcast_engine.api.repositories.shows_repository import ShowRepository


class ShowService:
    def __init__(self, repository: ShowRepository) -> None:
        self._repository = repository

    def create(self, data: ShowCreate) -> ShowRead:
        return self._repository.add(data)

    def get(self, show_id: UUID) -> ShowRead:
        show = self._repository.get(show_id)
        if show is None:
            raise NotFoundError("show", show_id)
        return show

    def list_page(self, *, limit: int, offset: int) -> Paged[ShowRead]:
        return self._repository.list_page(limit=limit, offset=offset)

    def update(self, show_id: UUID, data: ShowUpdate) -> ShowRead:
        changes = data.model_dump(mode="json", exclude_none=True)
        if not changes:
            return self.get(show_id)
        show = self._repository.update(show_id, changes)
        if show is None:
            raise NotFoundError("show", show_id)
        return show

    def delete(self, show_id: UUID) -> None:
        if not self._repository.delete(show_id):
            raise NotFoundError("show", show_id)
