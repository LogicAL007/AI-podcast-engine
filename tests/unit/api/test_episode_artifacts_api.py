from datetime import UTC, datetime
from uuid import UUID, uuid4

from podcast_engine.api.models.episodes_model import (
    ClaimRead,
    EpisodeFiles,
    EpisodeScript,
    LineRead,
    SegmentScript,
    StageRunRead,
)
from tests.unit.api.conftest import Harness


def _episode(harness: Harness) -> UUID:
    show_id = harness.client.post("/shows", json={"topic": "ClickHouse basics"}).json()["show_id"]
    return UUID(harness.client.post(f"/shows/{show_id}/episodes").json()["episode_id"])


def test_show_accepts_the_pipeline_fields() -> None:
    harness = Harness()
    body = {
        "topic": "What ClickHouse is",
        "sources": ["https://clickhouse.com/docs/get-started/about/intro"],
        "topic_keywords": "column-oriented OLAP analytics",
        "attribution": "Source: ClickHouse docs (CC BY-NC-SA 4.0).",
        "max_segments": 4,
        "ranking_profile": "daily",
    }
    created = harness.client.post("/shows", json=body)
    assert created.status_code == 201
    for name in ("topic_keywords", "attribution", "max_segments", "ranking_profile"):
        assert created.json()[name] == body[name]
    patched = harness.client.patch(f"/shows/{created.json()['show_id']}", json={"max_segments": 2})
    assert patched.json()["max_segments"] == 2


def test_show_rejects_out_of_range_pipeline_fields() -> None:
    harness = Harness()
    assert (
        harness.client.post("/shows", json={"topic": "abc", "max_segments": 13}).status_code == 422
    )
    assert (
        harness.client.post(
            "/shows", json={"topic": "abc", "ranking_profile": "weekly"}
        ).status_code
        == 422
    )


def test_audio_and_notes_are_404_until_published(harness: Harness) -> None:
    episode_id = _episode(harness)
    assert harness.client.get(f"/episodes/{episode_id}/audio.wav").status_code == 404
    assert harness.client.get(f"/episodes/{episode_id}/notes.md").status_code == 404
    assert harness.client.get(f"/episodes/{uuid4()}/audio.wav").status_code == 404


def _with_audio(harness: Harness, data: bytes) -> UUID:
    episode_id = _episode(harness)
    harness.episodes.files[episode_id] = EpisodeFiles(audio_key="a.wav", notes_key=None)
    harness.store.objects["a.wav"] = data
    return episode_id


def test_audio_supports_byte_ranges(harness: Harness) -> None:
    episode_id = _with_audio(harness, bytes(range(100)))
    url = f"/episodes/{episode_id}/audio.wav"

    whole = harness.client.get(url)
    assert whole.status_code == 200
    assert whole.headers["accept-ranges"] == "bytes"
    assert whole.headers["content-disposition"] == f'inline; filename="episode-{episode_id}.wav"'

    part = harness.client.get(url, headers={"Range": "bytes=10-19"})
    assert part.status_code == 206
    assert part.content == bytes(range(10, 20))
    assert part.headers["content-range"] == "bytes 10-19/100"

    assert harness.client.get(url, headers={"Range": "bytes=90-"}).content == bytes(range(90, 100))
    assert harness.client.get(url, headers={"Range": "bytes=-5"}).content == bytes(range(95, 100))

    outside = harness.client.get(url, headers={"Range": "bytes=500-"})
    assert outside.status_code == 416
    assert outside.headers["content-range"] == "bytes */100"


def test_audio_download_and_head(harness: Harness) -> None:
    episode_id = _with_audio(harness, b"RIFF" + b"x" * 96)
    url = f"/episodes/{episode_id}/audio.wav"
    download = harness.client.get(url, params={"download": "true"})
    assert download.headers["content-disposition"].startswith("attachment;")
    head = harness.client.head(url)
    assert head.status_code == 200
    assert head.headers["content-length"] == "100"
    assert head.content == b""


def test_episode_links_point_at_what_exists(harness: Harness) -> None:
    episode_id = _episode(harness)
    links = harness.client.get(f"/episodes/{episode_id}").json()["links"]
    assert links["audio"] is None
    assert links["notes"] is None
    assert links["script"] == f"/episodes/{episode_id}/script"
    episode = harness.episodes.rows[episode_id]
    harness.episodes.rows[episode_id] = episode.model_copy(
        update={"has_audio": True, "has_notes": True}
    )
    links = harness.client.get(f"/episodes/{episode_id}").json()["links"]
    assert links["audio"] == f"/episodes/{episode_id}/audio.wav"
    assert links["notes"] == f"/episodes/{episode_id}/notes.md"
    assert harness.client.get(links["script"]).status_code == 200


def test_audio_and_notes_are_served_from_storage(harness: Harness) -> None:
    episode_id = _episode(harness)
    harness.episodes.files[episode_id] = EpisodeFiles(audio_key="a.wav", notes_key="n.md")
    harness.store.objects.update({"a.wav": b"RIFF....WAVE", "n.md": b"# Notes\n"})

    audio = harness.client.get(f"/episodes/{episode_id}/audio.wav")
    assert audio.status_code == 200
    assert audio.headers["content-type"] == "audio/wav"
    assert audio.content == b"RIFF....WAVE"
    notes = harness.client.get(f"/episodes/{episode_id}/notes.md")
    assert notes.headers["content-type"].startswith("text/markdown")
    assert notes.text == "# Notes\n"


def test_script_shows_claims_with_verdicts(harness: Harness) -> None:
    episode_id = _episode(harness)
    chunk = uuid4()
    harness.episodes.scripts[episode_id] = EpisodeScript(
        episode_id=episode_id,
        segments=[
            SegmentScript(
                position=1,
                title="Intro",
                source_item_ids=[uuid4()],
                lines=[
                    LineRead(
                        speaker="Sam",
                        text="ClickHouse stores columns apart.",
                        claims=[
                            ClaimRead(
                                text="ClickHouse stores columns apart.",
                                chunk_ids=[chunk],
                                supported=True,
                                reason="word overlap 100%",
                            )
                        ],
                    )
                ],
            )
        ],
    )
    body = harness.client.get(f"/episodes/{episode_id}/script").json()
    (claim,) = body["segments"][0]["lines"][0]["claims"]
    assert claim["supported"] is True
    assert claim["chunk_ids"] == [str(chunk)]
    assert harness.client.get(f"/episodes/{uuid4()}/script").status_code == 404


def test_runs_list_each_stage(harness: Harness) -> None:
    episode_id = _episode(harness)
    harness.episodes.runs[episode_id] = [
        StageRunRead(
            stage="index",
            seconds=0.5,
            model="hashing",
            prompt_version=None,
            seed=7,
            started_at=datetime.now(UTC),
        )
    ]
    (run,) = harness.client.get(f"/episodes/{episode_id}/runs").json()["items"]
    assert run["stage"] == "index"
    assert run["seed"] == 7
    assert harness.client.get(f"/episodes/{uuid4()}/runs").status_code == 404
