"""Voice studio 2 through the API: type-to-speech clips, the music library, show settings for
host effects and music, and remixing a published episode."""

from typing import Any
from uuid import UUID, uuid4

import numpy as np
import pytest

from podcast_engine.api.models.episodes_model import EpisodeFiles
from podcast_engine.common.audio import SR, read_wav_bytes, wav_bytes
from podcast_engine.common.config import Settings
from podcast_engine.common.models import EpisodeStatus
from podcast_engine.common.queue import Stage
from podcast_engine.common.quota import DailyBudget, MemoryCounter
from tests.unit.api.conftest import ADMIN, Harness
from tests.unit.api.test_voices_api import register


@pytest.fixture
def harness() -> Harness:
    return Harness()


def tone(seconds: float = 3.0, amplitude: float = 0.2) -> bytes:
    t = np.arange(int(SR * seconds)) / SR
    return wav_bytes((amplitude * np.sin(2 * np.pi * 220 * t)).astype(np.float32))


def clip(harness: Harness, **body: Any) -> Any:
    payload = {"text": "Hello from the studio.", "voice": {"kind": "engine", "host": "Alex"}}
    return harness.client.post("/v1/speech", json={**payload, **body})


# ---- type-to-speech -------------------------------------------------------------------------


def test_the_engine_says_which_voices_can_speak(harness: Harness) -> None:
    engine = harness.client.get("/v1/speech/engine").json()
    assert engine["backend"] == "chatterbox"
    assert engine["recorded_voices"] is True
    assert engine["uses_quota"] is False
    assert {v["host"] for v in engine["engine_voices"]} == {"Alex", "Sam", "Jordan", "Riley"}
    assert engine["presets"]["deeper"]["deepen"] > 0
    assert "warm" in engine["deliveries"]

    harness.speech_settings = Settings(tts_backend="gemini", tts_requests_per_day=12)
    gemini = harness.client.get("/v1/speech/engine").json()
    assert gemini["recorded_voices"] is False
    assert gemini["uses_quota"] is True
    assert "Kore" in gemini["engine_voices"][0]["label"]


def test_a_clip_is_queued_for_the_voice_worker_then_played(harness: Harness) -> None:
    response = clip(harness, delivery="warm", effects={"deepen": 40, "broadcast": True})
    assert response.status_code == 202
    queued = response.json()
    assert queued["status"] == "queued"
    assert queued["audio"] is None
    assert queued["effects"] == {"deepen": 40, "warmth": 0, "broadcast": True}
    assert harness.spoken == [queued["clip_id"]]

    clip_id = UUID(queued["clip_id"])
    harness.store.put("speech/x.wav", tone(), "audio/wav")
    harness.speech.finish(clip_id, "speech/x.wav")
    done = harness.client.get(f"/v1/speech/{clip_id}").json()
    assert done["status"] == "done"
    played = harness.client.get(done["audio"])
    assert played.status_code == 200
    assert played.headers["cache-control"] == "private, no-store"
    assert len(read_wav_bytes(played.content)) == 3 * SR

    assert [c["clip_id"] for c in harness.client.get("/v1/speech").json()] == [str(clip_id)]
    assert harness.client.delete(f"/v1/speech/{clip_id}").status_code == 204
    assert "speech/x.wav" not in harness.store.objects
    assert harness.client.get(f"/v1/speech/{clip_id}").status_code == 404


def test_a_recorded_voice_must_be_your_own(harness: Harness) -> None:
    mine = register(harness).json()["voice_id"]
    assert clip(harness, voice={"kind": "recorded", "voice_id": mine}).status_code == 202
    someone_elses = str(uuid4())
    assert clip(harness, voice={"kind": "recorded", "voice_id": someone_elses}).status_code == 404


