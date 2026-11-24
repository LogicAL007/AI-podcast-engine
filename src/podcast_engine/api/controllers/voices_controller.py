from uuid import UUID

from podcast_engine.api.errors import http_errors
from podcast_engine.api.models.pagination_model import Paged
from podcast_engine.api.models.voices_model import ConsentForm, VoiceRead, VoiceSource
from podcast_engine.api.services.voices_service import MAX_BYTES, VoiceService


class VoiceController:
    """HTTP-facing entry point for cloned voices: calls the service and maps its errors to HTTP."""

    max_bytes = MAX_BYTES

    def __init__(self, service: VoiceService) -> None:
        """Create the controller.

        Args:
            service: The voice service holding the consent and storage rules.
        """
        self._service = service

    def register(
        self, owner: UUID, form: ConsentForm, *, source: VoiceSource, data: bytes
    ) -> VoiceRead:
        """Register a cloned voice from a recording and its signed consent.

        Args:
            owner: The signed-in user registering the voice.
            form: The consent form: who is speaking and what they agreed to.
            source: Whether the audio was recorded in the browser or uploaded.
            data: The recording, as WAV bytes.

        Returns:
            The registered voice.

        Raises:
            HTTPException: The service's domain errors, mapped to HTTP status codes.
        """
        return http_errors(lambda: self._service.register(owner, form, source=source, data=data))

    def list_page(self, owner: UUID, *, limit: int, offset: int) -> Paged[VoiceRead]:
        """Return one page of the caller's voices, newest first.

        Args:
            owner: The signed-in user.
            limit: Most voices to return.
            offset: Voices to skip before this page.

        Returns:
            The page of voices and the total across all pages.

        Raises:
            HTTPException: The service's domain errors, mapped to HTTP status codes.
        """
        return http_errors(lambda: self._service.list_page(owner, limit=limit, offset=offset))

    def get(self, voice_id: UUID, owner: UUID) -> VoiceRead:
        """Return one of the caller's voices.

        Args:
            voice_id: The voice to return.
            owner: The signed-in user.

        Returns:
            The voice and its consent record.

        Raises:
            HTTPException: The service's domain errors, mapped to HTTP status codes.
        """
        return http_errors(lambda: self._service.get(voice_id, owner))

    def audio(self, voice_id: UUID, owner: UUID) -> bytes:
        """Return a voice's original recording.

        Args:
            voice_id: The voice whose recording to return.
            owner: The signed-in user.

        Returns:
            The recording as WAV bytes.

        Raises:
            HTTPException: The service's domain errors, mapped to HTTP status codes.
        """
        return http_errors(lambda: self._service.audio(voice_id, owner))

    def delete(self, voice_id: UUID, owner: UUID) -> None:
        """Delete one of the caller's voices and its recording.

        Args:
            voice_id: The voice to delete.
            owner: The signed-in user.

        Raises:
            HTTPException: The service's domain errors, mapped to HTTP status codes.
        """
        http_errors(lambda: self._service.delete(voice_id, owner))
