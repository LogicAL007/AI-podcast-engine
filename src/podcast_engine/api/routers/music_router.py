from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Path, Response, UploadFile, status

from podcast_engine.api.controllers.music_controller import MusicController
from podcast_engine.api.dependencies import CurrentUserDep, get_music_controller
from podcast_engine.api.models.music_model import MusicTrackRead
from podcast_engine.api.openapi import errors, file_response
from podcast_engine.common.music import Role

router = APIRouter(prefix="/music", tags=["music"])

Controller = Annotated[MusicController, Depends(get_music_controller)]
TrackId = Annotated[
    str,
    Path(
        description="`builtin:...` or the id of a track you uploaded",
        pattern=r"^(builtin:[a-z0-9-]{1,40}|[0-9a-fA-F-]{36})$",
    ),
]
NOT_FOUND = errors(e404="Track not found")


@router.get(
    "",
    response_model=list[MusicTrackRead],
    summary="List the music library",
    response_description="The built-in tracks, then yours, newest first",
)
def list_music(me: CurrentUserDep, controller: Controller) -> list[MusicTrackRead]:
    """Every track a show can use.

    The built-in ones (made in the app, free to use) and the ones you uploaded.

    \f

    Args:
        me: The signed-in user.
        controller: The music controller, injected by FastAPI.

    Returns:
        The built-in tracks, then yours, newest first.
    """
    return controller.list_all(me.user_id)


@router.post(
    "",
    response_model=MusicTrackRead,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a track",
    response_description="The uploaded track",
    responses=errors(
        e409="The account already has the most tracks allowed",
        e413="The file is larger than the limit",
        e415="Not a 24 kHz mono 16-bit WAV",
        e422="Rights not confirmed, or the track is too short, long or silent",
    ),
)
def upload_music(
    me: CurrentUserDep,
    controller: Controller,
    audio: Annotated[UploadFile, File(description="24 kHz mono 16-bit WAV, 1 s to 6 minutes")],
    name: Annotated[str, Form(description="A name for the track")],
    rights: Annotated[
        bool, Form(description="You own this music or have a licence to use it in your podcast")
    ],
    role: Annotated[Role, Form(description="bed, intro, outro, sting or any")] = "any",
    credit: Annotated[
        str, Form(description="Credit line for the show notes, if the licence asks for one")
    ] = "",
) -> MusicTrackRead:
    """Add a track to your library, for your shows' intros, outros, stings and beds.

    You must confirm you have the right to use it.

    \f

    Args:
        me: The signed-in user.
        controller: The music controller, injected by FastAPI.
        audio: The track as 24 kHz mono 16-bit WAV; reading stops one byte past the limit, which is
            enough to refuse it.
        name: A name for the track.
        rights: Whether you own the music or have a licence to use it.
        role: What the track is for: bed, intro, outro, sting or any.
        credit: Credit line for the show notes, if the licence asks for one.

    Returns:
        The uploaded track.
    """
    data = audio.file.read(controller.max_bytes + 1)
    return controller.upload(
        me.user_id, name=name, role=role, credit=credit, rights=rights, data=data
    )


@router.get(
    "/{track_id}/audio.wav",
    summary="Play a track",
    response_class=Response,
    responses={**file_response("audio/wav", "The track", binary=True), **NOT_FOUND},
)
def music_audio(track_id: TrackId, me: CurrentUserDep, controller: Controller) -> Response:
    """A track's audio (24 kHz mono WAV): a built-in one, or one of yours.

    \f

    Args:
        track_id: ``builtin:...`` or the id of a track you uploaded.
        me: The signed-in user.
        controller: The music controller, injected by FastAPI.

    Returns:
        The WAV file, cacheable privately for an hour.
    """
    return Response(
        controller.audio(track_id, me.user_id),
        media_type="audio/wav",
        headers={"Cache-Control": "private, max-age=3600"},
    )


@router.delete(
    "/{track_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a track you uploaded",
    responses={**NOT_FOUND, **errors(e409="Built-in tracks cannot be deleted")},
)
def delete_music(track_id: TrackId, me: CurrentUserDep, controller: Controller) -> None:
    """Delete one of your tracks.

    Shows that used it go back to the default for that slot; episodes already made keep their audio.

    \f

    Args:
        track_id: The track to delete.
        me: The signed-in user.
        controller: The music controller, injected by FastAPI.
    """
    controller.delete(track_id, me.user_id)
