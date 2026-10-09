from uuid import uuid4

from podcast_engine.common.storage import feed_key
from tests.unit.api.conftest import Harness


def test_feed_served_with_rss_media_type(harness: Harness) -> None:
    show_id = uuid4()
    harness.store.put(feed_key(show_id), b"<rss/>", "application/rss+xml")
    response = harness.client.get(f"/feeds/{show_id}/rss.xml")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/rss+xml")
    assert response.content == b"<rss/>"


def test_unpublished_feed_is_404(harness: Harness) -> None:
    assert harness.client.get(f"/feeds/{uuid4()}/rss.xml").status_code == 404


def test_health(harness: Harness) -> None:
    assert harness.client.get("/health").json()["status"] == "ok"


def test_openapi_lists_every_route(harness: Harness) -> None:
    paths = harness.client.get("/openapi.json").json()["paths"]
    assert {
        "/shows",
        "/shows/{show_id}",
        "/shows/{show_id}/episodes",
        "/episodes/{episode_id}",
        "/feeds/{show_id}/rss.xml",
        "/health",
    } <= set(paths)
