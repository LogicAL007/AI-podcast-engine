from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Request, status

from podcast_engine.api.controllers.shows_controller import ShowController
from podcast_engine.api.dependencies import CurrentUserDep, get_show_controller
from podcast_engine.api.models.pagination_model import Page
from podcast_engine.api.models.shows_model import ShowCreate, ShowRead, ShowUpdate
from podcast_engine.api.openapi import errors
from podcast_engine.api.pagination import Paging, to_page

router = APIRouter(prefix="/shows", tags=["shows"])

Controller = Annotated[ShowController, Depends(get_show_controller)]
ShowId = Annotated[UUID, Path(description="The show's id")]
NOT_FOUND = errors(e404="Show not found")


@router.post(
    "",
    response_model=ShowRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a show",
    response_description="The created show",
)
def create_show(data: ShowCreate, me: CurrentUserDep, controller: Controller) -> ShowRead:
    """Create a show, owned by you.

    Its topic, style, hosts and the web pages its episodes are built from. Only you can see or
    change it.

    \f

    Args:
        data: The new show's settings.
        me: The signed-in user.
        controller: The show controller, injected by FastAPI.

    Returns:
        The created show.
    """
    return controller.create(data, me.user_id)


@router.get(
    "",
    response_model=Page[ShowRead],
    summary="List shows",
    response_description="A page of shows, newest first",
)
def list_shows(
    me: CurrentUserDep, controller: Controller, paging: Paging, request: Request
) -> Page[ShowRead]:
    """A page of your shows, newest first.

    \f

    Args:
        me: The signed-in user.
        controller: The show controller, injected by FastAPI.
        paging: The page size and offset from the query string.
        request: The request, used to build the next page's link.

    Returns:
        A page of shows.
    """
    result = controller.list_page(me.user_id, limit=paging.limit, offset=paging.offset)
    return to_page(result, paging, request)


@router.get(
    "/{show_id}",
    response_model=ShowRead,
    summary="Get a show",
    response_description="The show",
    responses=NOT_FOUND,
)
def get_show(show_id: ShowId, me: CurrentUserDep, controller: Controller) -> ShowRead:
    """One of your shows' settings.

    Another user's show is reported as not found.

    \f

    Args:
        show_id: The show to return.
        me: The signed-in user.
        controller: The show controller, injected by FastAPI.

    Returns:
        The show.
    """
    return controller.get(show_id, me.user_id)


@router.patch(
    "/{show_id}",
    response_model=ShowRead,
    summary="Update a show",
    response_description="The show after the change",
    responses=NOT_FOUND,
)
def update_show(
    show_id: ShowId, data: ShowUpdate, me: CurrentUserDep, controller: Controller
) -> ShowRead:
    """Change only the fields sent; omitted or null fields are kept.

    Applies to episodes started afterwards.

    \f

    Args:
        show_id: The show to change.
        data: The fields to change.
        me: The signed-in user.
        controller: The show controller, injected by FastAPI.

    Returns:
        The show after the change.
    """
    return controller.update(show_id, me.user_id, data)


@router.delete(
    "/{show_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a show",
    response_description="Deleted",
    responses=NOT_FOUND,
)
def delete_show(show_id: ShowId, me: CurrentUserDep, controller: Controller) -> None:
    """Delete a show and, by cascade, its source items, episodes and claims.

    Files already in object storage (audio, notes, feed) are not removed.

    \f

    Args:
        show_id: The show to delete.
        me: The signed-in user.
        controller: The show controller, injected by FastAPI.
    """
    controller.delete(show_id, me.user_id)
