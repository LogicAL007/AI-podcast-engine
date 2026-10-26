"""HTTP-facing orchestration for cloned voices: calls the service, maps its errors to HTTP."""

from uuid import UUID

from podcast_engine.api.errors import http_errors
from podcast_engine.api.models.pagination_model import Paged
from podcast_engine.api.models.voices_model import ConsentForm, VoiceRead, VoiceSource
from podcast_engine.api.services.voices_service import MAX_BYTES, VoiceService


class VoiceController:
    max_bytes = MAX_BYTES

    def __init__(self, service: VoiceService) -> None:
        self._service = service

    def register(
        self, owner: UUID, form: ConsentForm, *, source: VoiceSource, data: bytes
    ) -> VoiceRead:
        return http_errors(lambda: self._service.register(owner, form, source=source, data=data))

    def list_page(self, owner: UUID, *, limit: int, offset: int) -> Paged[VoiceRead]:
        return http_errors(lambda: self._service.list_page(owner, limit=limit, offset=offset))

    def get(self, voice_id: UUID, owner: UUID) -> VoiceRead:
        return http_errors(lambda: self._service.get(voice_id, owner))

    def audio(self, voice_id: UUID, owner: UUID) -> bytes:
        return http_errors(lambda: self._service.audio(voice_id, owner))

    def delete(self, voice_id: UUID, owner: UUID) -> None:
        http_errors(lambda: self._service.delete(voice_id, owner))
