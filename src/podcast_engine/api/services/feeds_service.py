"""Business rules for feeds. The publish stage writes feeds; this only reads them."""

from uuid import UUID

from podcast_engine.api.errors import NotFoundError
from podcast_engine.api.models.feeds_model import RssFeed
from podcast_engine.common.storage import ObjectStore, feed_key


class FeedService:
    def __init__(self, store: ObjectStore) -> None:
        self._store = store

    def get_rss(self, show_id: UUID) -> RssFeed:
        key = feed_key(show_id)
        if not self._store.exists(key):
            raise NotFoundError("feed", show_id)
        return RssFeed(show_id=show_id, content=self._store.get(key))
