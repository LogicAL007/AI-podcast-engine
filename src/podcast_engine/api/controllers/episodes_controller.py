"""HTTP-facing orchestration for episodes: calls the service, maps its errors to HTTP."""

from uuid import UUID

from fastapi import HTTPException, Response, status
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool

from podcast_engine.api.errors import NotFoundError, http_errors, to_http
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
from podcast_engine.api.services.episodes_service import (
    EpisodeLoader,
    EpisodeService,
    ProgressPacing,
    stream_progress,
)
from podcast_engine.common.models import EpisodeStatus


class EpisodeController:
    def __init__(self, service: EpisodeService) -> None:
        self._service = service

    def start(self, show_id: UUID, owner: UUID, *, rebuild: bool = False) -> EpisodeRead:
        return http_errors(lambda: self._service.start(show_id, owner, rebuild=rebuild))

    def get(self, episode_id: UUID, owner: UUID) -> EpisodeRead:
        return http_errors(lambda: self._service.get(episode_id, owner))

    def list_for_show(
        self, show_id: UUID, owner: UUID, *, status: EpisodeStatus | None, limit: int, offset: int
    ) -> Paged[EpisodeRead]:
        return http_errors(
            lambda: self._service.list_for_show(
                show_id, owner, status=status, limit=limit, offset=offset
            )
        )

    def list_all(
        self,
        owner: UUID,
        *,
        status: EpisodeStatus | None,
        show_id: UUID | None,
        limit: int,
        offset: int,
    ) -> Paged[EpisodeRead]:
        return http_errors(
            lambda: self._service.list_all(
                owner, status=status, show_id=show_id, limit=limit, offset=offset
            )
        )

    def get_script(self, episode_id: UUID, owner: UUID) -> EpisodeScript:
        return http_errors(lambda: self._service.get_script(episode_id, owner))

    def edit_script(self, episode_id: UUID, owner: UUID, edit: ScriptEdit) -> EpisodeRead:
        return http_errors(lambda: self._service.edit_script(episode_id, owner, edit))

    def approve(self, episode_id: UUID, owner: UUID) -> EpisodeRead:
        return http_errors(lambda: self._service.approve(episode_id, owner))

    def retry(self, episode_id: UUID, owner: UUID) -> EpisodeRead:
        return http_errors(lambda: self._service.retry(episode_id, owner))

    def cancel(self, episode_id: UUID, owner: UUID) -> EpisodeRead:
        return http_errors(lambda: self._service.cancel(episode_id, owner))

    def delete(self, episode_id: UUID, owner: UUID) -> None:
        http_errors(lambda: self._service.delete(episode_id, owner))

    def list_runs(
        self, episode_id: UUID, owner: UUID, *, limit: int, offset: int
    ) -> Paged[StageRunRead]:
        return http_errors(
            lambda: self._service.list_runs(episode_id, owner, limit=limit, offset=offset)
        )

    def list_claims(
        self,
        episode_id: UUID,
        owner: UUID,
        *,
        supported: bool | None,
        segment: int | None,
        limit: int,
        offset: int,
    ) -> Paged[ClaimDetail]:
        return http_errors(
            lambda: self._service.list_claims(
                episode_id, owner, supported=supported, segment=segment, limit=limit, offset=offset
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


EVENT_STREAM = "text/event-stream"


async def follow_progress(
    episode_id: UUID, owner: UUID, load: EpisodeLoader, pacing: ProgressPacing
) -> StreamingResponse:
    """The episode's progress as server-sent events. Each check runs the (blocking) database
    read in a worker thread, so an open stream holds neither a thread nor a connection."""

    async def load_once() -> EpisodeRead | None:
        return await run_in_threadpool(load, episode_id, owner)

    if await load_once() is None:  # someone else's episode is not found, as everywhere else
        raise to_http(NotFoundError("episode", episode_id))
    return StreamingResponse(
        stream_progress(load_once, pacing),
        media_type=EVENT_STREAM,
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},  # nginx: don't buffer
    )
