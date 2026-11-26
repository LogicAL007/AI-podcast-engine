from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Request

from podcast_engine.api.controllers.sources_controller import SourceController
from podcast_engine.api.dependencies import CurrentUserDep, get_source_controller
from podcast_engine.api.models.pagination_model import Page
from podcast_engine.api.models.sources_model import SourceRead
from podcast_engine.api.openapi import errors
from podcast_engine.api.pagination import Paging, to_page

router = APIRouter(tags=["sources"])

Controller = Annotated[SourceController, Depends(get_source_controller)]
ShowId = Annotated[UUID, Path(description="The show's id")]


@router.get(
    "/shows/{show_id}/sources",
    response_model=Page[SourceRead],
    summary="List a show's sources",
    response_description="A page of source sections, in source order",
    responses=errors(e404="Show not found"),
)
def list_show_sources(
    show_id: ShowId,
    me: CurrentUserDep,
    controller: Controller,
    paging: Paging,
    request: Request,
) -> Page[SourceRead]:
    """The sections the pipeline read from the show's pages, feeds and uploads.

    As last ingested: each one's heading, link, reliability tier, size and content hash. A section
    whose hash changes is what a refresh regenerates. Empty until the show's first episode has been
    ingested.

    \f

    Args:
        show_id: The show whose sources to list.
        me: The signed-in user.
        controller: The source controller, injected by FastAPI.
        paging: The page size and offset from the query string.
        request: The request, used to build the next page's link.

    Returns:
        A page of source sections, in source order.
    """
    result = controller.list_for_show(show_id, me.user_id, limit=paging.limit, offset=paging.offset)
    return to_page(result, paging, request)