def test_text_and_effects_are_checked(harness: Harness) -> None:
    assert clip(harness, text="").status_code == 422
    assert clip(harness, text="x" * 601).status_code == 422
    assert clip(harness, effects={"deepen": 101}).status_code == 422
    assert clip(harness, voice={"kind": "engine", "host": "Bob"}).status_code == 422
    assert harness.spoken == []


def test_clips_are_limited_per_hour(harness: Harness) -> None:
    harness.speech_settings = Settings(tts_backend="chatterbox", speech_clips_per_hour=2)
    assert clip(harness).status_code == 202
    assert clip(harness).status_code == 202
    refused = clip(harness)
    assert refused.status_code == 429
    assert int(refused.headers["retry-after"]) > 0


def test_gemini_clips_leave_half_the_days_voice_budget_to_episodes(harness: Harness) -> None:
    settings = Settings(tts_backend="gemini", tts_requests_per_day=4)
    harness.speech_settings = settings
    budget = DailyBudget(MemoryCounter(), {settings.tts_model: 4})
    harness.speech_budget = budget
    assert harness.client.get("/v1/speech/engine").json()["clips_left_today"] == 2
    budget.spend(settings.tts_model, 2)
    assert harness.client.get("/v1/speech/engine").json()["clips_left_today"] == 0
    refused = clip(harness)
    assert refused.status_code == 429
    assert "budget" in refused.json()["detail"]


def test_a_queue_outage_fails_the_clip_instead_of_leaving_it_queued(harness: Harness) -> None:
    harness.queue_down = True
    failed = clip(harness).json()
    assert failed["status"] == "failed"
    assert "queue" in failed["error"]


def test_another_owners_clip_is_not_found(harness: Harness) -> None:
    clip_id = UUID(clip(harness).json()["clip_id"])
    owner, read, key = harness.speech.rows[clip_id]
    harness.speech.rows[clip_id] = (uuid4(), read, key)
    assert harness.client.get(f"/v1/speech/{clip_id}").status_code == 404
    assert harness.client.get(f"/v1/speech/{clip_id}/audio.wav").status_code == 404
    assert harness.client.delete(f"/v1/speech/{clip_id}").status_code == 404
    assert owner == ADMIN.user_id


# ---- the music library ----------------------------------------------------------------------


def upload(harness: Harness, audio: bytes | None = None, **form: Any) -> Any:
    data = {"name": "My bed", "role": "bed", "rights": "true", "credit": "Music by Me", **form}
    return harness.client.post(
        "/v1/music", data=data, files={"audio": ("bed.wav", audio or tone(), "audio/wav")}
    )


def test_the_library_lists_built_in_tracks_then_yours(harness: Harness) -> None:
    track = upload(harness).json()
    tracks = harness.client.get("/v1/music").json()
    builtin = [t for t in tracks if t["builtin"]]
    assert {t["track_id"] for t in builtin} >= {"builtin:calm-pad", "builtin:two-note-sting"}
    assert tracks[-1]["track_id"] == track["track_id"]
    assert track["credit"] == "Music by Me"

    played = harness.client.get("/v1/music/builtin:two-note-sting/audio.wav")
    assert played.status_code == 200
    assert len(read_wav_bytes(played.content)) == pytest.approx(1.6 * SR, abs=2)
    assert harness.client.get(track["audio"]).content == tone()
    assert harness.client.get("/v1/music/builtin:nothing/audio.wav").status_code == 404


def test_an_upload_needs_the_rights_and_a_real_track(harness: Harness) -> None:
    assert upload(harness, rights="false").status_code == 422
    assert upload(harness, audio=b"not a wav").status_code == 415
    assert upload(harness, audio=tone(0.5)).status_code == 422  # under a second
    assert upload(harness, audio=tone(amplitude=0.0)).status_code == 422  # silent
    assert harness.client.get("/v1/music").json()[-1]["builtin"] is True  # nothing stored


