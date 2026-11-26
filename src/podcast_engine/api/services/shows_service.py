from uuid import UUID

from podcast_engine.api.errors import InvalidInputError, NotFoundError
from podcast_engine.api.models.pagination_model import Paged
from podcast_engine.api.models.shows_model import ShowCreate, ShowRead, ShowUpdate
from podcast_engine.api.repositories.music_repository import MusicRepository
from podcast_engine.api.repositories.shows_repository import ShowRepository
from podcast_engine.api.repositories.voices_repository import VoiceRepository
from podcast_engine.common.music import BUILTIN_TRACKS, ShowMusic, is_builtin


class ShowService:
    """Business rules for shows. No HTTP and no SQL in here.

    Every method acts for one owner: a show of another user is reported as not found, so its
    existence is not revealed.
    """

    def __init__(
        self,
        repository: ShowRepository,
        voices: VoiceRepository | None = None,
        music: MusicRepository | None = None,
    ) -> None:
        """Create the service.

        Args:
            repository: Where shows are stored.
            voices: Where registered voices are stored; without it, no host voice is accepted.
            music: Where uploaded tracks are stored; without it, only built-in tracks are accepted.
        """
        self._repository = repository
        self._voices = voices
        self._music = music

    def _check_voices(self, host_voices: dict[str, UUID] | None, owner: UUID) -> None:
        """Check that every host voice is one the owner registered, with consent.

        Args:
            host_voices: Each host's voice id, or None.
            owner: The show's owner.

        Raises:
            InvalidInputError: A voice is not the owner's or does not exist.
        """
        wanted = set((host_voices or {}).values())
        if not wanted:
            return
        owned = self._voices.owned(wanted, owner) if self._voices else set()
        if missing := wanted - owned:
            raise InvalidInputError(f"no such voice: {', '.join(sorted(map(str, missing)))}")

    def _check_music(self, music: ShowMusic | None, owner: UUID) -> None:
        """Check that the show uses only built-in tracks and the owner's own uploads.

        Args:
            music: The show's music settings, or None.
            owner: The show's owner.

        Raises:
            InvalidInputError: A track is not built in and not one of the owner's uploads.
        """
        wanted = music.track_ids() if music else set()
        uploaded = {t for t in wanted if not is_builtin(t)}
        owned = self._music.owned(uploaded, owner) if self._music and uploaded else set()
        missing = {t for t in wanted - uploaded if t not in BUILTIN_TRACKS} | (uploaded - owned)
        if missing:
            raise InvalidInputError(f"no such music track: {', '.join(sorted(missing))}")

    def create(self, data: ShowCreate, owner: UUID) -> ShowRead:
        """Create a show for its owner.

        Args:
            data: The new show's settings.
            owner: The user who will own it.

        Returns:
            The created show.

        Raises:
            InvalidInputError: A host voice or music track is not one the owner may use.
        """
        self._check_voices(data.host_voices, owner)
        self._check_music(data.music, owner)
        return self._repository.add(data, owner)

    def get(self, show_id: UUID, owner: UUID) -> ShowRead:
        """Return one of the owner's shows.

        Args:
            show_id: The show to return.
            owner: The user asking.

        Returns:
            The show.

        Raises:
            NotFoundError: The show does not exist or belongs to someone else.
        """
        show = self._repository.get(show_id, owner)
        if show is None:
            raise NotFoundError("show", show_id)
        return show

    def list_page(self, owner: UUID, *, limit: int, offset: int) -> Paged[ShowRead]:
        """Return one page of the owner's shows, newest first.

        Args:
            owner: The user asking.
            limit: Most shows to return.
            offset: Shows to skip before this page.

        Returns:
            The page of shows and the total across all pages.
        """
        return self._repository.list_page(owner, limit=limit, offset=offset)

    def update(self, show_id: UUID, owner: UUID, data: ShowUpdate) -> ShowRead:
        """Change some of a show's settings.

        Fields left out keep their value; an update that changes nothing returns the show as it is.

        Args:
            show_id: The show to change.
            owner: The user asking.
            data: The settings to change.

        Returns:
            The show with its new settings.

        Raises:
            NotFoundError: The show does not exist or belongs to someone else.
            InvalidInputError: A host voice or music track is not one the owner may use.
        """
        self._check_voices(data.host_voices, owner)
        self._check_music(data.music, owner)
        changes = data.model_dump(mode="json", exclude_none=True)
        if not changes:
            return self.get(show_id, owner)
        show = self._repository.update(show_id, owner, changes)
        if show is None:
            raise NotFoundError("show", show_id)
        return show

    def delete(self, show_id: UUID, owner: UUID) -> None:
        """Delete one of the owner's shows and everything in it.

        Args:
            show_id: The show to delete.
            owner: The user asking.

        Raises:
            NotFoundError: The show does not exist or belongs to someone else.
        """
        if not self._repository.delete(show_id, owner):
            raise NotFoundError("show", show_id)
