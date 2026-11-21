"""HTTP-facing orchestration for the music library: calls the service, maps its errors to HTTP."""

from uuid import UUID

from podcast_engine.api.errors import http_errors
from podcast_engine.api.models.music_model import MusicTrackRead
from podcast_engine.api.services.music_service import MAX_BYTES, MusicService
from podcast_engine.common.music import Role


class MusicController:
    max_bytes = MAX_BYTES

    def __init__(self, service: MusicService) -> None:
        self._service = service

    def list_all(self, owner: UUID) -> list[MusicTrackRead]:
        return http_errors(lambda: self._service.list_all(owner))

    def upload(
        self, owner: UUID, *, name: str, role: Role, credit: str, rights: bool, data: bytes
    ) -> MusicTrackRead:
        return http_errors(
            lambda: self._service.upload(
                owner, name=name, role=role, credit=credit, rights=rights, data=data
            )
        )

    def audio(self, track_id: str, owner: UUID) -> bytes:
        return http_errors(lambda: self._service.audio(track_id, owner))

    def delete(self, track_id: str, owner: UUID) -> None:
        http_errors(lambda: self._service.delete(track_id, owner))
