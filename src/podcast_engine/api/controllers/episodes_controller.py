"""HTTP-facing orchestration for episodes: calls the service, maps its errors to HTTP."""

from uuid import UUID

from fastapi import HTTPException, Response, status

from podcast_engine.api.errors import http_errors
from podcast_engine.api.http_range import RangeNotSatisfiableError, parse_range
from podcast_engine.api.models.episodes_model import (
    AUDIO_MEDIA_TYPE,
    ClaimDetail,
    EpisodeRead,
    EpisodeScript,
    ScriptEdit,
    StageRunRead,
)
from podcast_engine.api.models.pagination_model import Paged
from podcast_engine.api.services.episodes_service import EpisodeService
from podcast_engine.common.models import EpisodeStatus


class EpisodeController:
    def __init__(self, service: EpisodeService) -> None:
        self._service = service

    def start(self, show_id: UUID) -> EpisodeRead:
        return http_errors(lambda: self._service.start(show_id))

    def get(self, episode_id: UUID) -> EpisodeRead:
        return http_errors(lambda: self._service.get(episode_id))

    def list_for_show(
        self, show_id: UUID, *, status: EpisodeStatus | None, limit: int, offset: int
    ) -> Paged[EpisodeRead]:
        return http_errors(
            lambda: self._service.list_for_show(show_id, status=status, limit=limit, offset=offset)
        )

    def list_all(
        self, *, status: EpisodeStatus | None, show_id: UUID | None, limit: int, offset: int
    ) -> Paged[EpisodeRead]:
        return http_errors(
            lambda: self._service.list_all(
                status=status, show_id=show_id, limit=limit, offset=offset
            )
        )

    def get_script(self, episode_id: UUID) -> EpisodeScript:
        return http_errors(lambda: self._service.get_script(episode_id))

    def edit_script(self, episode_id: UUID, edit: ScriptEdit) -> EpisodeRead:
        return http_errors(lambda: self._service.edit_script(episode_id, edit))

    def approve(self, episode_id: UUID) -> EpisodeRead:
        return http_errors(lambda: self._service.approve(episode_id))

    def retry(self, episode_id: UUID) -> EpisodeRead:
        return http_errors(lambda: self._service.retry(episode_id))

    def cancel(self, episode_id: UUID) -> EpisodeRead:
        return http_errors(lambda: self._service.cancel(episode_id))

    def delete(self, episode_id: UUID) -> None:
        http_errors(lambda: self._service.delete(episode_id))

    def list_runs(self, episode_id: UUID, *, limit: int, offset: int) -> Paged[StageRunRead]:
        return http_errors(lambda: self._service.list_runs(episode_id, limit=limit, offset=offset))

    def list_claims(
        self,
        episode_id: UUID,
        *,
        supported: bool | None,
        segment: int | None,
        limit: int,
        offset: int,
    ) -> Paged[ClaimDetail]:
        return http_errors(
            lambda: self._service.list_claims(
                episode_id, supported=supported, segment=segment, limit=limit, offset=offset
            )
        )

    def get_audio(self, episode_id: UUID, *, byte_range: str | None, download: bool) -> Response:
        """The episode WAV, whole (200) or the requested byte range (206), so players can seek."""
        audio = http_errors(lambda: self._service.get_audio(episode_id))
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
        return http_errors(lambda: self._service.get_notes(episode_id))
