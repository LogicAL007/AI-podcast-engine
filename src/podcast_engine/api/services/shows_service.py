"""Business rules for shows. No HTTP and no SQL in here.

Every method acts for one owner: a show of another user is reported as not found, so its existence
is not revealed.
"""

from uuid import UUID

from podcast_engine.api.errors import InvalidInputError, NotFoundError
from podcast_engine.api.models.pagination_model import Paged
from podcast_engine.api.models.shows_model import ShowCreate, ShowRead, ShowUpdate
from podcast_engine.api.repositories.shows_repository import ShowRepository
from podcast_engine.api.repositories.voices_repository import VoiceRepository


class ShowService:
    def __init__(self, repository: ShowRepository, voices: VoiceRepository | None = None) -> None:
        self._repository = repository
        self._voices = voices

    def _check_voices(self, host_voices: dict[str, UUID] | None, owner: UUID) -> None:
        """A host may only speak with a voice its owner registered (with consent)."""
        wanted = set((host_voices or {}).values())
        if not wanted:
            return
        owned = self._voices.owned(wanted, owner) if self._voices else set()
        if missing := wanted - owned:
            raise InvalidInputError(f"no such voice: {', '.join(sorted(map(str, missing)))}")

    def create(self, data: ShowCreate, owner: UUID) -> ShowRead:
        self._check_voices(data.host_voices, owner)
        return self._repository.add(data, owner)

    def get(self, show_id: UUID, owner: UUID) -> ShowRead:
        show = self._repository.get(show_id, owner)
        if show is None:
            raise NotFoundError("show", show_id)
        return show

    def list_page(self, owner: UUID, *, limit: int, offset: int) -> Paged[ShowRead]:
        return self._repository.list_page(owner, limit=limit, offset=offset)

    def update(self, show_id: UUID, owner: UUID, data: ShowUpdate) -> ShowRead:
        self._check_voices(data.host_voices, owner)
        changes = data.model_dump(mode="json", exclude_none=True)
        if not changes:
            return self.get(show_id, owner)
        show = self._repository.update(show_id, owner, changes)
        if show is None:
            raise NotFoundError("show", show_id)
        return show

    def delete(self, show_id: UUID, owner: UUID) -> None:
        if not self._repository.delete(show_id, owner):
            raise NotFoundError("show", show_id)