def test_built_in_tracks_cannot_be_deleted_but_yours_can(harness: Harness) -> None:
    assert harness.client.delete("/v1/music/builtin:calm-pad").status_code == 409
    track = upload(harness).json()
    assert harness.client.delete(f"/v1/music/{track['track_id']}").status_code == 204
    assert harness.client.get(track["audio"]).status_code == 404


# ---- show settings --------------------------------------------------------------------------


def test_a_show_keeps_host_effects_and_music(harness: Harness) -> None:
    track = upload(harness).json()["track_id"]
    show = harness.client.post(
        "/v1/shows",
        json={
            "topic": "Tides and the moon",
            "host_effects": {"Alex": {"deepen": 40, "warmth": 20}},
            "music": {"intro": "builtin:bright-intro", "bed": track, "bed_level_db": -24},
        },
    ).json()
    assert show["host_effects"] == {"Alex": {"deepen": 40, "warmth": 20, "broadcast": False}}
    assert show["music"]["bed"] == track
    assert show["music"]["sting"] is None

    changed = harness.client.patch(
        f"/v1/shows/{show['show_id']}",
        json={
            "host_effects": {"Sam": {"broadcast": True}},
            "music": {"sting": "builtin:two-note-sting"},
        },
    ).json()
    assert set(changed["host_effects"]) == {"Sam"}
    assert changed["music"] == {
        "intro": None, "outro": None, "sting": "builtin:two-note-sting", "bed": None,
        "bed_level_db": -22,
    }  # fmt: skip

    # Deleting a track takes it off the show.
    harness.client.patch(f"/v1/shows/{show['show_id']}", json={"music": {"bed": track}})
    harness.client.delete(f"/v1/music/{track}")
    assert harness.client.get(f"/v1/shows/{show['show_id']}").json()["music"]["bed"] is None


@pytest.mark.parametrize(
    "body",
    [
        {"host_effects": {"Bob": {"deepen": 10}}},
        {"host_effects": {"Alex": {"deepen": 200}}},
        {"music": {"bed": "builtin:no-such-track"}},
        {"music": {"bed": str(uuid4())}},  # not one of yours
        {"music": {"bed_level_db": -5}},
    ],
)
def test_show_settings_are_checked(harness: Harness, body: dict[str, Any]) -> None:
    response = harness.client.post("/v1/shows", json={"topic": "Tides and the moon", **body})
    assert response.status_code == 422


# ---- remix ----------------------------------------------------------------------------------


def test_a_published_episode_is_remixed_without_voicing_again(harness: Harness) -> None:
    show = harness.client.post("/v1/shows", json={"topic": "Tides and the moon"}).json()
    episode = UUID(
        harness.client.post(f"/v1/shows/{show['show_id']}/episodes").json()["episode_id"]
    )
    assert harness.client.post(f"/v1/episodes/{episode}/remix").status_code == 409  # running

    harness.episodes.update(episode, status=EpisodeStatus.PUBLISHED, stage=None)
    harness.episodes.files[episode] = EpisodeFiles(audio_key="a.wav", notes_key=None)
    remixed = harness.client.post(f"/v1/episodes/{episode}/remix")
    assert remixed.status_code == 200
    assert remixed.json()["status"] == "queued"
    assert harness.stages[-1] == (episode, Stage.ASSEMBLE)


def test_a_remix_the_queue_cannot_take_leaves_the_episode_published(harness: Harness) -> None:
    show = harness.client.post("/v1/shows", json={"topic": "Tides and the moon"}).json()
    episode = UUID(
        harness.client.post(f"/v1/shows/{show['show_id']}/episodes").json()["episode_id"]
    )
    harness.episodes.update(episode, status=EpisodeStatus.PUBLISHED, stage=None)
    harness.episodes.files[episode] = EpisodeFiles(audio_key="a.wav", notes_key=None)
    harness.queue_down = True
    assert harness.client.post(f"/v1/episodes/{episode}/remix").status_code == 503
    assert harness.client.get(f"/v1/episodes/{episode}").json()["status"] == "published"
