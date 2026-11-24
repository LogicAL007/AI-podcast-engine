from uuid import UUID

from podcast_engine.api.errors import http_errors
from podcast_engine.api.models.music_model import MusicTrackRead
from podcast_engine.api.services.music_service import MAX_BYTES, MusicService
from podcast_engine.common.music import Role


class MusicController:
    """HTTP-facing entry point for the music library: calls the service, maps its errors to HTTP."""

    max_bytes = MAX_BYTES

    def __init__(self, service: MusicService) -> None:
        """Create the controller.

        Args:
            service: The music service holding the library's rules.
        """
        self._service = service

    def list_all(self, owner: UUID) -> list[MusicTrackRead]:
        """Return the built-in tracks and the caller's uploads.

        Args:
            owner: The signed-in user.

        Returns:
            Every track the caller can use.

        Raises:
            HTTPException: The service's domain errors, mapped to HTTP status codes.
        """
        return http_errors(lambda: self._service.list_all(owner))

    def upload(
        self, owner: UUID, *, name: str, role: Role, credit: str, rights: bool, data: bytes
    ) -> MusicTrackRead:
        """Add an uploaded track to the caller's library.

        Args:
            owner: The signed-in user.
            name: The track's name.
            role: What it is for: bed, intro, outro, sting or any.
            credit: Credit line for the show notes, or empty.
            rights: Whether the caller confirmed they may use the track.
            data: The track as 24 kHz mono WAV bytes.

        Returns:
            The stored track.

        Raises:
            HTTPException: The service's domain errors, mapped to HTTP status codes.
        """
        return http_errors(
            lambda: self._service.upload(
                owner, name=name, role=role, credit=credit, rights=rights, data=data
            )
        )

    def audio(self, track_id: str, owner: UUID) -> bytes:
        """Return a track's audio.

        Args:
            track_id: A built-in id (``builtin:...``) or an upload's id.
            owner: The signed-in user.

        Returns:
            The track as WAV bytes.

        Raises:
            HTTPException: The service's domain errors, mapped to HTTP status codes.
        """
        return http_errors(lambda: self._service.audio(track_id, owner))

    def delete(self, track_id: str, owner: UUID) -> None:
        """Delete one of the caller's uploaded tracks.

        Args:
            track_id: The upload to delete.
            owner: The signed-in user.

        Raises:
            HTTPException: The service's domain errors, mapped to HTTP status codes.
        """
        http_errors(lambda: self._service.delete(track_id, owner))
