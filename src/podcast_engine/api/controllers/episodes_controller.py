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
    """HTTP-facing entry point for episodes: calls the service and maps its errors to HTTP."""

    def __init__(self, service: EpisodeService) -> None:
        """Create the controller.

        Args:
            service: The episode service holding the business rules.
        """
        self._service = service

    def start(self, show_id: UUID, owner: UUID, *, rebuild: bool = False) -> EpisodeRead:
        """Start a new episode of one of the caller's shows.

        Args:
            show_id: The show.
            owner: The signed-in user.
            rebuild: Regenerate every segment, not only those whose sources changed.

        Returns:
            The queued episode.

        Raises:
            HTTPException: The service's domain errors, mapped to HTTP status codes.
        """
        return http_errors(lambda: self._service.start(show_id, owner, rebuild=rebuild))

    def get(self, episode_id: UUID, owner: UUID) -> EpisodeRead:
        """Return one of the caller's episodes.

        Args:
            episode_id: The episode.
            owner: The signed-in user.

        Returns:
            The episode and its progress.

        Raises:
            HTTPException: The service's domain errors, mapped to HTTP status codes.
        """
        return http_errors(lambda: self._service.get(episode_id, owner))

    def list_for_show(
        self, show_id: UUID, owner: UUID, *, status: EpisodeStatus | None, limit: int, offset: int
    ) -> Paged[EpisodeRead]:
        """Return one page of a show's episodes, newest first.

        Args:
            show_id: The show.
            owner: The signed-in user.
            status: Only episodes with this status, or all when None.
            limit: Most episodes to return.
            offset: Episodes to skip before this page.

        Returns:
            The page of episodes and the total.

        Raises:
            HTTPException: The service's domain errors, mapped to HTTP status codes.
        """
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
        """Return one page of the caller's episodes across shows, newest first.

        Args:
            owner: The signed-in user.
            status: Only episodes with this status, or all when None.
            show_id: Only this show's episodes, or all when None.
            limit: Most episodes to return.
            offset: Episodes to skip before this page.

        Returns:
            The page of episodes and the total.

        Raises:
            HTTPException: The service's domain errors, mapped to HTTP status codes.
        """
        return http_errors(
            lambda: self._service.list_all(
                owner, status=status, show_id=show_id, limit=limit, offset=offset
            )
        )

    def get_script(self, episode_id: UUID, owner: UUID) -> EpisodeScript:
        """Return an episode's script, with its claims and citations.

        Args:
            episode_id: The episode.
            owner: The signed-in user.

        Returns:
            The script.

        Raises:
            HTTPException: The service's domain errors, mapped to HTTP status codes.
        """
        return http_errors(lambda: self._service.get_script(episode_id, owner))

    def edit_script(self, episode_id: UUID, owner: UUID, edit: ScriptEdit) -> EpisodeRead:
        """Replace lines of a script waiting for review, then fact-check it again.

        Args:
            episode_id: The episode.
            owner: The signed-in user.
            edit: The lines to change.

        Returns:
            The episode after the edit.

        Raises:
            HTTPException: The service's domain errors, mapped to HTTP status codes.
        """
        return http_errors(lambda: self._service.edit_script(episode_id, owner, edit))

    def approve(self, episode_id: UUID, owner: UUID) -> EpisodeRead:
        """Release an episode waiting for review to voicing, as it is.

        Args:
            episode_id: The episode.
            owner: The signed-in user.

        Returns:
            The episode, queued for voicing.

        Raises:
            HTTPException: The service's domain errors, mapped to HTTP status codes.
        """
        return http_errors(lambda: self._service.approve(episode_id, owner))

    def remix(self, episode_id: UUID, owner: UUID) -> EpisodeRead:
        """Re-mix a published episode's audio with the show's current effects and music.

        Args:
            episode_id: The episode.
            owner: The signed-in user.

        Returns:
            The episode, queued for assembly.

        Raises:
            HTTPException: The service's domain errors, mapped to HTTP status codes.
        """
        return http_errors(lambda: self._service.remix(episode_id, owner))

    def retry(self, episode_id: UUID, owner: UUID) -> EpisodeRead:
        """Run a failed or cancelled episode again from the stage it stopped at.

        Args:
            episode_id: The episode.
            owner: The signed-in user.

        Returns:
            The episode, queued again.

        Raises:
            HTTPException: The service's domain errors, mapped to HTTP status codes.
        """
        return http_errors(lambda: self._service.retry(episode_id, owner))

    def cancel(self, episode_id: UUID, owner: UUID) -> EpisodeRead:
        """Stop an episode that is still being made.

        Args:
            episode_id: The episode.
            owner: The signed-in user.

        Returns:
            The cancelled episode.

        Raises:
            HTTPException: The service's domain errors, mapped to HTTP status codes.
        """
        return http_errors(lambda: self._service.cancel(episode_id, owner))

    def delete(self, episode_id: UUID, owner: UUID) -> None:
        """Delete one of the caller's episodes and its files.

        Args:
            episode_id: The episode.
            owner: The signed-in user.

        Raises:
            HTTPException: The service's domain errors, mapped to HTTP status codes.
        """
        http_errors(lambda: self._service.delete(episode_id, owner))

    def list_runs(
        self, episode_id: UUID, owner: UUID, *, limit: int, offset: int
    ) -> Paged[StageRunRead]:
        """Return one page of an episode's stage runs.

        Args:
            episode_id: The episode.
            owner: The signed-in user.
            limit: Most runs to return.
            offset: Runs to skip before this page.

        Returns:
            The page of runs and the total.

        Raises:
            HTTPException: The service's domain errors, mapped to HTTP status codes.
        """
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
        """Return one page of an episode's claims, with their verdicts.

        Args:
            episode_id: The episode.
            owner: The signed-in user.
            supported: Only supported (True) or unsupported (False) claims, or all when None.
            segment: Only this segment's claims, or all when None.
            limit: Most claims to return.
            offset: Claims to skip before this page.

        Returns:
            The page of claims and the total.

        Raises:
            HTTPException: The service's domain errors, mapped to HTTP status codes.
        """
        return http_errors(
            lambda: self._service.list_claims(
                episode_id, owner, supported=supported, segment=segment, limit=limit, offset=offset
            )
        )

    def get_audio(self, episode_id: UUID, *, byte_range: str | None, download: bool) -> Response:
        """Return the episode's WAV, whole or the requested byte range, so players can seek.

        Args:
            episode_id: The episode.
            byte_range: The request's ``Range`` header, or None.
            download: Whether to save it as a file instead of playing it.

        Returns:
            The whole file (200) or the range (206), cacheable privately for an hour.

        Raises:
            HTTPException: 404 when the audio is not assembled yet; 416 when the range is outside
                the file.
        """
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
        """Return a published episode's show notes.

        Args:
            episode_id: The episode.

        Returns:
            The notes as Markdown.

        Raises:
            HTTPException: The service's domain errors, mapped to HTTP status codes.
        """
        return http_errors(lambda: self._service.get_notes(episode_id))


EVENT_STREAM = "text/event-stream"


async def follow_progress(
    episode_id: UUID, owner: UUID, load: EpisodeLoader, pacing: ProgressPacing
) -> StreamingResponse:
    """Stream an episode's progress as server-sent events.

    Each check runs the (blocking) database read in a worker thread, so an open stream holds neither
    a thread nor a connection. Someone else's episode is not found, as everywhere else. nginx is
    told not to buffer the stream.

    Args:
        episode_id: The episode.
        owner: The signed-in user.
        load: Reads the episode for its owner, or None when it is not theirs.
        pacing: How often to check, and when to give up.

    Returns:
        The event stream.

    Raises:
        HTTPException: 404 when the episode is not the caller's.
    """

    async def load_once() -> EpisodeRead | None:
        """Read the episode once, in a worker thread.

        Returns:
            The episode, or None when it is not the caller's.
        """
        return await run_in_threadpool(load, episode_id, owner)

    if await load_once() is None:
        raise to_http(NotFoundError("episode", episode_id))
    return StreamingResponse(
        stream_progress(load_once, pacing),
        media_type=EVENT_STREAM,
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )
