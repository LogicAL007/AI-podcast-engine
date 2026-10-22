"""Routes for uploaded sources: paths, status codes and OpenAPI metadata only."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Path, Request, UploadFile, status

from podcast_engine.api.controllers.uploads_controller import UploadController
from podcast_engine.api.dependencies import CurrentUserDep, get_upload_controller
from podcast_engine.api.models.pagination_model import Page
from podcast_engine.api.models.uploads_model import UploadRead
from podcast_engine.api.openapi import errors
from podcast_engine.api.pagination import Paging, to_page

router = APIRouter(prefix="/shows/{show_id}/uploads", tags=["uploads"])

Controller = Annotated[UploadController, Depends(get_upload_controller)]
ShowId = Annotated[UUID, Path(description="The show's id")]
UploadId = Annotated[UUID, Path(description="The upload's id")]
NOT_FOUND = errors(e404="Show or upload not found")


@router.post(
    "",
    response_model=UploadRead,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a PDF source",
    response_description="The stored upload",
    responses=errors(
        e404="Show not found", e413="The file is larger than the limit", e415="Not a PDF"
    ),
)
def upload_source(
    show_id: ShowId,
    me: CurrentUserDep,
    controller: Controller,
    file: Annotated[UploadFile, File(description="A PDF; the limit is 25 MB unless configured")],
) -> UploadRead:
    """Add a PDF to the show's sources. Its text is read at the show's next episode: each heading
    starts a citable section (or each page, if the PDF has no headings), and citations in the show
    notes link to the page they come from. Uploads are private to the API."""
    data = file.file.read(controller.max_bytes + 1)  # one byte over the limit is enough to refuse
    return controller.add(show_id, me.user_id, filename=file.filename or "upload.pdf", data=data)


@router.get(
    "",
    response_model=Page[UploadRead],
    summary="List a show's uploads",
    response_description="A page of uploads, newest first",
    responses=errors(e404="Show not found"),
)
def list_uploads(
    show_id: ShowId,
    me: CurrentUserDep,
    controller: Controller,
    paging: Paging,
    request: Request,
) -> Page[UploadRead]:
    """The files uploaded as sources for the show, newest first."""
    result = controller.list_for_show(show_id, me.user_id, limit=paging.limit, offset=paging.offset)
    return to_page(result, paging, request)


@router.get(
    "/{upload_id}",
    response_model=UploadRead,
    summary="Get an upload",
    response_description="The upload",
    responses=NOT_FOUND,
)
def get_upload(
    show_id: ShowId, upload_id: UploadId, me: CurrentUserDep, controller: Controller
) -> UploadRead:
    """One upload's name, size and download link."""
    return controller.get(show_id, upload_id, me.user_id)


@router.delete(
    "/{upload_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an upload",
    response_description="Deleted",
    responses=NOT_FOUND,
)
def delete_upload(
    show_id: ShowId, upload_id: UploadId, me: CurrentUserDep, controller: Controller
) -> None:
    """Remove the upload and its file. Its sections leave the show's sources at the next episode,
    which regenerates the segments that used them."""
    controller.delete(show_id, upload_id, me.user_id)
