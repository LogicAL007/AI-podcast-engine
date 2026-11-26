"""Voice studio 2 without the API: voice effects, the built-in music, the bed under speech, the
show's music in an assembled episode, and the voice worker's type-to-speech task."""

from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import numpy as np
import pytest

from podcast_engine.common.audio import SR, read_wav_bytes, silence, wav_bytes
from podcast_engine.common.music import BUILTIN_TRACKS, ShowMusic, builtin_audio
from podcast_engine.common.repository import MusicTrackRecord, SpeechClipRecord
from podcast_engine.common.voice_fx import PRESETS, VoiceEffects, apply_effects
from podcast_engine.stages.assemble import service as assemble_service
from podcast_engine.stages.assemble.music import (
    SLOT_SECONDS,
    SPEECH_RMS,
    add_bed,
    apply_host_effects,
    duck_gains,
    fit_slot,
    load_show_tracks,
    loop_to,
)
from podcast_engine.stages.voice import speak
from podcast_engine.stages.voice.backends import PlaceholderBackend
from podcast_engine.stages.voice.speech_text import pieces, raw_speech_keys


def voiced(seconds: float = 1.0, f0: float = 160.0, level: float = 0.2) -> np.ndarray:
    """A voice-like tone: a fundamental and its overtones."""
    t = np.arange(int(SR * seconds)) / SR
    tone = sum(np.sin(2 * np.pi * f0 * k * t) / k for k in range(1, 8))
    return np.asarray(level * tone / np.max(np.abs(tone)), dtype=np.float32)


