"""The live progress stream: server-sent events while an episode is made."""

import json
from typing import Any
from uuid import UUID, uuid4

from podcast_engine.common.models import EpisodeStatus
from tests.unit.api.conftest import Harness

SHOW = {"topic": "tides", "sources": ["https://example.org/a"]}


def _episode(harness: Harness) -> UUID:
    show = harness.client.post("/v1/shows", json=SHOW).json()
    return UUID(harness.client.post(f"/v1/shows/{show['show_id']}/episodes").json()["episode_id"])


def _events(text: str) -> list[tuple[str, dict[str, Any]]]:
    out = []
    for block in text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines() if ": " in line)
        if "event" in lines:
            out.append((lines["event"], json.loads(lines["data"])))
    return out


def _stream(harness: Harness, episode_id: UUID) -> Any:
    return harness.client.get(f"/v1/episodes/{episode_id}/events")


def test_progress_is_streamed_stage_by_stage_until_published(harness: Harness) -> None:
    episode_id = _episode(harness)
    stages = ["ingest", "index", "retrieve_plan", "script", "factcheck", "voice", "assemble"]

    def move(stage: str) -> Any:
        return lambda: harness.episodes.update(
            episode_id, status=EpisodeStatus.PROCESSING, stage=stage
        )

    harness.on_poll = [move(stage) for stage in stages]
    harness.on_poll.append(
        lambda: harness.episodes.update(episode_id, status=EpisodeStatus.PUBLISHED, stage=None)
    )
    response = _stream(harness, episode_id)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["x-accel-buffering"] == "no"
    assert response.text.startswith("retry: 3000")
    events = _events(response.text)
    assert [data["step"] for _, data in events] == [0, 1, 2, 3, 4, 5, 6, 7, 8]
    assert events[0][1]["status"] == "queued"
    assert events[-1][1] == {
        "episode_id": str(episode_id), "status": "published", "stage": None, "step": 8,
        "steps": 8, "error": None, "rewrite_count": 0, "running": False,
    }  # fmt: skip


def test_an_episode_that_is_not_running_sends_one_event_and_ends(harness: Harness) -> None:
    episode_id = _episode(harness)
    harness.episodes.update(episode_id, status=EpisodeStatus.NEEDS_REVIEW, stage="factcheck")
    events = _events(_stream(harness, episode_id).text)
    assert [(name, data["status"]) for name, data in events] == [("episode", "needs_review")]


def test_quiet_streams_send_keep_alives_and_stop_after_an_hour(harness: Harness) -> None:
    episode_id = _episode(harness)
    harness.pacing = harness.pacing.__class__(
        poll_s=5.0, heartbeat_s=15.0, max_s=60.0, sleep=harness.pacing.sleep,
        clock=harness.pacing.clock,
    )  # fmt: skip
    text = _stream(harness, episode_id).text
    assert len(_events(text)) == 1  # nothing changed after the first event
    assert text.count(": keep-alive") == 3  # at 15, 30 and 45 s; the stream ends at 60 s


def test_a_deleted_episode_ends_the_stream_with_gone(harness: Harness) -> None:
    episode_id = _episode(harness)

    def delete() -> None:
        harness.episodes.rows.pop(episode_id)

    harness.on_poll = [delete]
    text = _stream(harness, episode_id).text
    assert text.rstrip().endswith("event: gone\ndata: {}")


def test_someone_elses_episode_is_not_found(harness: Harness) -> None:
    assert _stream(harness, uuid4()).status_code == 404
    episode_id = _episode(harness)
    harness.shows.owners[harness.episodes.rows[episode_id].show_id] = uuid4()
    assert _stream(harness, episode_id).status_code == 404
