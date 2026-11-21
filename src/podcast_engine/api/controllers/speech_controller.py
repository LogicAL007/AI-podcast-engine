"""HTTP-facing orchestration for type-to-speech: calls the service, maps its errors to HTTP."""

from uuid import UUID

from podcast_engine.api.errors import http_errors
from podcast_engine.api.models.speech_model import SpeechClipRead, SpeechCreate, SpeechEngine
from podcast_engine.api.services.speech_service import SpeechService


class SpeechController:
    def __init__(self, service: SpeechService) -> None:
        self._service = service

    def engine(self) -> SpeechEngine:
        return http_errors(self._service.engine)

    def create(self, owner: UUID, data: SpeechCreate) -> SpeechClipRead:
        return http_errors(lambda: self._service.create(owner, data))

    def recent(self, owner: UUID) -> list[SpeechClipRead]:
        return http_errors(lambda: self._service.recent(owner))

    def get(self, clip_id: UUID, owner: UUID) -> SpeechClipRead:
        return http_errors(lambda: self._service.get(clip_id, owner))

    def audio(self, clip_id: UUID, owner: UUID) -> bytes:
        return http_errors(lambda: self._service.audio(clip_id, owner))

    def delete(self, clip_id: UUID, owner: UUID) -> None:
        http_errors(lambda: self._service.delete(clip_id, owner))
