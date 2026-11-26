from uuid import UUID

from podcast_engine.api.errors import NotFoundError, to_http
from podcast_engine.api.models.feeds_model import RssFeed
from podcast_engine.api.services.feeds_service import FeedService


class FeedController:
    """HTTP-facing entry point for feeds: calls the service and maps its errors to HTTP."""

    def __init__(self, service: FeedService) -> None:
        """Create the controller.

        Args:
            service: The feed service that reads published feeds.
        """
        self._service = service

    def get_rss(self, show_id: UUID) -> RssFeed:
        """Return a show's published RSS feed.

        Args:
            show_id: The show whose feed to return.

        Returns:
            The feed document as written by the publish stage.

        Raises:
            HTTPException: 404 when the show has no published feed yet.
        """
        try:
            return self._service.get_rss(show_id)
        except NotFoundError as error:
            raise to_http(error) from error
