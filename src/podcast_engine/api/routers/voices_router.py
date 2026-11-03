"""Routes for cloned voices: paths, status codes and OpenAPI metadata only."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Path, Request, Response, UploadFile, status

from podcast_engine.api.consent_pdf import FILENAME, consent_pdf
from podcast_engine.api.controllers.voices_controller import VoiceController
from podcast_engine.api.dependencies import CurrentUserDep, get_voice_controller
from podcast_engine.api.models.pagination_model import Page
from podcast_engine.api.models.voices_model import (
    CONSENT_SECTIONS,
    CONSENT_STATEMENT,
    CONSENT_TITLE,
    CONSENT_VERSION,
    ConsentDocument,
    ConsentForm,
    ConsentSection,
    Relationship,
    VoiceRead,
    VoiceSource,
)
from podcast_engine.api.openapi import errors, file_response
from podcast_engine.api.pagination import Paging, to_page

router = APIRouter(prefix="/voices", tags=["voices"])

Controller = Annotated[VoiceController, Depends(get_voice_controller)]
VoiceId = Annotated[UUID, Path(description="The voice's id")]
NOT_FOUND = errors(e404="Voice not found")


@router.get(
    "/consent",
    response_model=ConsentDocument,
    summary="Read the consent form",
    response_description="The consent form, section by section, and where to get it as a PDF",
)
def consent_form(request: Request) -> ConsentDocument:
    """The consent form a speaker must read and agree to before their voice is recorded or
    uploaded. Its version and full text (`statement`) are stored with every voice signed on it;
    voices signed on an earlier version keep the text they agreed to."""
    return ConsentDocument(
        version=CONSENT_VERSION,
        title=CONSENT_TITLE,
        sections=[ConsentSection(heading=h, paragraphs=list(p)) for h, p in CONSENT_SECTIONS],
        statement=CONSENT_STATEMENT,
        pdf=str(request.url_for("consent_form_pdf").path),
    )


@router.get(
    "/consent.pdf",
    summary="Download the consent form as a PDF",
    response_class=Response,
    responses=file_response("application/pdf", "The consent form", binary=True),
)
def consent_form_pdf() -> Response:
    """The same consent form as a PDF, to read, keep or print. For someone else's voice, a
    printed copy signed by the speaker can be kept as their written permission."""
    return Response(
        consent_pdf(),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{FILENAME}"',
            "Cache-Control": "private, max-age=3600",
        },
    )


@router.post(
    "",
    response_model=VoiceRead,
    status_code=status.HTTP_201_CREATED,
    summary="Register a voice",
    response_description="The registered voice, with its consent record",
    responses=errors(
        e409="The account already has the most voices allowed",
        e413="The recording is larger than the limit",
        e415="Not a 24 kHz mono 16-bit WAV",
        e422="The consent form is incomplete, or the recording is too short, long or silent",
    ),
)
def register_voice(
    me: CurrentUserDep,
    controller: Controller,
    audio: Annotated[UploadFile, File(description="24 kHz mono 16-bit WAV, 5 to 90 seconds")],
    speaker: Annotated[str, Form(description="Whose voice it is")],
    signature: Annotated[str, Form(description="Full name typed as a signature")],
    relationship: Annotated[
        Relationship,
        Form(description="`self` (your own voice) or `permission` (someone else's, with consent)"),
    ],
    agree_clone: Annotated[bool, Form(description="Agrees to the voice being cloned")],
    agree_ai_label: Annotated[bool, Form(description="Agrees episodes are labelled AI-generated")],
    agree_withdraw: Annotated[
        bool, Form(description="Understands consent is withdrawn by deleting")
    ],
    terms: Annotated[
        str, Form(alias="license", description="Terms the recording may be used under")
    ] = "Used only to voice this account's podcasts in Podcast Engine",
    name: Annotated[str, Form(description="A label for the voice")] = "",
    permission_record: Annotated[
        str, Form(description="Where the speaker's written permission is kept")
    ] = "",
    source: Annotated[VoiceSource, Form(description="`recorded` or `uploaded`")] = "recorded",
) -> VoiceRead:
    """Register a recording of a voice for the Chatterbox backend to clone, with the consent form
    its speaker completed. Refused unless every consent statement is agreed to and signed (by the
    speaker, for their own voice; or with a note of where their written permission is kept)."""
    form = ConsentForm(
        name=name,
        speaker=speaker,
        license=terms,
        relationship=relationship,
        signature=signature,
        permission_record=permission_record,
        agree_clone=agree_clone,
        agree_ai_label=agree_ai_label,
        agree_withdraw=agree_withdraw,
    )
    data = audio.file.read(controller.max_bytes + 1)  # one byte over the limit is enough to refuse
    return controller.register(me.user_id, form, source=source, data=data)


@router.get(
    "",
    response_model=Page[VoiceRead],
    summary="List your voices",
    response_description="A page of voices, newest first",
)
def list_voices(
    me: CurrentUserDep, controller: Controller, paging: Paging, request: Request
) -> Page[VoiceRead]:
    """The voices you registered, newest first, each with its consent record."""
    result = controller.list_page(me.user_id, limit=paging.limit, offset=paging.offset)
    return to_page(result, paging, request)


@router.get(
    "/{voice_id}",
    response_model=VoiceRead,
    summary="Get a voice",
    response_description="The voice and its consent record",
    responses=NOT_FOUND,
)
def get_voice(voice_id: VoiceId, me: CurrentUserDep, controller: Controller) -> VoiceRead:
    """One of your voices, with its consent record."""
    return controller.get(voice_id, me.user_id)


@router.get(
    "/{voice_id}/audio.wav",
    summary="Play a voice's recording",
    response_class=Response,
    responses={**file_response("audio/wav", "The recording", binary=True), **NOT_FOUND},
)
def voice_audio(voice_id: VoiceId, me: CurrentUserDep, controller: Controller) -> Response:
    """The recording itself, for its owner only (never public)."""
    return Response(
        controller.audio(voice_id, me.user_id),
        media_type="audio/wav",
        headers={"Cache-Control": "private, no-store"},
    )


@router.delete(
    "/{voice_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a voice (withdraw consent)",
    responses=NOT_FOUND,
)
def delete_voice(voice_id: VoiceId, me: CurrentUserDep, controller: Controller) -> None:
    """Withdraw a voice: the recording and its record are deleted, and no host of your shows uses
    it any more. Episodes already published keep their audio."""
    controller.delete(voice_id, me.user_id)