def pitch(audio: np.ndarray) -> float:
    """The fundamental by autocorrelation, in Hz."""
    window = audio[SR // 4 : SR // 4 + 4096]
    corr = np.correlate(window, window, "full")[len(window) - 1 :]
    low, high = SR // 400, SR // 60
    return SR / (low + int(np.argmax(corr[low:high])))


def rms(audio: np.ndarray) -> float:
    return float(np.sqrt(np.mean(audio**2)))


# ---- voice effects --------------------------------------------------------------------------


def test_no_effects_leave_the_voice_untouched() -> None:
    audio = voiced()
    assert apply_effects(audio, VoiceEffects()) is audio
    assert apply_effects(audio, None) is audio


def test_deepen_lowers_the_pitch_and_keeps_the_length() -> None:
    audio = voiced(f0=160.0)
    deeper = apply_effects(audio, VoiceEffects(deepen=40))  # 2 semitones
    assert len(deeper) == len(audio)
    assert pitch(deeper) == pytest.approx(160.0 * 2 ** (-2 / 12), rel=0.03)
    assert pitch(apply_effects(audio, VoiceEffects(deepen=100))) < pitch(deeper)


def test_broadcast_evens_out_loud_and_quiet_speech() -> None:
    loud, quiet = voiced(0.6, level=0.6), voiced(0.6, level=0.06)
    before = rms(loud) / rms(quiet)
    out = apply_effects(np.concatenate([loud, quiet]), VoiceEffects(broadcast=True))
    after = rms(out[: len(loud)]) / rms(out[len(loud) :])
    assert after < before / 2
    assert float(np.max(np.abs(out))) <= 10 ** (-1 / 20) + 0.01  # the limiter's ceiling


def test_presets_are_valid_effect_settings() -> None:
    assert not PRESETS["natural"].active
    assert all(fx.active for name, fx in PRESETS.items() if name != "natural")


# ---- built-in music -------------------------------------------------------------------------


@pytest.mark.parametrize("track_id", sorted(BUILTIN_TRACKS))
def test_built_in_tracks_are_the_same_every_time(track_id: str) -> None:
    audio = builtin_audio(track_id)
    assert audio.dtype == np.float32
    assert np.array_equal(audio, BUILTIN_TRACKS[track_id].render())
    assert 0.05 < float(np.max(np.abs(audio))) <= 0.9
    assert not audio.flags.writeable  # shared: callers copy before changing it


@pytest.mark.parametrize("track_id", [t for t, track in BUILTIN_TRACKS.items() if track.seamless])
def test_a_looping_bed_has_no_step_where_it_repeats(track_id: str) -> None:
    audio = builtin_audio(track_id)
    largest_step = float(np.max(np.abs(np.diff(audio))))
    assert abs(float(audio[0]) - float(audio[-1])) < largest_step / 2


def test_show_music_names_its_tracks() -> None:
    music = ShowMusic(intro="builtin:bright-intro", bed=str(uuid4()))
    assert len(music.track_ids()) == 2
    with pytest.raises(ValueError, match=r"pattern"):
        ShowMusic(bed="../../etc/passwd")


# ---- mixing ---------------------------------------------------------------------------------


def test_slots_are_cut_to_length_and_levelled() -> None:
    long = voiced(30.0, level=0.5)
    for slot, seconds in SLOT_SECONDS.items():
        fitted = fit_slot(long, slot)
        assert len(fitted) == int(seconds * SR)
        assert abs(float(fitted[-1])) < 0.01  # faded out
    assert rms(fit_slot(long, "intro")) == pytest.approx(SPEECH_RMS * 0.8, rel=0.05)


def test_an_uploaded_bed_loops_with_a_crossfade_and_a_built_in_one_tiles() -> None:
    bed = voiced(3.0)
    looped = loop_to(bed, 10 * SR, seamless=False)
    assert len(looped) == 10 * SR
    assert np.array_equal(loop_to(bed, 7 * SR, seamless=True)[3 * SR : 6 * SR], bed)


def test_the_bed_ducks_under_speech_and_rises_in_pauses() -> None:
    talk = (np.random.default_rng(0).standard_normal(3 * SR) * SPEECH_RMS).astype(np.float32)
    region = np.concatenate([talk, silence(2.0), talk])
    gains_db = 20 * np.log10(duck_gains(region, -22))
    assert gains_db[int(1.5 * SR)] == pytest.approx(-22, abs=0.5)  # while talking
    assert gains_db[int(4.5 * SR)] > -16  # well into the pause
    assert gains_db[int(5.0 * SR)] < gains_db[int(4.5 * SR)]  # already going down before speech


def test_the_bed_goes_only_between_intro_and_outro() -> None:
    mix = np.concatenate([voiced(2.0), voiced(6.0, level=0.1), voiced(2.0)])
    out = add_bed(mix, builtin_audio("builtin:calm-pad"), start=2 * SR, end=8 * SR,
                  level_db=-22, seamless=True)  # fmt: skip
    bed = out - mix
    assert np.all(bed[: 2 * SR] == 0)
    assert np.all(bed[8 * SR :] == 0)
    assert rms(bed[3 * SR : 7 * SR]) > 0
    assert add_bed(mix, voiced(), start=0, end=SR // 2, level_db=-22, seamless=False) is mix


def test_effects_follow_each_speaker_and_skip_a_clip_shared_by_two() -> None:
    lines = [{"speaker": s} for s in ("Alex", "Sam", "Alex", "Sam")]
    clips: list[np.ndarray | None] = [voiced(), voiced(), voiced(), None]  # the last two together
    out, report = apply_host_effects(lines, clips, {"Alex": VoiceEffects(deepen=40)})
    assert out[0] is not None
    assert out[0] is not clips[0]
    assert pitch(out[0]) < pitch(voiced())
    assert out[1] is clips[1]  # Sam has no effects
    assert out[2] is clips[2]  # Alex and Sam in one clip: left as it is
    assert report["clips"] == 1
    assert report["skipped_mixed_clips"] == 1
    assert apply_host_effects(lines, clips, {})[0] is clips


def test_missing_tracks_fall_back_and_uploads_are_credited() -> None:
    upload = str(uuid4())
    store = SimpleNamespace(get=lambda key: wav_bytes(voiced(20.0)))
    record = MusicTrackRecord(track_id=upload, name="Mine", credit="Music by Me", object_key="k")
    music = ShowMusic(intro="builtin:bright-intro", bed=upload, sting=str(uuid4()))
    tracks = load_show_tracks(music, {upload: record}, store)
    assert tracks.intro is not None
    assert tracks.bed is not None
    assert tracks.sting is None
    assert tracks.report["sting"]["missing"] is True
    assert tracks.credits == ["Music by Me"]
    assert tracks.bed_seamless is False


def test_an_episode_is_assembled_with_the_shows_music_and_effects() -> None:
    lines = [
        {"kind": "segment", "position": 1, "speaker": s, "text": "Words here.", "key": f"k{n}"}
        for n, s in enumerate(["Alex", "Sam", "Alex", "Sam"])
    ] + [{"kind": "segment", "position": 2, "speaker": "Alex", "text": "More.", "key": "k4"}]
    stored = {f"k{n}": wav_bytes(voiced(2.0)) for n in range(5)}
    saved: dict[str, Any] = {}
    show = SimpleNamespace(
        host_effects={"Alex": VoiceEffects(deepen=40)},
        music=ShowMusic(sting="builtin:two-note-sting", bed="builtin:lofi-loop"),
    )
    ctx: Any = SimpleNamespace(
        settings=SimpleNamespace(assets_dir=SimpleNamespace(), assembly_style="plain"),
        repo=SimpleNamespace(
            get_episode=lambda _: SimpleNamespace(voice_lines=lines, show_id=uuid4()),
            list_segments=lambda _: [
                SimpleNamespace(position=p, title=f"Part {p}") for p in (1, 2)
            ],
            get_show=lambda _: show,
            get_music_tracks=lambda ids: {},
            update_episode=lambda _, **fields: saved.update(fields),
        ),
        store=SimpleNamespace(
            get=stored.__getitem__, put=lambda key, data, _: stored.update({key: data})
        ),
    )
    ctx.settings.assets_dir = __import__("pathlib").Path("/nonexistent")
    assemble_service.assemble_episode(uuid4(), ctx)
    assembly = saved["assembly"]
    assert assembly["checks_pass"], assembly["checks"]
    assert assembly["effects"]["clips"] == 3
    assert assembly["music"]["bed"]["name"] == "Lo-fi loop"
    assert assembly["music"]["sting"]["name"] == "Two-note sting"
    assert assembly["between_segments"] == "music:builtin:two-note-sting"
    assert assembly["after"]["lufs"] == pytest.approx(-16.0, abs=1.0)


def test_without_a_sting_segments_are_joined_by_a_pause_not_a_chime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: dict[str, Any] = {}

    def combine(lines: Any, clips: Any, titles: Any, **parts: Any) -> Any:
        sent.update(parts)
        return voiced(3.0), []

    monkeypatch.setattr(assemble_service, "mix", combine)
    lines = [{"kind": "segment", "position": p, "speaker": "Alex", "text": "Hi.", "key": f"k{p}"}
             for p in (1, 2)]  # fmt: skip
    stored = {f"k{p}": wav_bytes(voiced(1.0)) for p in (1, 2)}
    saved: dict[str, Any] = {}
    ctx: Any = SimpleNamespace(
        settings=SimpleNamespace(assets_dir=__import__("pathlib").Path("/nonexistent"),
                                 assembly_style="plain"),
        repo=SimpleNamespace(
            get_episode=lambda _: SimpleNamespace(voice_lines=lines, show_id=uuid4()),
            list_segments=lambda _: [SimpleNamespace(position=p, title=f"P{p}") for p in (1, 2)],
            get_show=lambda _: SimpleNamespace(host_effects={}, music=ShowMusic()),
            get_music_tracks=lambda ids: {},
            update_episode=lambda _, **fields: saved.update(fields),
        ),
        store=SimpleNamespace(get=stored.__getitem__, put=lambda *a: None),
    )  # fmt: skip
    assemble_service.assemble_episode(uuid4(), ctx)
    assert len(sent["transition"]) == 0  # no chime between segments
    assert saved["assembly"]["between_segments"] == "pause"
    assert len(sent["intro"]) > 0  # the intro and outro keep theirs until music is chosen


# ---- type-to-speech in the voice worker ------------------------------------------------------


def test_text_is_split_into_pieces_without_losing_a_word() -> None:
    text = "Hello there. " + "This is a longer sentence, with commas, " * 12 + "The end!"
    parts = pieces(text)
    assert all(len(p) <= 250 for p in parts)
    assert " ".join(parts) == " ".join(text.split())
    assert pieces("One. Two. Three.") == ["One. Two. Three."]


def test_a_withdrawn_voices_studio_speech_can_be_found() -> None:
    keys = raw_speech_keys("a" * 64, "One. Two.", "warm")
    assert len(keys) == 1
    assert keys[0].startswith("tts/")
    assert raw_speech_keys("b" * 64, "One. Two.", "warm") != keys


def speak_ctx(voice: dict[str, Any], backend: str = "placeholder") -> tuple[Any, dict[str, Any]]:
    clip = SpeechClipRecord(
        clip_id=uuid4(), owner_id=uuid4(), voice=voice, text="Hello. How are you?",
        delivery="neutral", effects={"deepen": 40}, status="queued",
    )  # fmt: skip
    state: dict[str, Any] = {"stored": {}, "updates": []}
    ctx: Any = SimpleNamespace(
        settings=SimpleNamespace(
            tts_backend=backend,
            tts_model="m",
            config_dir=__import__("pathlib").Path(__file__).resolve().parents[2] / "config",
        ),
        budget=None,
        repo=SimpleNamespace(
            get_speech_clip=lambda _: clip,
            finish_speech_clip=lambda _, **fields: state["updates"].append(fields),
        ),
        store=SimpleNamespace(
            exists=lambda key: key in state["stored"],
            get=lambda key: state["stored"][key],
            put=lambda key, data, _: state["stored"].__setitem__(key, data),
        ),
    )
    state["clip"] = clip
    return ctx, state


def test_the_voice_worker_voices_a_clip_with_its_effects(monkeypatch: pytest.MonkeyPatch) -> None:
    ctx, state = speak_ctx({"kind": "engine", "host": "Sam"})
    monkeypatch.setattr(speak, "_backend", lambda *_: PlaceholderBackend())
    assert speak.speak_clip(state["clip"].clip_id, ctx) == "done"
    first, last = state["updates"][0], state["updates"][-1]
    assert first == {"status": "working"}
    assert last["status"] == "done"
    assert last["duration_s"] > 0
    audio = read_wav_bytes(state["stored"][last["object_key"]])
    assert len(audio) > 0
    cached = [k for k in state["stored"] if k.startswith("tts/")]
    assert len(cached) == 1  # the raw speech, for the next try with other effects


def test_a_recorded_voice_needs_chatterbox(monkeypatch: pytest.MonkeyPatch) -> None:
    ctx, state = speak_ctx({"kind": "recorded", "voice_id": str(uuid4())}, backend="placeholder")
    monkeypatch.setattr(speak, "backend_unavailable", lambda _: None)
    assert speak.speak_clip(state["clip"].clip_id, ctx) == "failed"
    assert "cannot speak recorded voices" in state["updates"][-1]["error"]


def test_a_failed_engine_gives_a_plain_reason(monkeypatch: pytest.MonkeyPatch) -> None:
    ctx, state = speak_ctx({"kind": "engine", "host": "Alex"})

    class Broken(PlaceholderBackend):
        def synthesise(self, speaker: str, text: str, delivery: str = "neutral") -> np.ndarray:
            raise RuntimeError("model crashed")

    monkeypatch.setattr(speak, "_backend", lambda *_: Broken())
    assert speak.speak_clip(state["clip"].clip_id, ctx) == "failed"
    assert state["updates"][-1]["error"] == "The voice engine failed on this text; try again."
