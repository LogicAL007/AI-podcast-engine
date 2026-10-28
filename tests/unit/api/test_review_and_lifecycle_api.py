from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest

from podcast_engine.api.models.episodes_model import ClaimDetail, EpisodeFiles
from podcast_engine.common.models import EpisodeStatus
from podcast_engine.common.queue import Stage
from tests.unit.api.conftest import Harness

SHOW = {"topic": "ClickHouse basics", "host_count": 2}


def _show(harness: Harness, **fields: Any) -> UUID:
    return UUID(harness.client.post("/v1/shows", json={**SHOW, **fields}).json()["show_id"])


def _episode(harness: Harness, status: EpisodeStatus, *, stage: str | None = None) -> UUID:
    show_id = _show(harness)
    episode_id = UUID(harness.client.post(f"/v1/shows/{show_id}/episodes").json()["episode_id"])
    harness.episodes.update(episode_id, status=status, stage=stage)
    harness.stages.clear()
    return episode_id


# ---- pagination ---------------------------------------------------------------------------


def test_lists_return_a_page_with_a_next_link(harness: Harness) -> None:
    for n in range(5):
        harness.client.post("/v1/shows", json={"topic": f"Show number {n}"})
    first = harness.client.get("/v1/shows", params={"limit": 2}).json()
    assert first["total"] == 5
    assert (first["limit"], first["offset"]) == (2, 0)
    assert len(first["items"]) == 2
    assert first["next"] == "/v1/shows?limit=2&offset=2"
    last = harness.client.get("/v1/shows", params={"limit": 2, "offset": 4}).json()
    assert len(last["items"]) == 1
    assert last["next"] is None


def test_next_link_keeps_the_filters(harness: Harness) -> None:
    show_id = _show(harness)
    for _ in range(3):
        episode = harness.client.post(f"/v1/shows/{show_id}/episodes").json()
        harness.episodes.update(UUID(episode["episode_id"]), status=EpisodeStatus.FAILED)
    body = harness.client.get(
        f"/v1/shows/{show_id}/episodes", params={"status": "failed", "limit": 1}
    ).json()
    assert body["total"] == 3
    assert "status=failed" in body["next"]
    assert "offset=1" in body["next"]


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 101}, {"offset": -1}])
def test_paging_parameters_are_validated(harness: Harness, params: dict[str, int]) -> None:
    assert harness.client.get("/v1/shows", params=params).status_code == 422


def test_review_queue_lists_episodes_waiting_across_shows(harness: Harness) -> None:
    waiting = _episode(harness, EpisodeStatus.NEEDS_REVIEW)
    _episode(harness, EpisodeStatus.PUBLISHED)
    body = harness.client.get("/v1/episodes", params={"status": "needs_review"}).json()
    assert [e["episode_id"] for e in body["items"]] == [str(waiting)]
    assert harness.client.get("/v1/episodes").json()["total"] == 2


# ---- editing the script ---------------------------------------------------------------------


def _editable(harness: Harness) -> tuple[UUID, UUID]:
    episode_id = _episode(harness, EpisodeStatus.NEEDS_REVIEW, stage="factcheck")
    show_id = harness.episodes.rows[episode_id].show_id
    chunk = uuid4()
    harness.episodes.positions[episode_id] = [1, 2]
    harness.episodes.show_chunks[show_id] = {chunk}
    harness.episodes.raw_scripts[episode_id] = {
        "segments": {"1": [{"speaker": "Alex", "text": "Kept.", "claims": []}], "2": []},
        "avoid": {},
    }
    return episode_id, chunk


def test_editing_replaces_a_segment_and_fact_checks_it_again(harness: Harness) -> None:
    episode_id, chunk = _editable(harness)
    edit = {
        "segments": [
            {
                "position": 2,
                "lines": [
                    {"speaker": "Alex", "text": "Next, storage.", "delivery": "curious"},
                    {
                        "speaker": "Sam",
                        "text": "Columns are stored apart.",
                        "chunk_ids": [str(chunk)],
                    },
                ],
            }
        ]
    }
    response = harness.client.patch(f"/v1/episodes/{episode_id}/script", json=edit)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "queued"
    assert harness.stages == [(episode_id, Stage.FACTCHECK)]
    script = harness.episodes.raw_scripts[episode_id]
    assert script["segments"]["1"][0]["text"] == "Kept."
    framing, claim = script["segments"]["2"]
    assert framing["claims"] == []
    assert (framing["delivery"], claim["delivery"]) == ("curious", "neutral")  # kept for the voice
    assert claim["claims"][0]["chunk_ids"] == [str(chunk)]
    assert claim["claims"][0]["claim_id"]
    assert script["edited_segments"] == [2]


def test_edit_refuses_unknown_segments_speakers_and_passages(harness: Harness) -> None:
    episode_id, _ = _editable(harness)
    edit = {
        "segments": [
            {
                "position": 9,
                "lines": [{"speaker": "Riley", "text": "Hi.", "chunk_ids": [str(uuid4())]}],
            }
        ]
    }
    response = harness.client.patch(f"/v1/episodes/{episode_id}/script", json=edit)
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert "segment 9 does not exist" in detail
    assert "'Riley' is not a host" in detail
    assert "is not one of this show's sources" in detail
    assert harness.stages == []


