from typing import Annotated
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Path, Query, Response

from podcast_engine.api.controllers.episodes_controller import EpisodeController
from podcast_engine.api.controllers.uploads_controller import UploadController
from podcast_engine.api.dependencies import get_episode_controller, get_upload_controller
from podcast_engine.api.models.episodes_model import AUDIO_MEDIA_TYPE, NOTES_MEDIA_TYPE
from podcast_engine.api.models.uploads_model import PDF_MEDIA_TYPE
from podcast_engine.api.openapi import errors, file_response

router = APIRouter()

Controller = Annotated[EpisodeController, Depends(get_episode_controller)]
Uploads = Annotated[UploadController, Depends(get_upload_controller)]
EpisodeId = Annotated[UUID, Path(description="The episode's id")]
ShowId = Annotated[UUID, Path(description="The show's id")]
UploadId = Annotated[UUID, Path(description="The upload's id")]
NOT_FOUND = errors(e404="Show or upload not found")

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


@router.get(
    "/episodes/{episode_id}/audio.wav",
    tags=["episodes"],
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
            description=(
                "Optional byte range, e.g. `bytes=0-` or `bytes=1000000-1999999`. Browsers and "
                "podcast apps send it to seek and resume."
            ),
        ),
    ] = None,
    download: Annotated[
        bool, Query(description="`true` to save as a file (`Content-Disposition: attachment`)")
    ] = False,
) -> Response:
    """The finished episode audio, the same file the RSS feed points to.

    Supports HTTP range requests, so it plays and seeks in a browser `<audio>` element and in
    podcast apps. The AI-generated disclosure is the first thing spoken. Available once the assemble
    stage has run; 404 before then.

    Open without login, like the feed, notes and uploaded PDFs: podcast apps send no credentials,
    and the URL's random id reveals nothing else.

    \f

    Args:
        episode_id: The episode.
        controller: The episode controller, injected by FastAPI.
        byte_range: The ``Range`` header, if the client sent one.
        download: Whether to save the audio as a file instead of playing it.

    Returns:
        The whole file, or the requested range with status 206.
    """
    response = controller.get_audio(episode_id, byte_range=byte_range, download=download)
    response.headers.setdefault("Accept-Ranges", "bytes")
    return response


get_episode_audio_head = router.api_route(
    "/episodes/{episode_id}/audio.wav",
    methods=["HEAD"],
    tags=["episodes"],
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
    tags=["episodes"],
    response_class=Response,
    summary="Get an episode's show notes",
    responses={
        **file_response(NOTES_MEDIA_TYPE, "Show notes in Markdown", binary=False),
        **errors(e404="Episode not found, or not published yet"),
    },
)
def get_episode_notes(episode_id: EpisodeId, controller: Controller) -> Response:
    """Markdown show notes, available once the episode is published.

    The AI-generated disclosure first, then chapters with their start times, each claim with its
    citation numbers, the numbered sources, the source attribution, and how the episode was made
    (models, prompts, voices, seed).

    \f

    Args:
        episode_id: The episode.
        controller: The episode controller, injected by FastAPI.

    Returns:
        The notes as Markdown.
    """
    return Response(content=controller.get_notes(episode_id), media_type=NOTES_MEDIA_TYPE)


@router.get(
    "/shows/{show_id}/uploads/{upload_id}/file",
    tags=["uploads"],
    response_class=Response,
    summary="Download an uploaded file",
    responses={**file_response(PDF_MEDIA_TYPE, "The PDF", binary=True), **NOT_FOUND},
)
def download_upload(show_id: ShowId, upload_id: UploadId, controller: Uploads) -> Response:
    """The uploaded PDF, as it was uploaded.

    Show-note citations of uploaded sources link here, with `#page=N` so a PDF viewer opens at the
    cited page.

    \f

    Args:
        show_id: The show it belongs to.
        upload_id: The upload.
        controller: The upload controller, injected by FastAPI.

    Returns:
        The PDF, shown inline with its original file name.
    """
    content = controller.get_file(show_id, upload_id)
    return Response(
        content.data,
        media_type=content.content_type,
        headers={"Content-Disposition": f"inline; filename*=UTF-8''{quote(content.filename)}"},
    )
