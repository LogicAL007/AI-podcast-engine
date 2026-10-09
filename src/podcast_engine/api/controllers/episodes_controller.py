"""HTTP-facing orchestration for episodes: calls the service, maps its errors to HTTP."""

from uuid import UUID

from fastapi import HTTPException, Response, status

from podcast_engine.api.errors import DomainError, to_http
from podcast_engine.api.http_range import RangeNotSatisfiableError, parse_range
from podcast_engine.api.models.episodes_model import (
    AUDIO_MEDIA_TYPE,
    EpisodeRead,
    EpisodeScript,
    StageRunRead,
)
from podcast_engine.api.services.episodes_service import EpisodeService


class EpisodeController:
    def __init__(self, service: EpisodeService) -> None:
        self._service = service

    def start(self, show_id: UUID) -> EpisodeRead:
        try:
            return self._service.start(show_id)
        except DomainError as error:
            raise to_http(error) from error

    def get(self, episode_id: UUID) -> EpisodeRead:
        try:
            return self._service.get(episode_id)
        except DomainError as error:
            raise to_http(error) from error

    def list_for_show(self, show_id: UUID, *, limit: int, offset: int) -> list[EpisodeRead]:
        try:
            return self._service.list_for_show(show_id, limit=limit, offset=offset)
        except DomainError as error:
            raise to_http(error) from error

    def get_script(self, episode_id: UUID) -> EpisodeScript:
        try:
            return self._service.get_script(episode_id)
        except DomainError as error:
            raise to_http(error) from error

    def list_runs(self, episode_id: UUID) -> list[StageRunRead]:
        try:
            return self._service.list_runs(episode_id)
        except DomainError as error:
            raise to_http(error) from error

    def get_audio(self, episode_id: UUID, *, byte_range: str | None, download: bool) -> Response:
        """The episode WAV, whole (200) or the requested byte range (206), so players can seek."""
        try:
            audio = self._service.get_audio(episode_id)
        except DomainError as error:
            raise to_http(error) from error
        size = len(audio)
        disposition = "attachment" if download else "inline"
        headers = {
            "Accept-Ranges": "bytes",
            "Content-Disposition": f'{disposition}; filename="episode-{episode_id}.wav"',
            "Cache-Control": "private, max-age=3600",
        }
        try:
            span = parse_range(byte_range, size)
        except RangeNotSatisfiableError as error:
            raise HTTPException(
                status.HTTP_416_RANGE_NOT_SATISFIABLE,
                f"range {byte_range} is outside the {size}-byte file",
                headers={"Content-Range": f"bytes */{size}"},
            ) from error
        if span is None:
            return Response(audio, media_type=AUDIO_MEDIA_TYPE, headers=headers)
        first, last = span
        headers["Content-Range"] = f"bytes {first}-{last}/{size}"
        return Response(
            audio[first : last + 1],
            status_code=status.HTTP_206_PARTIAL_CONTENT,
            media_type=AUDIO_MEDIA_TYPE,
            headers=headers,
        )

    def get_notes(self, episode_id: UUID) -> str:
        try:
            return self._service.get_notes(episode_id)
        except DomainError as error:
            raise to_http(error) from error