def test_only_an_episode_waiting_for_review_can_be_edited_or_approved(harness: Harness) -> None:
    episode_id = _episode(harness, EpisodeStatus.PROCESSING)
    edit = {"segments": [{"position": 1, "lines": [{"speaker": "Alex", "text": "Hi."}]}]}
    assert harness.client.patch(f"/v1/episodes/{episode_id}/script", json=edit).status_code == 409
    response = harness.client.post(f"/v1/episodes/{episode_id}/approve")
    assert response.status_code == 409
    assert "processing" in response.json()["detail"]


def test_approve_releases_to_voicing(harness: Harness) -> None:
    episode_id = _episode(harness, EpisodeStatus.NEEDS_REVIEW, stage="factcheck")
    body = harness.client.post(f"/v1/episodes/{episode_id}/approve").json()
    assert body["status"] == "queued"
    assert body["approved_at"] is not None
    assert harness.stages == [(episode_id, Stage.VOICE)]


def test_approve_with_the_queue_down_leaves_it_in_review(harness: Harness) -> None:
    episode_id = _episode(harness, EpisodeStatus.NEEDS_REVIEW)
    harness.queue_down = True
    assert harness.client.post(f"/v1/episodes/{episode_id}/approve").status_code == 503
    assert harness.episodes.rows[episode_id].status is EpisodeStatus.NEEDS_REVIEW


def test_shows_can_require_review_before_voicing(harness: Harness) -> None:
    created = harness.client.post("/v1/shows", json={**SHOW, "review_before_voice": True}).json()
    assert created["review_before_voice"] is True


# ---- lifecycle ------------------------------------------------------------------------------


def test_retry_resumes_from_the_failed_stage(harness: Harness) -> None:
    episode_id = _episode(harness, EpisodeStatus.FAILED, stage="voice")
    body = harness.client.post(f"/v1/episodes/{episode_id}/retry").json()
    assert body["status"] == "queued"
    assert harness.stages == [(episode_id, Stage.VOICE)]
    assert harness.client.post(f"/v1/episodes/{episode_id}/retry").status_code == 409


def test_cancel_stops_a_running_episode_but_not_a_finished_one(harness: Harness) -> None:
    running = _episode(harness, EpisodeStatus.PROCESSING, stage="script")
    assert harness.client.post(f"/v1/episodes/{running}/cancel").json()["status"] == "cancelled"
    finished = _episode(harness, EpisodeStatus.PUBLISHED)
    assert harness.client.post(f"/v1/episodes/{finished}/cancel").status_code == 409


def test_delete_removes_files_and_rebuilds_the_feed(harness: Harness) -> None:
    episode_id = _episode(harness, EpisodeStatus.PUBLISHED)
    show_id = harness.episodes.rows[episode_id].show_id
    harness.episodes.files[episode_id] = EpisodeFiles(audio_key="a.wav", notes_key="n.md")
    harness.store.objects.update({"a.wav": b"audio", "n.md": b"notes"})

    assert harness.client.delete(f"/v1/episodes/{episode_id}").status_code == 204
    assert harness.store.objects == {}
    assert harness.feeds_rebuilt == [show_id]
    assert harness.client.get(f"/v1/episodes/{episode_id}").status_code == 404


def test_a_running_episode_must_be_cancelled_before_deleting(harness: Harness) -> None:
    episode_id = _episode(harness, EpisodeStatus.PROCESSING)
    response = harness.client.delete(f"/v1/episodes/{episode_id}")
    assert response.status_code == 409
    assert "cancel it" in response.json()["detail"]


def test_claims_can_be_filtered_by_verdict_and_segment(harness: Harness) -> None:
    episode_id = _episode(harness, EpisodeStatus.PUBLISHED)
    harness.episodes.claims[episode_id] = [
        ClaimDetail(
            claim_id=uuid4(), segment=s, text=f"claim {n}", chunk_ids=[], supported=ok, reason="r"
        )
        for n, (s, ok) in enumerate([(1, True), (1, False), (2, False)])
    ]
    body = harness.client.get(
        f"/v1/episodes/{episode_id}/claims", params={"supported": "false"}
    ).json()
    assert [c["text"] for c in body["items"]] == ["claim 1", "claim 2"]
    body = harness.client.get(
        f"/v1/episodes/{episode_id}/claims", params={"supported": "false", "segment": 2}
    ).json()
    assert body["total"] == 1
    assert harness.client.get(f"/v1/episodes/{uuid4()}/claims").status_code == 404


def test_approved_at_is_reported(harness: Harness) -> None:
    episode_id = _episode(harness, EpisodeStatus.PUBLISHED)
    when = datetime.now(UTC) - timedelta(hours=1)
    harness.episodes.update(episode_id, approved_at=when)
    assert harness.client.get(f"/v1/episodes/{episode_id}").json()["approved_at"] is not None
