from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import numpy as np
import pytest

from podcast_engine.common.audio import SR
from podcast_engine.common.llm import GeminiQuotaError
from podcast_engine.common.models import Claim, Delivery, ScriptLine
from podcast_engine.common.queue import Stage
from podcast_engine.common.quota import DailyBudget, MemoryCounter
from podcast_engine.stages.assemble.service import (
    SPEECH_RMS,
    mix,
    needs_normalisation,
    pause_after,
    tighten,
)
from podcast_engine.stages.publish.service import AI_DISCLOSURE, with_disclosure
from podcast_engine.stages.voice import service as voice_service
from podcast_engine.stages.voice.backends import ChatterboxBackend, PlaceholderBackend
from podcast_engine.stages.voice.service import (
    dialogue_cache_key,
    episode_lines,
    segment_cache_key,
    voice_groups,
)


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

    def synthesise(self, speaker: str, text: str, delivery: str = "neutral") -> np.ndarray:
        self.requests.append([speaker])
        return super().synthesise(speaker, text)

    def synthesise_dialogue(
        self, lines: list[tuple[str, str]], deliveries: list[str] | None = None
    ) -> np.ndarray:
        self.requests.append([speaker for speaker, _ in lines])
        return np.concatenate([super().synthesise(s, t) for s, t in lines])


def voice_ctx(budget: DailyBudget | None = None) -> tuple[Any, dict[str, Any]]:
    """A two-host episode of 10 spoken lines in 5 parts, with storage in memory."""
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
        settings=SimpleNamespace(tts_backend="gemini", tts_model="gemini-3.8-flash-tts"),
        budget=budget,
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
    return ctx, saved


def test_the_voice_stage_sends_one_request_per_part_and_reuses_them(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx, saved = voice_ctx()
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


def test_the_voice_stage_starts_only_if_todays_budget_covers_every_part(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    budget = DailyBudget(MemoryCounter(), {"gemini-3.8-flash-tts": 12})
    budget.spend("gemini-3.8-flash-tts", 8)  # 4 left; the episode needs 5
    ctx, _ = voice_ctx(budget)
    fake = CountingDialogue()
    monkeypatch.setattr(voice_service, "_backend", lambda *_: fake)

    with pytest.raises(GeminiQuotaError, match=r"voicing 5 part\(s\).*4 of today's 12 left"):
        voice_service.synthesise_voices(uuid4(), ctx)
    assert fake.requests == []  # nothing was sent, so nothing was half done


def test_a_delivery_changes_the_cache_key_but_a_neutral_line_keeps_its_old_one() -> None:
    plain = segment_cache_key("p", "v", "So, what changed?")
    assert segment_cache_key("p", "v", "So, what changed?", "neutral") == plain
    assert segment_cache_key("p", "v", "So, what changed?", "curious") != plain


def test_every_delivery_has_a_chatterbox_style() -> None:
    assert set(ChatterboxBackend.STYLES) == {d.value for d in Delivery}
    calm, lively = ChatterboxBackend.STYLES["serious"], ChatterboxBackend.STYLES["excited"]
    assert calm[0] < lively[0]  # an excited line is more expressive than a serious one


def test_voice_lines_carry_how_each_line_is_said_and_whether_it_is_a_fact() -> None:
    claim = Claim(claim_id=uuid4(), text="Rules changed in January.")
    script = {
        1: [
            ScriptLine(speaker="Alex", text="So what changed?", delivery=Delivery.CURIOUS),
            ScriptLine(speaker="Sam", text="Rules changed in January.", claims=(claim,)),
        ]
    }
    lines = episode_lines("Permits", ["Alex", "Sam"], script)
    segment = [line for line in lines if line["kind"] == "segment"]
    assert [(line["delivery"], line["claim"]) for line in segment] == [
        ("curious", False),
        ("neutral", True),
    ]
    assert lines[1]["delivery"] == "warm"  # the welcome


def test_a_clip_loses_the_silence_around_its_words_and_is_brought_to_speech_level() -> None:
    words = np.full(SR, 0.5, dtype=np.float32)
    clip = np.concatenate([np.zeros(SR // 2, dtype=np.float32), words, np.zeros(SR)])
    tight = tighten(clip)
    assert len(tight) < SR * 1.1  # the half second before and the second after are gone
    assert np.sqrt(np.mean(tight**2)) == pytest.approx(SPEECH_RMS, rel=0.1)


def test_pauses_follow_the_turns_of_the_conversation() -> None:
    def line(speaker: str, text: str, **extra: Any) -> dict[str, Any]:
        return {**spoken("segment", 1, speaker, text), **extra}

    fact = line("Sam", "The rules changed on January first for every student.", claim=True)
    question = line("Alex", "Wait, does that apply to everyone?")
    answer = line("Sam", "It applies to most new applicants, yes, from this year.")
    same = line("Sam", "And there is one more change.")
    reply = line("Alex", "Right.")
    assert pause_after(question, answer) < pause_after(fact, question)  # answers come in fast
    assert pause_after(fact, reply) == pause_after(question, answer)  # so do quick reactions
    assert pause_after(answer, same) < pause_after(fact, question)  # carrying on: brief
    assert pause_after(EPISODE[0], EPISODE[1]) == 0.7  # after the AI disclosure
