from uuid import UUID

from podcast_engine.api.errors import NotFoundError
from podcast_engine.api.models.feeds_model import RssFeed
from podcast_engine.common.storage import ObjectStore, feed_key


class FeedService:
    """Business rules for feeds.

    The publish stage writes each show's feed to object storage; this service only reads it.
    """

    def __init__(self, store: ObjectStore) -> None:
        """Create the service.

        Args:
            store: The object store the publish stage writes feeds to.
        """
        self._store = store

    def get_rss(self, show_id: UUID) -> RssFeed:
        """Read a show's published RSS feed.

        Args:
            show_id: The show whose feed to read.

        Returns:
            The feed document and the show it belongs to.

        Raises:
            NotFoundError: The show has no published feed yet.
        """
        key = feed_key(show_id)
        if not self._store.exists(key):
            raise NotFoundError("feed", show_id)
        return RssFeed(show_id=show_id, content=self._store.get(key))
