from uuid import UUID

from podcast_engine.api.errors import http_errors
from podcast_engine.api.models.speech_model import SpeechClipRead, SpeechCreate, SpeechEngine
from podcast_engine.api.services.speech_service import SpeechService


class SpeechController:
    """HTTP-facing entry point for type-to-speech: calls the service and maps its errors to HTTP."""

    def __init__(self, service: SpeechService) -> None:
        """Create the controller.

        Args:
            service: The type-to-speech service.
        """
        self._service = service

    def engine(self) -> SpeechEngine:
        """Report which voices this server can speak with.

        Returns:
            The TTS backend, whether recorded voices work, the prebuilt voices and today's TTS
            budget.

        Raises:
            HTTPException: The service's domain errors, mapped to HTTP status codes.
        """
        return http_errors(self._service.engine)

    def create(self, owner: UUID, data: SpeechCreate) -> SpeechClipRead:
        """Queue a line of text to be voiced.

        Args:
            owner: The signed-in user.
            data: The text, the voice, the delivery and any effects.

        Returns:
            The queued clip.

        Raises:
            HTTPException: The service's domain errors, mapped to HTTP status codes.
        """
        return http_errors(lambda: self._service.create(owner, data))

    def recent(self, owner: UUID) -> list[SpeechClipRead]:
        """Return the caller's most recent clips.

        Args:
            owner: The signed-in user.

        Returns:
            The clips, newest first.

        Raises:
            HTTPException: The service's domain errors, mapped to HTTP status codes.
        """
        return http_errors(lambda: self._service.recent(owner))

    def get(self, clip_id: UUID, owner: UUID) -> SpeechClipRead:
        """Return one of the caller's clips.

        Args:
            clip_id: The clip to return.
            owner: The signed-in user.

        Returns:
            The clip and its status.

        Raises:
            HTTPException: The service's domain errors, mapped to HTTP status codes.
        """
        return http_errors(lambda: self._service.get(clip_id, owner))

    def audio(self, clip_id: UUID, owner: UUID) -> bytes:
        """Return a finished clip's audio.

        Args:
            clip_id: The clip whose audio to return.
            owner: The signed-in user.

        Returns:
            The clip as WAV bytes.

        Raises:
            HTTPException: The service's domain errors, mapped to HTTP status codes.
        """
        return http_errors(lambda: self._service.audio(clip_id, owner))

    def delete(self, clip_id: UUID, owner: UUID) -> None:
        """Delete one of the caller's clips and its audio.

        Args:
            clip_id: The clip to delete.
            owner: The signed-in user.

        Raises:
            HTTPException: The service's domain errors, mapped to HTTP status codes.
        """
        http_errors(lambda: self._service.delete(clip_id, owner))
