"""Routes for shows: paths, status codes and OpenAPI metadata only."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query, status

from podcast_engine.api.controllers.shows_controller import ShowController
from podcast_engine.api.dependencies import get_show_controller
from podcast_engine.api.models.shows_model import ShowCreate, ShowRead, ShowUpdate
from podcast_engine.api.openapi import errors

router = APIRouter(prefix="/shows", tags=["shows"])

Controller = Annotated[ShowController, Depends(get_show_controller)]
ShowId = Annotated[UUID, Path(description="The show's id")]
Limit = Annotated[int, Query(ge=1, le=100, description="Most shows to return")]
Offset = Annotated[int, Query(ge=0, description="Shows to skip, for paging")]
NOT_FOUND = errors(e404="Show not found")


@router.post(
    "",
    response_model=ShowRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a show",
    response_description="The created show",
)
def create_show(data: ShowCreate, controller: Controller) -> ShowRead:
    """Create a show: its topic, style, hosts and the web pages its episodes are built from."""
    return controller.create(data)


@router.get(
    "",
    response_model=list[ShowRead],
    summary="List shows",
    response_description="Shows, newest first",
)
def list_shows(controller: Controller, limit: Limit = 20, offset: Offset = 0) -> list[ShowRead]:
    """A page of shows, newest first."""
    return controller.list_page(limit=limit, offset=offset)


@router.get(
    "/{show_id}",
    response_model=ShowRead,
    summary="Get a show",
    response_description="The show",
    responses=NOT_FOUND,
)
def get_show(show_id: ShowId, controller: Controller) -> ShowRead:
    """One show's settings."""
    return controller.get(show_id)


@router.patch(
    "/{show_id}",
    response_model=ShowRead,
    summary="Update a show",
    response_description="The show after the change",
    responses=NOT_FOUND,
)
def update_show(show_id: ShowId, data: ShowUpdate, controller: Controller) -> ShowRead:
    """Change only the fields sent; omitted or null fields are kept. Applies to episodes started
    afterwards."""
    return controller.update(show_id, data)


@router.delete(
    "/{show_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a show",
    response_description="Deleted",
    responses=NOT_FOUND,
)
def delete_show(show_id: ShowId, controller: Controller) -> None:
    """Delete a show and, by cascade, its source items, episodes and claims. Files already in object
    storage (audio, notes, feed) are not removed."""
    controller.delete(show_id)
