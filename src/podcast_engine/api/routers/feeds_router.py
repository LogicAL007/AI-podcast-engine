"""Routes for feeds: paths, status codes and OpenAPI metadata only."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status

from podcast_engine.api.controllers.feeds_controller import FeedController
from podcast_engine.api.dependencies import get_feed_controller
from podcast_engine.api.models.feeds_model import RSS_MEDIA_TYPE

router = APIRouter(prefix="/feeds", tags=["feeds"])

Controller = Annotated[FeedController, Depends(get_feed_controller)]


@router.get(
    "/{show_id}/rss.xml",
    response_class=Response,
    responses={
        status.HTTP_200_OK: {"content": {RSS_MEDIA_TYPE: {}}, "description": "The RSS feed"},
        status.HTTP_404_NOT_FOUND: {"description": "No episode has been published yet"},
    },
)
def get_rss(show_id: UUID, controller: Controller) -> Response:
    """Serve the show's RSS feed (FR10) for podcast apps."""
    feed = controller.get_rss(show_id)
    return Response(content=feed.content, media_type=RSS_MEDIA_TYPE)
