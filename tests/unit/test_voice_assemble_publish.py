from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import numpy as np
import pytest

from podcast_engine.common.audio import SR
from podcast_engine.common.queue import Stage
from podcast_engine.stages.assemble.service import mix, needs_normalisation
from podcast_engine.stages.publish.service import AI_DISCLOSURE, with_disclosure
from podcast_engine.stages.voice import service as voice_service
from podcast_engine.stages.voice.backends import PlaceholderBackend
from podcast_engine.stages.voice.service import dialogue_cache_key, segment_cache_key, voice_groups


def test_cache_key_depends_on_provider_voice_and_text() -> None:
    base = segment_cache_key("p", "v1", "hello")
    assert base == segment_cache_key("p", "v1", "hello")
    assert base != segment_cache_key("p", "v2", "hello")
    assert base != segment_cache_key("q", "v1", "hello")
    assert base != segment_cache_key("p", "v1", "hello!")


def test_loudness_within_tolerance_is_left_alone() -> None:
    assert not needs_normalisation(-16.5)
    assert needs_normalisation(-23.0)


def test_disclosure_added_once() -> None:
    notes = with_disclosure("Notes")
    assert notes.startswith(AI_DISCLOSURE)
    assert with_disclosure(notes) == notes


def spoken(kind: str, position: int | None, speaker: str, text: str = "Words.") -> dict[str, Any]:
    return {"kind": kind, "position": position, "speaker": speaker, "text": text}


EPISODE = [
    spoken("disclosure", None, "Alex"),
    spoken("opening", None, "Alex"),
    spoken("opening", None, "Sam"),
    spoken("segment", 1, "Alex"),
    spoken("segment", 1, "Sam"),
    spoken("segment", 1, "Alex"),
    spoken("segment", 2, "Sam"),
    spoken("closing", None, "Sam"),
    spoken("closing", None, "Alex"),
]


def test_each_part_of_the_episode_is_voiced_in_one_request() -> None:
    assert voice_groups(EPISODE, max_chars=3000) == [[0], [1, 2], [3, 4, 5], [6], [7, 8]]


def test_a_group_holds_at_most_two_speakers_and_the_character_limit() -> None:
    three = [spoken("segment", 1, name) for name in ("Alex", "Sam", "Jordan", "Alex")]
    assert voice_groups(three, max_chars=3000) == [[0, 1], [2, 3]]
    long = [spoken("segment", 1, "Alex", "x" * 40) for _ in range(5)]
    assert voice_groups(long, max_chars=100) == [[0, 1], [2, 3], [4]]


def test_a_dialogue_key_changes_with_any_word_or_voice() -> None:
    backend = PlaceholderBackend()
    base = dialogue_cache_key(backend, EPISODE[1:3])
    assert base == dialogue_cache_key(backend, [dict(line) for line in EPISODE[1:3]])
    edited = [EPISODE[1], {**EPISODE[2], "text": "Other words."}]
    assert base != dialogue_cache_key(backend, edited)
    swapped = [{**EPISODE[1], "speaker": "Sam"}, {**EPISODE[2], "speaker": "Alex"}]
    assert base != dialogue_cache_key(backend, swapped)


def test_lines_voiced_together_play_once_with_chapters_intact() -> None:
    one_second = np.full(SR, 0.1, dtype=np.float32)
    clips: list[np.ndarray | None] = [one_second, one_second, None, one_second, None, None]
    clips += [one_second, one_second, None]
    audio, chapters = mix(
        EPISODE,
        clips,
        {1: "First", 2: "Second"},
        intro=np.zeros(0, dtype=np.float32),
        outro=np.zeros(0, dtype=np.float32),
        transition=np.zeros(0, dtype=np.float32),
    )
    assert [title for _, title in chapters] == ["First", "Second"]
    assert np.count_nonzero(audio) == 5 * SR  # five clips, each played once


class CountingDialogue(PlaceholderBackend):
    """A placeholder that voices dialogue too, counting the requests it would send."""

    max_dialogue_chars = 3000

    def __init__(self) -> None:
        self.requests: list[list[str]] = []

    def synthesise(self, speaker: str, text: str) -> np.ndarray:
        self.requests.append([speaker])
        return super().synthesise(speaker, text)

    def synthesise_dialogue(self, lines: list[tuple[str, str]]) -> np.ndarray:
        self.requests.append([speaker for speaker, _ in lines])
        return np.concatenate([super().synthesise(s, t) for s, t in lines])


def test_the_voice_stage_sends_one_request_per_part_and_reuses_them(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    script = {
        "segments": {
            "1": [
                {"speaker": speaker, "text": f"Line {n}.", "claims": []}
                for n, speaker in enumerate(["Alex", "Sam", "Alex", "Sam"])
            ],
            "2": [{"speaker": "Alex", "text": "Last point.", "claims": []}],
        }
    }
    episode = SimpleNamespace(show_id=uuid4(), script=script, manifest={})
    saved: dict[str, Any] = {}
    stored: dict[str, bytes] = {}
    ctx: Any = SimpleNamespace(
        settings=SimpleNamespace(tts_backend="gemini"),
        repo=SimpleNamespace(
            get_episode=lambda _: episode,
            get_show=lambda _: SimpleNamespace(topic="Tides", host_count=2, host_voices={}),
            update_episode=lambda _, **fields: saved.update(fields),
        ),
        store=SimpleNamespace(
            exists=lambda key: key in stored,
            put=lambda key, data, _: stored.__setitem__(key, data),
        ),
        hosts=lambda count: ["Alex", "Sam"][:count],
    )
    fake = CountingDialogue()
    monkeypatch.setattr(voice_service, "_backend", lambda *_: fake)

    assert voice_service.synthesise_voices(uuid4(), ctx) is Stage.ASSEMBLE
    # disclosure, opening, segment 1, segment 2, closing: 5 requests for 10 lines
    assert len(fake.requests) == 5
    assert fake.requests[2] == ["Alex", "Sam", "Alex", "Sam"]
    keys = [line["key"] for line in saved["voice_lines"]]
    assert len(keys) == 10
    assert sum(key is not None for key in keys) == 5

    voice_service.synthesise_voices(uuid4(), ctx)  # a retry: everything comes from storage
    assert len(fake.requests) == 5
