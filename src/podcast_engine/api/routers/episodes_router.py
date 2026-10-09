"""Routes for episodes: paths, status codes and OpenAPI metadata only."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from podcast_engine.api.controllers.episodes_controller import EpisodeController
from podcast_engine.api.dependencies import get_episode_controller
from podcast_engine.api.models.episodes_model import EpisodeRead

router = APIRouter(tags=["episodes"])

Controller = Annotated[EpisodeController, Depends(get_episode_controller)]


@router.post(
    "/shows/{show_id}/episodes",
    response_model=EpisodeRead,
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        status.HTTP_404_NOT_FOUND: {"description": "Show not found"},
        status.HTTP_503_SERVICE_UNAVAILABLE: {"description": "Job queue unavailable"},
    },
)
def start_episode(show_id: UUID, controller: Controller) -> EpisodeRead:
    """Start generating a new episode. Returns at once; poll the episode for progress."""
    return controller.start(show_id)


@router.get(
    "/shows/{show_id}/episodes",
    response_model=list[EpisodeRead],
    responses={status.HTTP_404_NOT_FOUND: {"description": "Show not found"}},
)
def list_episodes(
    show_id: UUID,
    controller: Controller,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[EpisodeRead]:
    """List a show's episodes, newest first."""
    return controller.list_for_show(show_id, limit=limit, offset=offset)


@router.get(
    "/episodes/{episode_id}",
    response_model=EpisodeRead,
    responses={status.HTTP_404_NOT_FOUND: {"description": "Episode not found"}},
)
def get_episode(episode_id: UUID, controller: Controller) -> EpisodeRead:
    return controller.get(episode_id)
