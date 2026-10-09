"""Routes for shows: paths, status codes and OpenAPI metadata only."""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from podcast_engine.api.controllers.shows_controller import ShowController
from podcast_engine.api.dependencies import get_show_controller
from podcast_engine.api.models.shows_model import ShowCreate, ShowRead, ShowUpdate

router = APIRouter(prefix="/shows", tags=["shows"])

Controller = Annotated[ShowController, Depends(get_show_controller)]
NOT_FOUND: dict[int | str, dict[str, Any]] = {
    status.HTTP_404_NOT_FOUND: {"description": "Show not found"}
}


@router.post("", response_model=ShowRead, status_code=status.HTTP_201_CREATED)
def create_show(data: ShowCreate, controller: Controller) -> ShowRead:
    """Create a show (FR1)."""
    return controller.create(data)


@router.get("", response_model=list[ShowRead])
def list_shows(
    controller: Controller,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[ShowRead]:
    """List shows, newest first."""
    return controller.list_page(limit=limit, offset=offset)


@router.get("/{show_id}", response_model=ShowRead, responses=NOT_FOUND)
def get_show(show_id: UUID, controller: Controller) -> ShowRead:
    return controller.get(show_id)


@router.patch("/{show_id}", response_model=ShowRead, responses=NOT_FOUND)
def update_show(show_id: UUID, data: ShowUpdate, controller: Controller) -> ShowRead:
    """Change only the fields that are sent."""
    return controller.update(show_id, data)


@router.delete("/{show_id}", status_code=status.HTTP_204_NO_CONTENT, responses=NOT_FOUND)
def delete_show(show_id: UUID, controller: Controller) -> None:
    """Delete a show and, by cascade, its items, episodes and claims."""
    controller.delete(show_id)
