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
    """Add a PDF to the show's sources.

    Its text is read at the show's next episode: each heading starts a citable section (or each
    page, if the PDF has no headings), and citations in the show notes link to the page they come
    from. Uploads are private to the API.

    \f

    Args:
        show_id: The show to add the file to.
        me: The signed-in user.
        controller: The upload controller, injected by FastAPI.
        file: The uploaded PDF; reading stops one byte past the limit, which is enough to refuse it.

    Returns:
        The stored upload.
    """
    data = file.file.read(controller.max_bytes + 1)
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
    """The files uploaded as sources for the show, newest first.

    \f

    Args:
        show_id: The show whose uploads to list.
        me: The signed-in user.
        controller: The upload controller, injected by FastAPI.
        paging: The page size and offset from the query string.
        request: The request, used to build the next page's link.

    Returns:
        A page of uploads.
    """
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
    """One upload's name, size and download link.

    \f

    Args:
        show_id: The show it belongs to.
        upload_id: The upload to return.
        me: The signed-in user.
        controller: The upload controller, injected by FastAPI.

    Returns:
        The upload.
    """
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
    """Remove the upload and its file.

    Its sections leave the show's sources at the next episode, which regenerates the segments that
    used them.

    \f

    Args:
        show_id: The show it belongs to.
        upload_id: The upload to delete.
        me: The signed-in user.
        controller: The upload controller, injected by FastAPI.
    """
    controller.delete(show_id, upload_id, me.user_id)
