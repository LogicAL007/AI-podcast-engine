"""Routes for episodes: paths, status codes and OpenAPI metadata only."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Path, Query, Response, status

from podcast_engine.api.controllers.episodes_controller import EpisodeController
from podcast_engine.api.dependencies import get_episode_controller
from podcast_engine.api.models.episodes_model import (
    AUDIO_MEDIA_TYPE,
    NOTES_MEDIA_TYPE,
    EpisodeRead,
    EpisodeScript,
    StageRunRead,
)
from podcast_engine.api.openapi import errors, file_response

router = APIRouter(tags=["episodes"])

Controller = Annotated[EpisodeController, Depends(get_episode_controller)]
ShowId = Annotated[UUID, Path(description="The show's id")]
EpisodeId = Annotated[UUID, Path(description="The episode's id")]
Limit = Annotated[int, Query(ge=1, le=100, description="Most episodes to return")]
Offset = Annotated[int, Query(ge=0, description="Episodes to skip, for paging")]

AUDIO_HEADERS = {
    "Accept-Ranges": {
        "description": "Always `bytes`: ranges are supported",
        "schema": {"type": "string"},
    },
    "Content-Disposition": {
        "description": (
            "`inline` to play, or `attachment` with `?download=true`; filename `episode-<id>.wav`"
        ),
        "schema": {"type": "string"},
    },
}


@router.post(
    "/shows/{show_id}/episodes",
    response_model=EpisodeRead,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Start an episode",
    response_description="The new episode, `queued`; poll it for progress",
    responses=errors(
        e404="Show not found", e503="Job queue unavailable; the episode is marked `failed`"
    ),
)
def start_episode(show_id: ShowId, controller: Controller) -> EpisodeRead:
    """Create an episode and start generating it in the background. Returns at once, with the
    episode `queued`; its status shows progress.

    For a show that already has a published episode, this is a refresh: only segments whose
    sources changed are re-scripted and re-voiced, and if no source changed the episode ends as
    `unchanged`.
    """
    return controller.start(show_id)


@router.get(
    "/shows/{show_id}/episodes",
    response_model=list[EpisodeRead],
    summary="List a show's episodes",
    response_description="Episodes, newest first",
    responses=errors(e404="Show not found"),
)
def list_episodes(
    show_id: ShowId, controller: Controller, limit: Limit = 20, offset: Offset = 0
) -> list[EpisodeRead]:
    """A page of the show's episodes, newest first, each with its status and links."""
    return controller.list_for_show(show_id, limit=limit, offset=offset)


@router.get(
    "/episodes/{episode_id}",
    response_model=EpisodeRead,
    summary="Get an episode",
    response_description="The episode, its progress, and links to what it produced",
    responses=errors(e404="Episode not found"),
)
def get_episode(episode_id: EpisodeId, controller: Controller) -> EpisodeRead:
    """The episode's status, current stage and any error, with links to its audio, show notes,
    script, stage runs and feed. The audio and notes links are null until they exist."""
    return controller.get(episode_id)


@router.get(
    "/episodes/{episode_id}/script",
    response_model=EpisodeScript,
    summary="Get an episode's script",
    response_description="Segments and lines, with each claim's citations and verdict",
    responses=errors(e404="Episode not found"),
)
def get_episode_script(episode_id: EpisodeId, controller: Controller) -> EpisodeScript:
    """The script by segment. Each factual claim lists the passages it cites and the
    fact-check verdict, so it can be reviewed before or after voicing. Empty until the
    script stage has run."""
    return controller.get_script(episode_id)


@router.get(
    "/episodes/{episode_id}/runs",
    response_model=list[StageRunRead],
    summary="List an episode's stage runs",
    response_description="One record per completed stage, oldest first",
    responses=errors(e404="Episode not found"),
)
def list_episode_runs(episode_id: EpisodeId, controller: Controller) -> list[StageRunRead]:
    """How long each stage took and which model, prompt version and seed it used, so a run can be
    timed, costed and repeated (transparency and reproducibility requirements)."""
    return controller.list_runs(episode_id)


@router.get(
    "/episodes/{episode_id}/audio.wav",
    response_class=Response,
    summary="Get an episode's audio",
    responses={
        **file_response(AUDIO_MEDIA_TYPE, "The whole episode: 24 kHz mono 16-bit WAV", binary=True),
        206: {
            "description": "The requested byte range (`Content-Range` says which)",
            "content": {AUDIO_MEDIA_TYPE: {"schema": {"type": "string", "format": "binary"}}},
            "headers": {
                "Content-Range": {
                    "schema": {"type": "string"},
                    "description": "`bytes first-last/size`",
                }
            },
        },
        **errors(
            e404="Episode not found, or its audio is not assembled yet",
            e416="The range is outside the file; `Content-Range: bytes */size` gives the size",
        ),
    },
)
def get_episode_audio(
    episode_id: EpisodeId,
    controller: Controller,
    byte_range: Annotated[
        str | None,
        Header(
            alias="Range",
            description="Optional byte range, e.g. `bytes=0-` or `bytes=1000000-1999999`. "
            "Browsers and "
            "podcast apps send it to seek and resume.",
        ),
    ] = None,
    download: Annotated[
        bool, Query(description="`true` to save as a file (`Content-Disposition: attachment`)")
    ] = False,
) -> Response:
    """The finished episode audio, the same file the RSS feed points to.

    Supports HTTP range requests, so it plays and seeks in a browser `<audio>` element and in
    podcast apps. The AI-generated disclosure is the first thing spoken. Available once the
    assemble stage has run; 404 before then.
    """
    response = controller.get_audio(episode_id, byte_range=byte_range, download=download)
    response.headers.setdefault("Accept-Ranges", "bytes")
    return response


get_episode_audio_head = router.api_route(
    "/episodes/{episode_id}/audio.wav",
    methods=["HEAD"],
    response_class=Response,
    summary="Check an episode's audio",
    description="Headers only (size, ranges, disposition), without the body.",
    responses={
        200: {"description": "The audio exists", "headers": AUDIO_HEADERS},
        **errors(e404="Not available"),
    },
    name="head_episode_audio",
)(get_episode_audio)


@router.get(
    "/episodes/{episode_id}/notes.md",
    response_class=Response,
    summary="Get an episode's show notes",
    responses={
        **file_response(NOTES_MEDIA_TYPE, "Show notes in Markdown", binary=False),
        **errors(e404="Episode not found, or not published yet"),
    },
)
def get_episode_notes(episode_id: EpisodeId, controller: Controller) -> Response:
    """Markdown show notes: the AI-generated disclosure first, then chapters with their start times,
    each claim with its citation numbers, the numbered sources, the source attribution, and how the
    episode was made (models, prompts, voices, seed). Available once the episode is published."""
    return Response(content=controller.get_notes(episode_id), media_type=NOTES_MEDIA_TYPE)
