from uuid import uuid4

from podcast_engine.common.models import EpisodeStatus
from tests.unit.api.conftest import Harness

SHOW = {"topic": "Open-source AI research"}


def _show(harness: Harness) -> str:
    return str(harness.client.post("/v1/shows", json=SHOW).json()["show_id"])


def test_start_returns_202_and_enqueues(harness: Harness) -> None:
    show_id = _show(harness)
    response = harness.client.post(f"/v1/shows/{show_id}/episodes")
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "queued"
    assert [str(e) for e in harness.enqueued] == [body["episode_id"]]


def test_start_for_unknown_show_is_404_and_enqueues_nothing(harness: Harness) -> None:
    assert harness.client.post(f"/v1/shows/{uuid4()}/episodes").status_code == 404
    assert harness.enqueued == []


def test_queue_outage_marks_episode_failed_and_returns_503(harness: Harness) -> None:
    show_id = _show(harness)
    harness.queue_down = True
    response = harness.client.post(f"/v1/shows/{show_id}/episodes")
    assert response.status_code == 503
    (episode,) = harness.episodes.rows.values()
    assert episode.status is EpisodeStatus.FAILED


def test_get_and_list(harness: Harness) -> None:
    show_id = _show(harness)
    episode_id = harness.client.post(f"/v1/shows/{show_id}/episodes").json()["episode_id"]

    assert harness.client.get(f"/v1/episodes/{episode_id}").json()["show_id"] == show_id
    listed = harness.client.get(f"/v1/shows/{show_id}/episodes").json()["items"]
    assert [e["episode_id"] for e in listed] == [episode_id]
    assert harness.client.get(f"/v1/episodes/{uuid4()}").status_code == 404
    assert harness.client.get(f"/v1/shows/{uuid4()}/episodes").status_code == 404
