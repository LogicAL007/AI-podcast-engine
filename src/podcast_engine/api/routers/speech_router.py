"""Routes for type-to-speech: paths, status codes and OpenAPI metadata only."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query, Response, status

from podcast_engine.api.controllers.speech_controller import SpeechController
from podcast_engine.api.dependencies import CurrentUserDep, get_speech_controller
from podcast_engine.api.models.speech_model import SpeechClipRead, SpeechCreate, SpeechEngine
from podcast_engine.api.openapi import errors, file_response

router = APIRouter(prefix="/speech", tags=["speech"])

Controller = Annotated[SpeechController, Depends(get_speech_controller)]
ClipId = Annotated[UUID, Path(description="The clip's id")]
NOT_FOUND = errors(e404="Clip not found")


@router.get(
    "/engine",
    response_model=SpeechEngine,
    summary="What the voice engine can say",
    response_description="The engine, its voices, effect presets and today's budget",
)
def speech_engine(me: CurrentUserDep, controller: Controller) -> SpeechEngine:  # noqa: ARG001
    """Which voices can speak on this server: recorded voices need the Chatterbox engine; the
    engine's own voices always work. With Gemini, each clip spends the shared daily budget."""
    return controller.engine()


@router.post(
    "",
    response_model=SpeechClipRead,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Voice a line",
    response_description="The clip, queued for the voice worker",
    responses=errors(
        e404="The recorded voice is not one of yours",
        e429="The hourly clip limit, or today's Gemini voice budget for clips, is used up",
    ),
)
def create_clip(data: SpeechCreate, me: CurrentUserDep, controller: Controller) -> SpeechClipRead:
    """Queue a line to be voiced in a recorded voice or one of the engine's own, with voice
    effects. Poll `GET /speech/{clip_id}` until it is `done`, then play `audio`."""
    return controller.create(me.user_id, data)


@router.get(
    "",
    response_model=list[SpeechClipRead],
    summary="List your recent clips",
    response_description="Your 20 most recent clips, newest first",
)
def list_clips(me: CurrentUserDep, controller: Controller) -> list[SpeechClipRead]:
    """Your most recent type-to-speech clips, newest first."""
    return controller.recent(me.user_id)


@router.get(
    "/{clip_id}",
    response_model=SpeechClipRead,
    summary="Get a clip",
    response_description="The clip and its status",
    responses=NOT_FOUND,
)
def get_clip(clip_id: ClipId, me: CurrentUserDep, controller: Controller) -> SpeechClipRead:
    """One of your clips, with its status."""
    return controller.get(clip_id, me.user_id)


@router.get(
    "/{clip_id}/audio.wav",
    summary="Play or download a clip",
    response_class=Response,
    responses={**file_response("audio/wav", "The clip", binary=True), **NOT_FOUND},
)
def clip_audio(
    clip_id: ClipId,
    me: CurrentUserDep,
    controller: Controller,
    download: Annotated[
        bool, Query(description="Save as a file (`attachment`) instead of playing it")
    ] = False,
) -> Response:
    """The clip's audio (24 kHz mono WAV), for its owner only."""
    disposition = "attachment" if download else "inline"
    return Response(
        controller.audio(clip_id, me.user_id),
        media_type="audio/wav",
        headers={
            "Cache-Control": "private, no-store",
            "Content-Disposition": f'{disposition}; filename="speech-{clip_id}.wav"',
        },
    )


@router.delete(
    "/{clip_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a clip",
    responses=NOT_FOUND,
)
def delete_clip(clip_id: ClipId, me: CurrentUserDep, controller: Controller) -> None:
    """Delete a clip and its audio."""
    controller.delete(clip_id, me.user_id)
