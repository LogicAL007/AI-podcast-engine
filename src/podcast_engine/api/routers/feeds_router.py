from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Response

from podcast_engine.api.controllers.feeds_controller import FeedController
from podcast_engine.api.dependencies import get_feed_controller
from podcast_engine.api.models.feeds_model import RSS_MEDIA_TYPE
from podcast_engine.api.openapi import errors, file_response

router = APIRouter(prefix="/feeds", tags=["feeds"])

Controller = Annotated[FeedController, Depends(get_feed_controller)]
ShowId = Annotated[UUID, Path(description="The show's id")]


@router.get(
    "/{show_id}/rss.xml",
    response_class=Response,
    summary="Get a show's RSS feed",
    responses={
        **file_response(
            RSS_MEDIA_TYPE, "RSS 2.0 with iTunes tags, one item per published episode", binary=False
        ),
        **errors(e404="No episode of this show has been published yet"),
    },
)
def get_show_feed(show_id: ShowId, controller: Controller) -> Response:
    """The show's podcast feed, for podcast apps.

    Each item's enclosure is the episode's audio, its description the show notes; titles are
    labelled `[AI-generated]`. Rewritten by the publish stage each time an episode is published.

    \f

    Args:
        show_id: The show whose feed to return.
        controller: The feed controller, injected by FastAPI.

    Returns:
        The RSS 2.0 document with iTunes tags.
    """
    feed = controller.get_rss(show_id)
    return Response(content=feed.content, media_type=RSS_MEDIA_TYPE)
