"""HTTP-facing orchestration for feeds: calls the service, maps its errors to HTTP."""

from uuid import UUID

from podcast_engine.api.errors import NotFoundError, to_http
from podcast_engine.api.models.feeds_model import RssFeed
from podcast_engine.api.services.feeds_service import FeedService


class FeedController:
    def __init__(self, service: FeedService) -> None:
        self._service = service

    def get_rss(self, show_id: UUID) -> RssFeed:
        try:
            return self._service.get_rss(show_id)
        except NotFoundError as error:
            raise to_http(error) from error
